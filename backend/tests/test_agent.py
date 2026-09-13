"""Combined LangGraph lifecycle and autonomous PydanticAI behavior tests."""

from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.brain import AutonomousAgent
from mia_dpp.agent.graph import MiaAgent
from mia_dpp.agent.models import (
    AgentRequest,
    AgentReviewDecision,
    AgentReviewRequest,
    AgentStatus,
)
from mia_dpp.agent.tools import AGENT_TOOLS
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.products.research import ProductResearchTool
from mia_dpp.tools.products.tool import ProductDiscoveryTool
from mia_dpp.tools.search import SearchHit
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy
from mia_dpp.workspace.models import ArtifactKind
from mia_dpp.workspace.store import FileWorkspaceStore


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
    async def load(self, url: str) -> RenderedPage:
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


class ScriptedTestModel(TestModel):
    def __init__(self, arguments: dict[str, dict[str, object]], **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._arguments = arguments

    def gen_tool_args(self, tool_def: ToolDefinition) -> object:
        return self._arguments.get(tool_def.name, super().gen_tool_args(tool_def))


def build_agent(
    tmp_path: Path,
    model: TestModel,
    *,
    loader: FixtureLoader | None = None,
) -> tuple[MiaAgent, FileWorkspaceStore]:
    repository = OfficialTemplateRepository()
    search = FakeSearch()

    async def public_resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    workspace = FileWorkspaceStore(tmp_path / "workspaces")
    review = MappingReviewService(repository)
    brain = AutonomousAgent(
        model=model,
        company_tool=CompanyDiscoveryTool(search),
        product_tool=ProductDiscoveryTool(search),
        product_research_tool=ProductResearchTool(search),
        web_tool=WebExtractionTool(
            loader=loader or FixtureLoader(),
            url_policy=ProductUrlPolicy(public_resolver),
        ),
        mapping_tool=ProductResolver(repository),
        mapping_review=review,
        dpp_pipeline=DeterministicDppPipeline(repository),
        workspace=workspace,
    )
    return (
        MiaAgent(
            brain=brain,
            mapping_review=review,
            workspace=workspace,
            database_path=tmp_path / "threads.sqlite3",
        ),
        workspace,
    )


def test_langgraph_runs_pydanticai_and_checkpoints_state(tmp_path: Path) -> None:
    model = TestModel(
        call_tools=["search_companies"],
        custom_output_args={
            "reply": "Please select the intended company.",
            "status": "awaiting_company",
            "decision_summary": "The company identity is ambiguous.",
        },
    )
    agent, _ = build_agent(tmp_path, model)

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
    agent, workspace = build_agent(tmp_path, model)

    result = asyncio.run(agent.message(AgentRequest(message=f"Create a DPP from {url}")))

    assert result.current_product is not None
    assert result.current_product.resolution is not None
    assert result.artifact_count >= 6
    artifacts = workspace.list_artifacts(result.thread_id)
    assert {item.kind.value for item in artifacts} >= {
        "source",
        "evidence",
        "mapping",
        "coverage",
        "trace",
    }
    mapping = next(item for item in artifacts if item.kind.value == "mapping")
    assert mapping.derived_from


def test_model_visible_tools_cannot_claim_human_authority() -> None:
    names = {tool.name for tool in AGENT_TOOLS}

    assert "review_semantic_mapping" not in names
    assert "record_human_requirement_value" not in names
    assert {"request_human_review", "request_human_value"} <= names


def test_human_review_resumes_the_same_langgraph_checkpoint(tmp_path: Path) -> None:
    url = "https://manufacturer.example/products/pg-16"
    model = ScriptedTestModel(
        arguments={
            "extract_product_page": {"url": url, "product_id": "product-review"},
            "map_product_evidence": {"product_id": "product-review"},
            "request_human_review": {"product_id": "product-review"},
        },
        call_tools=[
            "extract_product_page",
            "map_product_evidence",
            "request_human_review",
        ],
        custom_output_args={
            "reply": "Please review the mappings.",
            "status": "awaiting_review",
            "decision_summary": "A human decision is required.",
        },
    )
    agent, workspace = build_agent(tmp_path, model)
    pending = asyncio.run(agent.message(AgentRequest(message=f"DPP from {url}")))

    assert pending.pending_human_request is not None
    assert pending.current_product is not None
    reviews = pending.current_product.pending_reviews
    assert reviews
    resumed = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=pending.thread_id,
                product_id="product-review",
                decisions=tuple(
                    AgentReviewDecision(review_id=item.id, decision="reject") for item in reviews
                ),
            )
        )
    )

    assert resumed.thread_id == pending.thread_id
    assert resumed.pending_human_request is None
    assert resumed.current_product is not None
    assert not resumed.current_product.pending_reviews
    assert any(item.kind.value == "review" for item in workspace.list_artifacts(pending.thread_id))


def test_workspace_artifacts_are_isolated_by_thread(tmp_path: Path) -> None:
    store = FileWorkspaceStore(tmp_path / "workspaces")
    first = store.write_json("thread-aaaaaaaa", ArtifactKind.EVIDENCE, "evidence.json", {"a": 1})
    store.write_json("thread-bbbbbbbb", ArtifactKind.EVIDENCE, "evidence.json", {"b": 2})

    _, data = store.read_artifact("thread-aaaaaaaa", first.id)
    assert b'"a": 1' in data
    with pytest.raises(KeyError):
        store.read_artifact("thread-bbbbbbbb", first.id)
    assert zipfile.is_zipfile(BytesIO(store.export_zip("thread-aaaaaaaa")))
