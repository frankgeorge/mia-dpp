"""Agent V2 tests use PydanticAI's deterministic model, never a live LLM."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic_ai.models.test import TestModel

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.v2.models import AgentV2Request, AgentV2Status, MiaState
from mia_dpp.agent.v2.runtime import MiaAgentV2
from mia_dpp.agent.v2.store import InMemoryThreadStore, SQLiteThreadStore
from mia_dpp.tools.company.tool import CompanyDiscoveryTool
from mia_dpp.tools.mapping.resolver import ProductResolver
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
        web_tool=WebExtractionTool(loader=UnusedLoader()),
        mapping_tool=ProductResolver(repository),
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
        web_tool=WebExtractionTool(loader=UnusedLoader()),
        mapping_tool=ProductResolver(repository),
        dpp_pipeline=DeterministicDppPipeline(repository),
    )

    result = asyncio.run(runtime.message(AgentV2Request(message="Create a DPP")))

    assert result.status is AgentV2Status.AWAITING_INPUT
    assert result.trace_events[0].event_type == "run.configuration_required"
