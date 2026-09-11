# mypy: disable-error-code="attr-defined"
"""Deterministic and semantic source resolution nodes."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Literal

from mia_dpp.agent.state import AgentState
from mia_dpp.api.schemas import WebsiteIngestResponse
from mia_dpp.domain.completion import build_completion_summary
from mia_dpp.domain.mappings import (
    MappingResult,
    MappingStatus,
    ProposedFieldMapping,
    SemanticReviewItem,
)
from mia_dpp.idta import mapping_target
from mia_dpp.resolution.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping_confidence,
)
from mia_dpp.workflow import completed_event

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class ResolveNodes:
    async def _resolve_semantics(self, state: AgentState) -> AgentState:
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        started_at = datetime.now(UTC)
        decisions = await self._semantic_tool.propose(
            website.knowledge_package,
            website.coverage_report,
        )
        already_used = {
            item.evidence_id
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
        }
        existing_paths = {
            item.target.instance_path
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
        }
        requirements = {item.id: item for item in website.coverage_report.inventory.requirements}
        evidence = {item.id: item for item in website.evidence}
        review_items: list[SemanticReviewItem] = []
        by_target = {
            (item.template_key, item.template_release, item.template_path): item
            for item in requirements.values()
        }
        for proposal in (*website.mapping_result.mapped, *website.mapping_result.ambiguous):
            if proposal.status is not MappingStatus.REVIEW:
                continue
            requirement = by_target.get(
                (
                    proposal.target.template_key,
                    proposal.target.template_release,
                    proposal.target.template_path,
                )
            )
            if requirement is None:
                continue
            identity = f"{requirement.id}\0{proposal.evidence_id}"
            review_items.append(
                SemanticReviewItem(
                    id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    requirement_id=requirement.id,
                    mapping=proposal,
                )
            )
        for decision in decisions:
            requirement = requirements.get(decision.requirement_id)
            record = evidence.get(decision.evidence_id)
            if requirement is None or record is None or record.id in already_used:
                continue
            template = self._repository.load(requirement.template_key)
            target = mapping_target(template, requirement.template_path)
            if target.instance_path in existing_paths:
                continue
            assessment = assess_mapping_confidence(
                source_label=MatchQuality.WEAK,
                value_format=ValueFormatQuality.PLAUSIBLE,
                semantic_match=MatchQuality.STRONG,
                destination_candidates=1,
            )
            mapping = ProposedFieldMapping(
                evidence_id=record.id,
                source_field=record.source_label or record.predicate,
                source_value=self._display_value(record.value, record.unit),
                target_element=target.id_short,
                semantic_id=target.semantic_id.primary_value,
                target=target,
                confidence=assessment.score,
                confidence_assessment=assessment,
                reasoning=(
                    "Semantic proposal from the configured model; human approval is required. "
                    + decision.reasoning
                ),
                status=MappingStatus.REVIEW,
            )
            identity = f"{decision.requirement_id}\0{decision.evidence_id}"
            review_items.append(
                SemanticReviewItem(
                    id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    requirement_id=decision.requirement_id,
                    mapping=mapping,
                )
            )
            already_used.add(record.id)
            existing_paths.add(target.instance_path)

        if review_items:
            existing_outcome_ids = {
                item.evidence_id
                for item in (
                    *website.mapping_result.mapped,
                    *website.mapping_result.ambiguous,
                )
            }
            semantic_review_mappings = tuple(
                item.mapping
                for item in review_items
                if item.mapping.evidence_id not in existing_outcome_ids
            )
            reviewed_ids = {
                item.mapping.evidence_id for item in review_items
            } | existing_outcome_ids
            summary_result = MappingResult(
                mapped=(*website.mapping_result.mapped, *semantic_review_mappings),
                ambiguous=website.mapping_result.ambiguous,
                unmatched_evidence_ids=tuple(
                    item.id for item in website.evidence if item.id not in reviewed_ids
                ),
            )
            website = website.model_copy(
                update={
                    "completion_summary": build_completion_summary(
                        website.coverage_report,
                        summary_result,
                        website.evidence,
                    )
                }
            )

        semantic_event = completed_event(
            stage="reasoning.semantic",
            started_at=started_at,
            input_count=website.coverage_report.statistics.unmatched_evidence,
            output_count=len(review_items),
            summary=(
                f"Produced {len(review_items)} constrained semantic proposal"
                f"{'s' if len(review_items) != 1 else ''} for human review."
            ),
            metadata={
                "configured": self._reasoning.configured,
                "authoritative": False,
            },
        )
        website = website.model_copy(
            update={"workflow_events": (*website.workflow_events, semantic_event)}
        )
        if review_items:
            reply = (
                f"I retained {len(website.evidence)} source facts and found "
                f"{len(review_items)} additional semantic proposal"
                f"{'s' if len(review_items) != 1 else ''}. Please review each before continuing."
            )
            return {
                "website_result": website.model_dump(mode="json"),
                "review_items": [item.model_dump(mode="json") for item in review_items],
                "reply": reply,
                "status": "awaiting_review",
            }

        if self._reasoning.configured:
            reply = (
                f"I retained {len(website.evidence)} source facts. The semantic model found no "
                "additional mapping that was safe enough to propose; unresolved evidence remains "
                "visible for later research or clarification."
            )
        else:
            reply = (
                f"I retained {len(website.evidence)} source facts and completed deterministic "
                "coverage. Configure OPENROUTER_API_KEY to reason over unresolved mappings."
            )
        return {
            "website_result": website.model_dump(mode="json"),
            "reply": reply,
            "messages": [{"role": "assistant", "content": reply}],
            "status": "completed",
        }

    async def _after_semantics(self, state: AgentState) -> Literal["review", "completion"]:
        return "review" if state.get("review_items") else "completion"
