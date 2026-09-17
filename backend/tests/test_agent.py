"""Persisted autonomous PydanticAI behavior tests."""

from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.dependencies import MiaDependencies
from mia_dpp.agent.models import (
    AgentRequest,
    AgentReviewDecision,
    AgentReviewRequest,
    AgentStatus,
    AgentValueRequest,
    MiaState,
    ProductWork,
)
from mia_dpp.agent.tools import AGENT_TOOLS, extract_product_page
from mia_dpp.config import Settings
from mia_dpp.domain.discovery import ProductSourceCandidate
from mia_dpp.mia import Mia
from mia_dpp.store import ArtifactKind, SessionSnapshot, Store
from mia_dpp.tools.mapping.mapper import DeterministicWebsiteMapper
from mia_dpp.tools.mapping.models import (
    BatchSemanticMappingResult,
    EvidenceMappingDecision,
    SemanticMappingMetrics,
    SemanticMappingRun,
)
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.mapping.semantic import deterministic_hints, lean_evidence, lean_targets
from mia_dpp.tools.search import SearchHit
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy


class FakeSearch:
    async def search(self, query: str, *, limit: int = 8) -> tuple[SearchHit, ...]:
        return (
            SearchHit(
                title="Siemens AG | Official website",
                url="https://www.siemens.com/global/en.html",
                snippet="Siemens AG industrial technology.",
            ),
            SearchHit(
                title="Siemens Energy | Official website",
                url="https://www.siemens-energy.com/",
                snippet="A separate energy technology company.",
            ),
        )


class FixtureLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def load(self, url: str) -> RenderedPage:
        self.calls.append(url)
        return RenderedPage(
            url=url,
            html="""
            <html><head><script type="application/ld+json">
            {"@context":"https://schema.org","@type":"Product","name":"Gauge PG-16",
             "model":"PG-16","manufacturer":{"name":"Example Instruments GmbH"},
             "serialNumber":"SN-2048","sku":"63820","productionDate":"2024"}
            </script></head><body><h1>Gauge PG-16</h1>
            <table><tr><th>Supply voltage</th><td>24 V</td></tr></table></body></html>
            """,
        )


class SlowFixtureLoader(FixtureLoader):
    async def load(self, url: str) -> RenderedPage:
        await asyncio.sleep(0.2)
        return await super().load(url)


class ScriptedTestModel(TestModel):
    def __init__(self, arguments: dict[str, dict[str, object]], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._arguments = arguments

    def gen_tool_args(self, tool_def: ToolDefinition) -> object:
        return self._arguments.get(tool_def.name, super().gen_tool_args(tool_def))


class PhasedTestModel(ScriptedTestModel):
    def __init__(self, phases: list[list[str]], **kwargs: object) -> None:
        super().__init__(call_tools=phases[0], **kwargs)
        self._phases = phases
        self._request_index = 0

    async def request(self, messages, model_settings, model_request_parameters):
        phase = self._request_index
        self._request_index += 1
        if phase < len(self._phases):
            self.call_tools = self._phases[phase]
            messages = [item for item in messages if not isinstance(item, ModelResponse)]
        else:
            self.call_tools = []
        return await super().request(messages, model_settings, model_request_parameters)


class FakeSemanticMapper:
    def __init__(self) -> None:
        self.calls = 0

    async def map(self, package, template_index, deterministic, *, reviewed_knowledge=()):
        self.calls += 1
        evidence = lean_evidence(package)
        targets = lean_targets(template_index)
        hints = deterministic_hints(deterministic, template_index)
        authoritative = {item.evidence_id: item.requirement_id for item in hints}
        semantic_target = targets[0].id if targets else None
        semantic_assigned = False
        decisions = []
        for item in evidence:
            if item.id in authoritative:
                decisions.append(
                    EvidenceMappingDecision(
                        evidence_id=item.id,
                        status="mapped",
                        requirement_id=authoritative[item.id],
                        reason="Preserve the deterministic mapping.",
                    )
                )
            elif not semantic_assigned and semantic_target is not None:
                semantic_assigned = True
                decisions.append(
                    EvidenceMappingDecision(
                        evidence_id=item.id,
                        status="mapped",
                        requirement_id=semantic_target,
                        reason="The fake mapper selected one official target for review.",
                    )
                )
            else:
                decisions.append(
                    EvidenceMappingDecision(
                        evidence_id=item.id,
                        status="unmapped",
                        reason="No suitable fixed official target exists.",
                    )
                )
        return SemanticMappingRun(
            evidence=evidence,
            targets=targets,
            deterministic_mappings=hints,
            result=BatchSemanticMappingResult(decisions=tuple(decisions)),
            metrics=SemanticMappingMetrics(
                evidence_count=len(evidence),
                target_count=len(targets),
                lean_evidence_json_bytes=1,
                lean_target_json_bytes=1,
                model_requests=1,
            ),
        )


class AllUnmatchedSemanticMapper(FakeSemanticMapper):
    async def map(self, package, template_index, deterministic, *, reviewed_knowledge=()):
        self.calls += 1
        evidence = lean_evidence(package)
        targets = lean_targets(template_index)
        hints = deterministic_hints(deterministic, template_index)
        authoritative = {item.evidence_id: item.requirement_id for item in hints}
        decisions = tuple(
            EvidenceMappingDecision(
                evidence_id=item.id,
                status="mapped",
                requirement_id=authoritative[item.id],
                reason="Preserve the deterministic mapping.",
            )
            if item.id in authoritative
            else EvidenceMappingDecision(
                evidence_id=item.id,
                status="unmapped",
                reason="No suitable fixed official target exists.",
            )
            for item in evidence
        )
        return SemanticMappingRun(
            evidence=evidence,
            targets=targets,
            deterministic_mappings=hints,
            result=BatchSemanticMappingResult(decisions=decisions),
            metrics=SemanticMappingMetrics(
                evidence_count=len(evidence),
                target_count=len(targets),
                lean_evidence_json_bytes=1,
                lean_target_json_bytes=1,
                model_requests=1,
            ),
        )


def build_mia(
    tmp_path: Path,
    model: TestModel,
    *,
    loader: FixtureLoader | None = None,
    semantic_mapper: FakeSemanticMapper | None = None,
) -> tuple[Mia, Store]:
    search = FakeSearch()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    mia = Mia(
        settings=Settings(
            openrouter_api_key=None,
            MIA_THREAD_STORE_PATH=tmp_path / "threads.sqlite3",
            MIA_WORKSPACE_ROOT=tmp_path / "workspaces",
        ),
        model=model,
        search_provider=search,
        web_tool=WebExtractionTool(
            loader=loader or FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ),
        semantic_mapper=semantic_mapper or FakeSemanticMapper(),
    )
    return mia, mia.store


def test_pydanticai_session_store_preserves_state_between_turns(tmp_path: Path) -> None:
    model = TestModel(
        call_tools=["search_companies"],
        custom_output_args={
            "reply": "Please select the intended company.",
            "status": "awaiting_company",
            "decision_summary": "The company identity is ambiguous.",
        },
    )
    agent, _ = build_mia(tmp_path, model)

    first = asyncio.run(agent.message(AgentRequest(message="Create a DPP for Siemens")))
    second = asyncio.run(
        agent.message(AgentRequest(thread_id=first.thread_id, message="Show the choices again"))
    )

    assert first.status is AgentStatus.AWAITING_COMPANY
    assert len(first.company_candidates) == 2
    assert second.thread_id == first.thread_id
    assert second.company_candidates == first.company_candidates


def test_one_pydanticai_run_can_call_multiple_tools_and_create_lineage(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-fixture"},
            "map_product_evidence": {"product_id": "product-fixture"},
        },
        call_tools=["extract_product_page", "map_product_evidence"],
        custom_output_args={
            "reply": "Evidence was extracted and mapped.",
            "status": "awaiting_input",
            "decision_summary": "Extraction and deterministic mapping completed.",
        },
    )
    agent, workspace = build_mia(tmp_path, model)

    result = asyncio.run(agent.message(AgentRequest(message=f"Create a DPP from {url}")))

    assert result.current_product is not None
    assert result.current_product.mapping_result is not None
    assert result.artifact_count >= 4
    artifacts = workspace.list_artifacts(result.thread_id)
    assert {item.kind.value for item in artifacts} >= {
        "source",
        "evidence",
        "mapping",
        "coverage",
    }
    mapping = next(item for item in artifacts if item.kind.value == "mapping")
    assert mapping.derived_from


def test_direct_url_does_not_trigger_company_confirmation_or_repeat_work(
    tmp_path: Path,
) -> None:
    url = "https://manufacturer.example/products/pg-16"
    loader = FixtureLoader()
    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-direct"},
            "search_companies": {"company_name": "Example Instruments"},
            "map_product_evidence": {"product_id": "product-direct"},
        },
        call_tools=[
            "extract_product_page",
            "extract_product_page",
            "search_companies",
            "map_product_evidence",
            "map_product_evidence",
        ],
        custom_output_args={
            "reply": "The direct product source was extracted and mapped.",
            "status": "awaiting_input",
            "decision_summary": "Reused completed work instead of requesting confirmation.",
        },
    )
    agent, workspace = build_mia(tmp_path, model, loader=loader)

    result = asyncio.run(agent.message(AgentRequest(message=f"Create a DPP from {url}")))

    assert loader.calls == [url]
    assert result.company_candidates == ()
    assert result.current_product is not None
    assert result.current_product.mapping_result is not None
    event_types = {event.event_type for event in result.trace_events}
    assert "web.extraction_reused" in event_types
    assert "company.search_skipped" in event_types
    assert "mapping.reused" in event_types
    artifacts = workspace.list_artifacts(result.thread_id)
    assert sum(item.kind is ArtifactKind.EVIDENCE for item in artifacts) == 1
    assert {item.name for item in artifacts if item.kind is ArtifactKind.MAPPING} == {
        "semantic-evidence.json",
        "semantic-targets.json",
        "batch-semantic-result.json",
        "mapping.json",
    }


def test_additional_source_stays_attached_to_the_current_product(tmp_path: Path) -> None:
    product_url = "https://manufacturer.example/products/pg-16"
    additional_url = "https://www.siemens.com/global/en.html"
    repository = OfficialTemplateRepository()
    search = FakeSearch()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    web_tool = WebExtractionTool(
        loader=FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    initial = asyncio.run(web_tool.extract(product_url))
    source_candidate = ProductSourceCandidate(
        id="source-additional",
        product_id="product-direct",
        title="Manufacturer details",
        url=additional_url,
        description="Official company page",
        authoritative_domain=True,
        source_uri=additional_url,
    )
    state = MiaState(
        thread_id="thread-additional-source",
        selected_product_ids=("product-direct",),
        current_product_id="product-direct",
        products={
            "product-direct": ProductWork(
                product_id="product-direct",
                product_name=initial.product_name,
                source_urls=(initial.evidence[0].source_uri,),
                source_artifact_ids=initial.source_artifact_ids,
                evidence=initial.evidence,
                source_candidates=(source_candidate,),
            )
        },
    )
    store = Store(tmp_path / "store.sqlite3", tmp_path / "workspaces")
    review = MappingReviewService(repository)
    dependencies = MiaDependencies(
        state=state,
        search=search,
        web_tool=web_tool,
        templates=repository,
        mapping_review=review,
        store=store,
    )

    observation = asyncio.run(
        extract_product_page(SimpleNamespace(deps=dependencies), additional_url)  # type: ignore[arg-type]
    )

    assert observation.identifiers == ("product-direct",)
    assert state.current_product_id == "product-direct"
    assert tuple(state.products) == ("product-direct",)
    assert len(state.products["product-direct"].source_urls) == 2


def test_direct_url_ignores_a_model_invented_product_id(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    repository = OfficialTemplateRepository()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    dependencies = MiaDependencies(
        state=MiaState(thread_id="thread-untrusted-product-id"),
        search=FakeSearch(),
        web_tool=WebExtractionTool(
            loader=FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ),
        templates=repository,
        mapping_review=MappingReviewService(repository),
        store=Store(tmp_path / "store.sqlite3", tmp_path / "workspaces"),
    )

    observation = asyncio.run(
        extract_product_page(SimpleNamespace(deps=dependencies), url, "null")  # type: ignore[arg-type]
    )

    product_id = observation.identifiers[0]
    assert product_id != "null"
    assert product_id in dependencies.state.products


def test_trace_is_observable_before_agent_run_completes(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    model = ScriptedTestModel(
        arguments={"extract_product_page": {"url": url, "product_id": "product-live"}},
        call_tools=["extract_product_page"],
        custom_output_args={
            "reply": "Extraction completed.",
            "status": "awaiting_input",
            "decision_summary": "The page was extracted.",
        },
    )
    agent, workspace = build_mia(tmp_path, model, loader=SlowFixtureLoader())
    thread_id = "thread-live-events"

    async def observe() -> None:
        task = asyncio.create_task(
            agent.message(AgentRequest(thread_id=thread_id, message=f"DPP from {url}"))
        )
        await asyncio.sleep(0.05)
        assert workspace.list_events(thread_id)
        assert not task.done()
        await task

    asyncio.run(observe())


def test_model_visible_tools_cannot_claim_human_authority() -> None:
    names = {tool.name for tool in AGENT_TOOLS}

    assert "review_semantic_mapping" not in names
    assert "record_human_requirement_value" not in names
    assert {"request_human_review", "request_human_value"} <= names


def test_human_review_resumes_the_same_persisted_session(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-review"},
            "map_product_evidence": {"product_id": "product-review"},
            "request_human_value": {
                "product_id": "product-review",
                "requirement_id": "ignored-while-review-pending",
                "question": "What is the manufacturer name?",
            },
            "request_human_review": {"product_id": "product-review"},
        },
        call_tools=[
            "extract_product_page",
            "map_product_evidence",
            "request_human_value",
            "request_human_review",
        ],
        custom_output_args={
            "reply": "The model claims an untrusted number of reviews.",
            "status": "awaiting_review",
            "decision_summary": "A human decision is required.",
        },
    )
    agent, workspace = build_mia(tmp_path, model)
    pending = asyncio.run(agent.message(AgentRequest(message=f"DPP from {url}")))

    assert pending.pending_human_request is not None
    assert pending.pending_human_request.kind.value == "mapping_review"
    assert pending.current_product is not None
    assert pending.current_product.status.value == "awaiting_review"
    assert not any(event.tool_name == "request_human_value" for event in pending.trace_events)
    reviews = pending.current_product.pending_reviews
    assert reviews
    assert f"- {len(reviews)} evidence row" in pending.reply
    assert "untrusted number" not in pending.reply
    decisions = tuple(
        AgentReviewDecision(
            review_id=item.id,
            decision="reject",
            comment="The source label means a different product property.",
        )
        for item in reviews
    )
    with pytest.raises(ValueError, match="stale"):
        asyncio.run(
            agent.review(
                AgentReviewRequest(
                    thread_id=pending.thread_id,
                    product_id="product-review",
                    mapping_cycle_id="cycle-stale",
                    decisions=decisions,
                )
            )
        )
    resumed = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=pending.thread_id,
                product_id="product-review",
                mapping_cycle_id=pending.current_product.mapping_cycle_id,
                decisions=decisions,
            )
        )
    )

    assert resumed.thread_id == pending.thread_id
    assert resumed.pending_human_request is None
    assert resumed.current_product is not None
    assert not resumed.current_product.pending_reviews
    review_artifact = next(
        item for item in workspace.list_artifacts(pending.thread_id) if item.kind.value == "review"
    )
    _, review_data = workspace.read_artifact(pending.thread_id, review_artifact.id)
    assert b'"comment": "The source label means a different product property."' in review_data
    with pytest.raises(ValueError, match="exactly one matching"):
        asyncio.run(
            agent.review(
                AgentReviewRequest(
                    thread_id=pending.thread_id,
                    product_id="product-review",
                    decisions=decisions,
                )
            )
        )


def test_semantic_mapping_has_a_structured_review_explanation(tmp_path: Path) -> None:
    repository = OfficialTemplateRepository()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    extraction = asyncio.run(
        WebExtractionTool(
            loader=FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ).extract("https://manufacturer.example/products/pg-16")
    )
    index = build_template_index(
        (repository.load("digital_nameplate"), repository.load("technical_data"))
    )
    mapping_result = asyncio.run(
        DeterministicWebsiteMapper(repository, index).propose(extraction.evidence)
    )
    service = MappingReviewService(repository)
    semantic_run = asyncio.run(
        FakeSemanticMapper().map(extraction, index, mapping_result)
    )
    result = service.apply_semantic_run(extraction, mapping_result, index, semantic_run)
    proposal = next(
        item
        for item in service.complete_review(extraction, result, index)
        if item.mapping is not None and item.mapping.mapping_origin.value == "semantic_agent"
    )

    assert proposal.mapping is not None
    assert proposal.mapping.llm_review is not None
    assert proposal.mapping.llm_review.evidence_ids == (proposal.evidence_id,)

    knowledge = Store(tmp_path / "reviewed-knowledge.sqlite3")
    candidate = knowledge.remember_mapping_candidate(
        proposal.mapping,
        manufacturer="Example Instruments GmbH",
        domain="manufacturer.example",
        product_family="Gauge",
    )
    assert candidate.status.value == "candidate"
    assert not knowledge.relevant_mapping_knowledge(
        proposal.mapping.source_field,
        manufacturer="Example Instruments GmbH",
        domain="manufacturer.example",
        template_keys=(proposal.mapping.target.template_key,),
    )

    _, _, reviewed = service.decide(
        extraction,
        result,
        index,
        proposal,
        decision="keep",
        thread_id="thread-knowledge-test",
        comment="Confirmed from the manufacturer's terminology.",
    )
    assert reviewed.mapping is not None
    trusted = knowledge.remember_mapping_review(
        reviewed.mapping,
        decision="keep",
        manufacturer="Example Instruments GmbH",
        domain="manufacturer.example",
        product_family="Gauge",
        comment="Confirmed from the manufacturer's terminology.",
    )
    assert trusted.status.value == "trusted"
    assert trusted.confirmations == 1
    assert trusted.human_comments == ("Confirmed from the manufacturer's terminology.",)
    assert knowledge.relevant_mapping_knowledge(
        proposal.mapping.source_field,
        manufacturer="Example Instruments GmbH",
        domain="manufacturer.example",
        template_keys=(proposal.mapping.target.template_key,),
    ) == (trusted,)
    assert not knowledge.relevant_mapping_knowledge(
        proposal.mapping.source_field,
        manufacturer="Unrelated Manufacturer",
        domain="unrelated.example",
        template_keys=(proposal.mapping.target.template_key,),
    )


def test_workspace_artifacts_are_isolated_by_thread(tmp_path: Path) -> None:
    store = Store(tmp_path / "store.sqlite3", tmp_path / "workspaces")
    first = store.write_json("thread-aaaaaaaa", ArtifactKind.EVIDENCE, "evidence.json", {"a": 1})
    store.write_json("thread-bbbbbbbb", ArtifactKind.EVIDENCE, "evidence.json", {"b": 2})

    _, data = store.read_artifact("thread-aaaaaaaa", first.id)
    assert b'"a": 1' in data
    with pytest.raises(KeyError):
        store.read_artifact("thread-bbbbbbbb", first.id)
    assert zipfile.is_zipfile(BytesIO(store.export_zip("thread-aaaaaaaa")))


def test_human_value_is_verified_and_resumes_the_deferred_agent(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    repository = OfficialTemplateRepository()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    web_tool = WebExtractionTool(
        loader=FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    package = asyncio.run(web_tool.extract(url))
    index = build_template_index((repository.load("digital_nameplate"),))
    deterministic = asyncio.run(
        DeterministicWebsiteMapper(repository, index).propose(package.evidence)
    )
    semantic = asyncio.run(
        AllUnmatchedSemanticMapper().map(package, index, deterministic)
    )
    mapping = MappingReviewService(repository).apply_semantic_run(
        package, deterministic, index, semantic
    )
    work = ProductWork(
        product_id="product-value",
        product_name=package.product_name,
        source_urls=(url,),
        source_artifact_ids=package.source_artifact_ids,
        acquired_sources=package.acquired_sources,
        evidence=package.evidence,
        mapping_result=mapping,
        template_index=index,
    )
    missing = next(
        item.requirement_id
        for item in work.coverage_report.coverage
        if item.status.value == "missing"
        and next(req for req in index.requirements if req.id == item.requirement_id).kind.value
        == "value"
    )
    model = ScriptedTestModel(
        arguments={
            "request_human_value": {
                "product_id": "product-value",
                "requirement_id": missing,
                "question": "Please provide the missing official value.",
            }
        },
        call_tools=["request_human_value"],
        custom_output_args={
            "reply": "The human value was saved.",
            "status": "awaiting_input",
            "decision_summary": "Trusted evidence was applied.",
        },
    )
    mia = Mia(
        settings=Settings(
            openrouter_api_key=None,
            MIA_THREAD_STORE_PATH=tmp_path / "value.sqlite3",
            MIA_WORKSPACE_ROOT=tmp_path / "value-workspace",
        ),
        model=model,
        search_provider=FakeSearch(),
        web_tool=web_tool,
        semantic_mapper=AllUnmatchedSemanticMapper(),
    )
    state = MiaState(
        thread_id="thread-human-value",
        current_product_id="product-value",
        selected_product_ids=("product-value",),
        products={"product-value": work},
        target_submodels=("digital_nameplate",),
    )
    mia.store.save(SessionSnapshot(state=state, history=[]))

    pending = asyncio.run(
        mia.message(AgentRequest(thread_id=state.thread_id, message="Continue the DPP"))
    )
    assert pending.pending_human_request is not None
    resumed = asyncio.run(
        mia.provide_value(
            AgentValueRequest(
                thread_id=state.thread_id,
                product_id="product-value",
                requirement_id=missing,
                value="Human verified value",
            )
        )
    )

    assert resumed.pending_human_request is None
    assert resumed.current_product is not None
    human = resumed.current_product.evidence[-1]
    assert human.status.value == "verified"
    assert human.source_type.value == "human"
    assert next(
        item
        for item in resumed.current_product.coverage_report.coverage
        if item.requirement_id == missing
    ).status.value == "satisfied"
    assert {item.name for item in mia.store.list_artifacts(state.thread_id)} >= {
        "human-evidence.json",
        "coverage-after-human-value.json",
    }


def test_controlled_workflow_reviews_once_then_builds_and_validates(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    model = PhasedTestModel(
        phases=[
            ["extract_product_page", "map_product_evidence", "request_human_review"],
            ["build_product_aas"],
        ],
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-e2e"},
            "map_product_evidence": {"product_id": "product-e2e"},
            "request_human_review": {"product_id": "product-e2e"},
            "build_product_aas": {"product_id": "product-e2e"},
        },
        custom_output_args={
            "reply": "The DPP was built and validated.",
            "status": "completed",
            "decision_summary": "The controlled workflow completed.",
        },
    )
    semantic = AllUnmatchedSemanticMapper()
    mia, workspace = build_mia(tmp_path, model, semantic_mapper=semantic)
    thread_id = "thread-controlled-e2e"
    workspace.save(
        SessionSnapshot(
            state=MiaState(
                thread_id=thread_id,
                target_submodels=("digital_nameplate",),
            ),
            history=[],
        )
    )

    pending = asyncio.run(
        mia.message(AgentRequest(thread_id=thread_id, message=f"Create a DPP from {url}"))
    )
    assert pending.pending_human_request is not None
    assert pending.current_product is not None
    reviews = pending.current_product.pending_reviews
    assert len(reviews) == len(pending.current_product.evidence)

    completed = asyncio.run(
        mia.review(
            AgentReviewRequest(
                thread_id=thread_id,
                product_id="product-e2e",
                mapping_cycle_id=pending.current_product.mapping_cycle_id,
                decisions=tuple(
                    AgentReviewDecision(review_id=item.id, decision="keep")
                    for item in reviews
                ),
            )
        )
    )

    assert semantic.calls == 1
    assert completed.pending_human_request is None
    assert completed.current_product is not None
    assert not completed.current_product.pending_reviews
    assert completed.current_product.aas_artifact_sha256 is not None, (
        model._request_index,
        [
            (item.event_type, item.tool_name, item.summary)
            for item in workspace.list_events(thread_id)
        ],
    )
    assert completed.current_product.status.value == "completed"
    names = {item.name for item in workspace.list_artifacts(thread_id)}
    assert {
        "rendered-source.html",
        "evidence.json",
        "batch-semantic-result.json",
        "mapping.json",
        "coverage.json",
        "mapping-review.json",
        "aas.json",
        "validation.json",
    } <= names
    persisted = workspace.load(thread_id)
    assert persisted is not None
    assert persisted.state.products["product-e2e"].confirmed_mapping_cycle_ids
