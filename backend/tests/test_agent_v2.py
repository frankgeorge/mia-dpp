"""Agent V2 tests use PydanticAI's deterministic model, never a live LLM."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.v2.models import AgentV2Request, AgentV2Status, MiaState
from mia_dpp.agent.v2.runtime import MiaAgentV2
from mia_dpp.agent.v2.store import InMemoryThreadStore, SQLiteThreadStore
from mia_dpp.domain.evidence import SourceType
from mia_dpp.domain.mappings import CoverageStatus, MappingOrigin, MappingStatus
from mia_dpp.domain.targets import RequirementKind
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.products.research import ProductResearchTool
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.search import SearchHit
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool


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


class UnusedLoader:
    async def load(self, url: str) -> RenderedPage:
        raise AssertionError(f"web extraction was not expected for {url}")


class FixtureLoader:
    async def load(self, url: str) -> RenderedPage:
        html = """
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"Gauge PG-16",
         "model":"PG-16","manufacturer":{"name":"Example Instruments GmbH"},
         "serialNumber":"SN-2048","sku":"63820","productionDate":"2024"}
        </script></head><body><h1>Gauge PG-16</h1>
        <table><tr><th>Supply voltage</th><td>24 V</td></tr></table></body></html>
        """
        return RenderedPage(url=url, html=html)


class ScriptedTestModel(TestModel):
    def __init__(self, arguments: dict[str, dict[str, object]], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._arguments = arguments

    def gen_tool_args(self, tool_def: ToolDefinition) -> object:
        return self._arguments.get(tool_def.name, super().gen_tool_args(tool_def))


def agent(store: InMemoryThreadStore | SQLiteThreadStore) -> MiaAgentV2:
    repository = OfficialTemplateRepository()
    search = FakeSearch()
    model = TestModel(
        call_tools=["search_companies"],
        custom_output_args={
            "reply": "Please select the intended company.",
            "status": "awaiting_company",
            "decision_summary": "The company name is ambiguous.",
        },
    )
    return MiaAgentV2(
        model=model,
        store=store,
        company_tool=CompanyDiscoveryTool(search),
        product_tool=ProductDiscoveryTool(search),
        product_research_tool=ProductResearchTool(search),
        web_tool=WebExtractionTool(loader=UnusedLoader()),
        mapping_tool=ProductResolver(repository),
        mapping_review=MappingReviewService(repository),
        dpp_pipeline=DeterministicDppPipeline(repository),
    )


def test_company_only_request_uses_discovery_and_returns_structured_choices() -> None:
    store = InMemoryThreadStore()
    result = asyncio.run(agent(store).message(AgentV2Request(message="Create a DPP for Siemens")))

    assert result.status is AgentV2Status.AWAITING_COMPANY
    assert {item.name for item in result.company_candidates} == {"Siemens AG", "Siemens Energy"}
    assert [item.event_type for item in result.trace_events] == [
        "run.started",
        "company.candidates",
        "run.completed",
    ]
    assert result.trace_events[1].tool_name == "search_companies"

    snapshot = asyncio.run(store.load(result.thread_id))
    assert snapshot is not None
    assert snapshot.state.company_candidates == result.company_candidates
    assert snapshot.messages


def test_sqlite_keeps_workflow_state_and_model_history_separate(tmp_path: Path) -> None:
    store = SQLiteThreadStore(tmp_path / "threads.sqlite3")
    result = asyncio.run(agent(store).message(AgentV2Request(message="DPP for Siemens")))

    loaded = asyncio.run(store.load(result.thread_id))
    assert loaded is not None
    assert isinstance(loaded.state, MiaState)
    assert loaded.state.user_goal == "DPP for Siemens"
    assert len(loaded.state.company_candidates) == 2
    assert len(loaded.messages) >= 2


def test_unconfigured_agent_does_not_attempt_a_model_or_tool_call() -> None:
    repository = OfficialTemplateRepository()
    search = FakeSearch()
    store = InMemoryThreadStore()
    runtime = MiaAgentV2(
        model=None,
        store=store,
        company_tool=CompanyDiscoveryTool(search),
        product_tool=ProductDiscoveryTool(search),
        product_research_tool=ProductResearchTool(search),
        web_tool=WebExtractionTool(loader=UnusedLoader()),
        mapping_tool=ProductResolver(repository),
        mapping_review=MappingReviewService(repository),
        dpp_pipeline=DeterministicDppPipeline(repository),
    )

    result = asyncio.run(runtime.message(AgentV2Request(message="Create a DPP")))

    assert result.status is AgentV2Status.AWAITING_INPUT
    assert result.trace_events[0].event_type == "run.configuration_required"


def test_one_agent_run_can_extract_then_map_without_a_fixed_graph() -> None:
    repository = OfficialTemplateRepository()
    search = FakeSearch()
    url = "https://manufacturer.example/products/pg-16"

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    from mia_dpp.tools.web.url_policy import ProductUrlPolicy

    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-fixture"},
            "map_product_evidence": {"product_id": "product-fixture"},
        },
        call_tools=["extract_product_page", "map_product_evidence"],
        custom_output_args={
            "reply": "Evidence was extracted and mapped.",
            "status": "awaiting_input",
            "decision_summary": "Used two capabilities in one autonomous run.",
        },
    )
    runtime = MiaAgentV2(
        model=model,
        store=InMemoryThreadStore(),
        company_tool=CompanyDiscoveryTool(search),
        product_tool=ProductDiscoveryTool(search),
        product_research_tool=ProductResearchTool(search),
        web_tool=WebExtractionTool(
            loader=FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ),
        mapping_tool=ProductResolver(repository),
        mapping_review=MappingReviewService(repository),
        dpp_pipeline=DeterministicDppPipeline(repository),
    )

    result = asyncio.run(runtime.message(AgentV2Request(message=f"Create a DPP from {url}")))

    assert result.current_product is not None
    assert result.current_product.extractions
    assert result.current_product.resolution is not None
    assert [item.tool_name for item in result.trace_events if item.tool_name] == [
        "extract_product_page",
        "map_product_evidence",
    ]
    assert result.current_product.resolution.evidence


def test_product_research_returns_typed_authoritative_sources() -> None:
    search = FakeSearch()
    tool = ProductResearchTool(search)

    candidates = asyncio.run(
        tool.search(
            product_id="product-siemens",
            product_name="SIMATIC controller",
            query="datasheet",
            manufacturer_domain="siemens.com",
        )
    )

    assert candidates
    assert candidates[0].product_id == "product-siemens"
    assert candidates[0].authoritative_domain is True


def test_semantic_proposal_is_bounded_and_rejection_retains_evidence() -> None:
    repository = OfficialTemplateRepository()
    store = InMemoryThreadStore()
    url = "https://manufacturer.example/products/pg-16"

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    from mia_dpp.tools.web.url_policy import ProductUrlPolicy

    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-fixture"},
            "map_product_evidence": {"product_id": "product-fixture"},
        },
        call_tools=["extract_product_page", "map_product_evidence"],
        custom_output_args={
            "reply": "Mapped fixture.",
            "status": "awaiting_input",
            "decision_summary": "Fixture ready.",
        },
    )
    runtime = MiaAgentV2(
        model=model,
        store=store,
        company_tool=CompanyDiscoveryTool(FakeSearch()),
        product_tool=ProductDiscoveryTool(FakeSearch()),
        product_research_tool=ProductResearchTool(FakeSearch()),
        web_tool=WebExtractionTool(
            loader=FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ),
        mapping_tool=ProductResolver(repository),
        mapping_review=MappingReviewService(repository),
        dpp_pipeline=DeterministicDppPipeline(repository),
    )
    response = asyncio.run(runtime.message(AgentV2Request(message=f"DPP from {url}")))
    assert response.current_product is not None
    result = response.current_product.resolution
    assert result is not None
    review_service = MappingReviewService(repository)
    context = review_service.semantic_context(result)
    assert context.evidence and context.requirements

    proposal = review_service.propose(
        result,
        evidence_id=context.evidence[0].id,
        requirement_id=context.requirements[0].id,
        reason_summary="The label may describe this official field.",
    )
    assert proposal.mapping.mapping_origin is MappingOrigin.SEMANTIC_AGENT
    assert proposal.mapping.status is MappingStatus.REVIEW

    rejected, decision = review_service.decide(
        result,
        proposal,
        decision="reject",
        thread_id=response.thread_id,
    )
    assert decision.mapping.status is MappingStatus.REJECTED
    assert proposal.mapping.evidence_id in rejected.mapping_result.unmatched_evidence_ids
    assert any(item.id == proposal.mapping.evidence_id for item in rejected.evidence)


def test_human_gap_answer_becomes_evidence_and_satisfies_requirement() -> None:
    repository = OfficialTemplateRepository()
    url = "https://manufacturer.example/products/pg-16"

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    from mia_dpp.tools.mapping.models import WebsiteIngestRequest
    from mia_dpp.tools.web.url_policy import ProductUrlPolicy

    web_tool = WebExtractionTool(
        loader=FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    extraction = asyncio.run(web_tool.extract(url))
    result = asyncio.run(
        ProductResolver(repository).resolve(extraction, WebsiteIngestRequest(url=url))
    )
    missing = next(
        requirement
        for requirement, coverage in zip(
            result.coverage_report.inventory.requirements,
            result.coverage_report.coverage,
            strict=True,
        )
        if coverage.status is CoverageStatus.MISSING
        and requirement.semantic_id is not None
        and not requirement.wildcard
        and requirement.kind is RequirementKind.VALUE
        and requirement.id_short is not None
    )

    updated = MappingReviewService(repository).record_human_value(
        result,
        requirement_id=missing.id,
        value="human supplied value",
        thread_id="thread-human-answer",
    )

    human = updated.evidence[-1]
    assert human.source_type is SourceType.HUMAN
    assert human.source_uri.endswith(missing.id)
    coverage = next(
        item for item in updated.coverage_report.coverage if item.requirement_id == missing.id
    )
    assert coverage.status is CoverageStatus.SATISFIED
    accepted = next(item for item in updated.mapping_result.mapped if item.evidence_id == human.id)
    assert accepted.mapping_origin is MappingOrigin.HUMAN
    assert accepted.human_reviewed is True
