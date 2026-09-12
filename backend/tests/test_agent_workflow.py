"""End-to-end tests for the resumable LangGraph MVP without live model calls."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.graph import MiaAgentWorkflow
from mia_dpp.agent.models import AgentMessageRequest, AgentReviewDecision, AgentReviewRequest
from mia_dpp.domain.evidence import ProductKnowledgePackage, SourceType
from mia_dpp.domain.mappings import (
    CoverageReport,
    MappingStatus,
    SemanticMatchDecision,
)
from mia_dpp.domain.workflow import AgentRunStatus
from mia_dpp.llm.chat import ChatMessage, ConversationDecision
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy

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

    async def decide(self, messages: Sequence[ChatMessage]) -> ConversationDecision:
        self.conversations.append(tuple(messages))
        return ConversationDecision(
            intent="chat",
            reply="Please provide a direct manufacturer product-page URL.",
        )

    async def propose(
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


class NoProposalReasoningService(FakeReasoningService):
    async def propose(
        self,
        package: ProductKnowledgePackage,
        coverage: CoverageReport,
    ) -> tuple[SemanticMatchDecision, ...]:
        return ()


def workflow(reasoning: FakeReasoningService) -> MiaAgentWorkflow:
    repository = OfficialTemplateRepository()
    web_tool = WebExtractionTool(
        loader=FixtureLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    return MiaAgentWorkflow(
        repository,
        web_tool,
        ProductResolver(repository),
        reasoning,
        reasoning,
    )


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

    assert completed.status is AgentRunStatus.AWAITING_INPUT
    assert completed.review_items[0].mapping.status is MappingStatus.APPROVED
    assert "finished processing" in completed.reply
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


def test_source_review_finishes_before_optional_or_missing_field_questions() -> None:
    agent = workflow(FakeReasoningService())
    review = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))
    assert review.status is AgentRunStatus.AWAITING_REVIEW
    assert "review" in review.reply.casefold()

    completed_source = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=review.thread_id,
                decisions=tuple(
                    AgentReviewDecision(review_id=item.id, decision="approve")
                    for item in review.review_items
                ),
            )
        )
    )

    assert completed_source.status is AgentRunStatus.AWAITING_OPTIONAL_CHOICE
    assert completed_source.website_result is not None
    nameplate = next(
        item
        for item in completed_source.website_result.completion_summary.fixed_templates
        if item.template_key == "digital_nameplate"
    )
    assert nameplate.mandatory_missing == 0
    assert not any(
        item.source_type is SourceType.HUMAN for item in completed_source.website_result.evidence
    )


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


def test_missing_mandatory_answers_become_evidence_and_resume_same_thread() -> None:
    class SparseLoader:
        async def load(self, url: str) -> RenderedPage:
            return RenderedPage(
                url=url,
                html="""
                <html><head><title>Controller</title></head><body>
                  <dl><dt>Manufacturer</dt><dd>Example GmbH</dd></dl>
                </body></html>
                """,
            )

    repository = OfficialTemplateRepository()
    web_tool = WebExtractionTool(
        loader=SparseLoader(),
        url_policy=ProductUrlPolicy(public_resolver),
    )
    reasoning = NoProposalReasoningService()
    agent = MiaAgentWorkflow(
        repository,
        web_tool,
        ProductResolver(repository),
        reasoning,
        reasoning,
    )

    review = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))
    assert review.status is AgentRunStatus.AWAITING_REVIEW
    first = asyncio.run(
        agent.review(
            AgentReviewRequest(
                thread_id=review.thread_id,
                decisions=tuple(
                    AgentReviewDecision(review_id=item.id, decision="approve")
                    for item in review.review_items
                ),
            )
        )
    )
    assert first.status is AgentRunStatus.AWAITING_INPUT
    assert "manufacturer product designation" in first.reply.casefold()

    second = asyncio.run(
        agent.message(
            AgentMessageRequest(
                thread_id=first.thread_id,
                message="Controller X",
            )
        )
    )
    assert second.thread_id == first.thread_id
    assert second.status is AgentRunStatus.AWAITING_INPUT
    assert second.website_result is not None
    human = [
        item for item in second.website_result.evidence if item.source_type is SourceType.HUMAN
    ]
    assert len(human) == 1
    assert human[0].value == "Controller X"
    assert "manufacturer product designation" not in second.reply.casefold()

    third = asyncio.run(
        agent.message(
            AgentMessageRequest(
                thread_id=first.thread_id,
                message="ORDER-42",
            )
        )
    )
    assert third.status is AgentRunStatus.AWAITING_OPTIONAL_CHOICE
    assert third.website_result is not None
    assert third.website_result.completion_summary.fixed_templates[0].mandatory_missing == 0

    ready = asyncio.run(
        agent.message(
            AgentMessageRequest(
                thread_id=first.thread_id,
                message="Continue with current data",
            )
        )
    )
    assert ready.status is AgentRunStatus.COMPLETED
    assert ready.thread_id == first.thread_id


def test_unavailable_answer_is_not_asked_repeatedly() -> None:
    agent = workflow(FakeReasoningService())
    pending = asyncio.run(agent.message(AgentMessageRequest(message=f"Build from {PRODUCT_URL}")))
    decisions = tuple(
        AgentReviewDecision(review_id=item.id, decision="reject") for item in pending.review_items
    )
    question = asyncio.run(
        agent.review(AgentReviewRequest(thread_id=pending.thread_id, decisions=decisions))
    )
    assert question.status is AgentRunStatus.AWAITING_INPUT
    first_question = question.reply

    next_question = asyncio.run(
        agent.message(AgentMessageRequest(thread_id=pending.thread_id, message="unavailable"))
    )
    assert next_question.reply != first_question
