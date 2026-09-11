"""End-to-end tests for the resumable LangGraph MVP without live model calls."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from mia_dpp.agent_workflow import MiaAgentWorkflow
from mia_dpp.extraction import RenderedPage
from mia_dpp.models import (
    AgentMessageRequest,
    AgentReviewDecision,
    AgentReviewRequest,
    AgentRunStatus,
    ChatMessage,
    ConversationDecision,
    CoverageReport,
    MappingStatus,
    ProductKnowledgePackage,
    SemanticMatchDecision,
    SourceType,
)
from mia_dpp.templates import OfficialTemplateRepository
from mia_dpp.url_policy import ProductUrlPolicy
from mia_dpp.website import WebsiteIngestionService

FIXTURE = Path(__file__).parent / "fixtures" / "web" / "website-product.html"
PRODUCT_URL = "https://manufacturer.example/products/pg-16"


async def public_resolver(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


class FixtureLoader:
    async def load(self, url: str) -> RenderedPage:
        return RenderedPage(url=url, html=FIXTURE.read_text(encoding="utf-8"))


class FakeReasoningService:
    def __init__(self) -> None:
        self.conversations: list[tuple[ChatMessage, ...]] = []

    @property
    def configured(self) -> bool:
        return True

    async def converse(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        self.conversations.append(tuple(messages))
        return ConversationDecision(
            intent="chat",
            reply="Please provide a direct manufacturer product-page URL.",
        )

    async def propose_semantic_matches(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        connectivity = next(
            item for item in package.evidence if item.source_label == "Connectivity"
        )
        family = next(
            item
            for item in coverage.inventory.requirements
            if item.template_key == "digital_nameplate"
            and item.id_short == "ManufacturerProductFamily"
        )
        return (
            SemanticMatchDecision(
                evidence_id=connectivity.id,
                requirement_id=family.id,
                reasoning="The fake model selected an existing evidence and requirement ID.",
            ),
        )


def workflow(reasoning: FakeReasoningService) -> MiaAgentWorkflow:
    repository = OfficialTemplateRepository()
    website = WebsiteIngestionService(
        repository,
        loader=FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    return MiaAgentWorkflow(repository, website, reasoning)


def test_conversation_uses_model_and_retains_thread_history() -> None:
    reasoning = FakeReasoningService()
    agent = workflow(reasoning)

    first = asyncio.run(agent.message(AgentMessageRequest(message="Hello, what can MIA do?")))
    second = asyncio.run(
        agent.message(
            AgentMessageRequest(
                thread_id=first.thread_id,
                message="What source should I provide?",
            )
        )
    )

    assert first.status is AgentRunStatus.COMPLETED
    assert second.thread_id == first.thread_id
    assert len(reasoning.conversations) == 2
    assert [item.role for item in reasoning.conversations[1]] == ["user", "assistant", "user"]
    assert "product-page URL" in second.reply


def test_url_runs_tools_then_pauses_and_resumes_human_review() -> None:
    agent = workflow(FakeReasoningService())

    pending = asyncio.run(
        agent.message(AgentMessageRequest(message=f"Please create a DPP from {PRODUCT_URL}"))
    )

    assert pending.status is AgentRunStatus.AWAITING_REVIEW
    assert pending.website_result is not None
    assert len(pending.website_result.evidence) >= 18
    assert pending.review_items
    proposal = pending.review_items[0]
    assert proposal.mapping.status is MappingStatus.REVIEW
    assert proposal.mapping.evidence_id in {
        item.id for item in pending.website_result.knowledge_package.evidence
    }
    assert proposal.requirement_id in {
        item.id for item in pending.website_result.coverage_report.inventory.requirements
    }
    assert pending.website_result.workflow_events[-1].stage == "reasoning.semantic"

    decisions = tuple(
        AgentReviewDecision(
            review_id=item.id,
            decision="approve" if item.id == proposal.id else "reject",
        )
        for item in pending.review_items
    )
    completed = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=pending.thread_id,
                decisions=decisions,
            )
        )
    )

    assert completed.status is AgentRunStatus.COMPLETED
    assert completed.review_items[0].mapping.status is MappingStatus.APPROVED
    assert "1 semantic mapping approved" in completed.reply
    assert completed.website_result is not None
    assert proposal.mapping.evidence_id not in {
        *completed.website_result.mapping_result.unmatched_evidence_ids,
    }


def test_chat_remains_available_without_consuming_pending_review() -> None:
    reasoning = FakeReasoningService()
    agent = workflow(reasoning)
    pending = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))

    reply = asyncio.run(
        agent.message(
            AgentMessageRequest(
                thread_id=pending.thread_id,
                message="No, 52161 would be an order number.",
            )
        )
    )

    assert reply.status is AgentRunStatus.AWAITING_REVIEW
    assert [item.id for item in reply.review_items] == [item.id for item in pending.review_items]
    assert reply.website_result == pending.website_result
    assert reasoning.conversations[-1][-1].content == "No, 52161 would be an order number."


def test_rejection_keeps_source_evidence_unmatched() -> None:
    agent = workflow(FakeReasoningService())
    pending = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))
    rejected_ids = {item.mapping.evidence_id for item in pending.review_items}
    completed = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=pending.thread_id,
                decisions=tuple(
                    AgentReviewDecision(review_id=item.id, decision="reject")
                    for item in pending.review_items
                ),
            )
        )
    )

    assert completed.website_result is not None
    assert rejected_ids <= {item.id for item in completed.website_result.evidence}
    assert rejected_ids <= set(completed.website_result.mapping_result.unmatched_evidence_ids)
    assert all(item.mapping.status is MappingStatus.REJECTED for item in completed.review_items)


def test_correction_uses_official_target_and_creates_human_evidence_for_new_value() -> None:
    agent = workflow(FakeReasoningService())
    pending = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))
    assert pending.website_result is not None
    selected = pending.review_items[0]
    corrected_requirement = next(
        item
        for item in pending.website_result.coverage_report.inventory.requirements
        if item.template_key == "digital_nameplate" and item.id_short == "ManufacturerProductFamily"
    )
    decisions = tuple(
        AgentReviewDecision(
            review_id=item.id,
            decision="correct" if item.id == selected.id else "reject",
            corrected_requirement_id=(corrected_requirement.id if item.id == selected.id else None),
            corrected_value="TankControl 25 LTE" if item.id == selected.id else None,
        )
        for item in pending.review_items
    )

    completed = asyncio.run(
        agent.review(AgentReviewRequest(thread_id=pending.thread_id, decisions=decisions))
    )

    assert completed.website_result is not None
    corrected = next(item for item in completed.review_items if item.id == selected.id)
    assert corrected.mapping.status is MappingStatus.APPROVED
    assert corrected.mapping.target_element == "ManufacturerProductFamily"
    assert corrected.mapping.source_value == "TankControl 25 LTE"
    human = next(
        item
        for item in completed.website_result.evidence
        if item.id == corrected.mapping.evidence_id
    )
    assert human.source_type is SourceType.HUMAN
    assert selected.mapping.evidence_id in {item.id for item in completed.website_result.evidence}
