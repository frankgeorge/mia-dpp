# mypy: disable-error-code="attr-defined"
"""Human approve, correct, and reject orchestration."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from langgraph.types import interrupt

from mia_dpp.agent.state import AgentState
from mia_dpp.domain.completion import build_completion_summary
from mia_dpp.domain.contracts import (
    AgentReviewDecision,
    AgentReviewRequest,
    EvidenceRecord,
    EvidenceStatus,
    MappingResult,
    MappingStatus,
    ProposedFieldMapping,
    SemanticReviewItem,
    SourceLocation,
    SourceType,
    WebsiteIngestResponse,
)
from mia_dpp.idta import mapping_target

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class ReviewNodes:
    async def _human_review(self, state: AgentState) -> AgentState:
        items = tuple(SemanticReviewItem.model_validate(item) for item in state["review_items"])
        submission = AgentReviewRequest.model_validate(
            interrupt(
                {
                    "type": "semantic_mapping_review",
                    "reviewItems": [item.model_dump(mode="json") for item in items],
                    "allowedDecisions": ["approve", "correct", "reject"],
                }
            )
        )
        if submission.thread_id == "":
            raise ValueError("thread ID is required")
        decisions = {item.review_id: item for item in submission.decisions}
        expected = {item.id for item in items}
        if set(decisions) != expected:
            raise ValueError("a decision is required for every semantic proposal")
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        reviewed = [
            self._apply_review_decision(item, decisions[item.id], website) for item in items
        ]
        website = self._reconcile_review(website, reviewed)
        approved = sum(item.mapping.status is MappingStatus.APPROVED for item in reviewed)
        reply = (
            f"Review saved: {approved} semantic mapping"
            f"{'s' if approved != 1 else ''} approved and {len(reviewed) - approved} rejected. "
            "Approved mappings can now participate in deterministic compilation."
        )
        return {
            "website_result": website.model_dump(mode="json"),
            "review_items": [item.model_dump(mode="json") for item in reviewed],
            "reply": reply,
            "messages": [{"role": "assistant", "content": reply}],
            "status": "completed",
        }

    def _apply_review_decision(
        self,
        item: SemanticReviewItem,
        decision: AgentReviewDecision,
        website: WebsiteIngestResponse,
    ) -> SemanticReviewItem:
        if decision.decision == "reject":
            return item.model_copy(
                update={
                    "mapping": item.mapping.model_copy(update={"status": MappingStatus.REJECTED})
                }
            )
        if decision.decision == "approve":
            return item.model_copy(
                update={
                    "mapping": item.mapping.model_copy(update={"status": MappingStatus.APPROVED})
                }
            )

        requirement_id = decision.corrected_requirement_id or item.requirement_id
        requirements = {
            requirement.id: requirement
            for requirement in website.coverage_report.inventory.requirements
        }
        requirement = requirements.get(requirement_id)
        if requirement is None or requirement.semantic_id is None or requirement.wildcard:
            raise ValueError("corrected target must be a fixed official requirement")
        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        mapping = item.mapping
        if decision.corrected_value is not None:
            record = self._human_correction_evidence(
                mapping,
                decision.corrected_value,
            )
            package = website.knowledge_package.model_copy(
                update={"evidence": (*website.knowledge_package.evidence, record)}
            )
            website.knowledge_package = package
            website.evidence = package.evidence
            mapping = mapping.model_copy(
                update={
                    "evidence_id": record.id,
                    "source_value": decision.corrected_value,
                }
            )
        mapping = mapping.model_copy(
            update={
                "target_element": target.id_short,
                "semantic_id": target.semantic_id.primary_value,
                "target": target,
                "status": MappingStatus.APPROVED,
                "reasoning": (
                    "Corrected and approved by the human reviewer. "
                    + (decision.comment or "The official target was validated by MIA.")
                ),
            }
        )
        return SemanticReviewItem(id=item.id, requirement_id=requirement_id, mapping=mapping)

    def _human_correction_evidence(
        self,
        mapping: ProposedFieldMapping,
        value: str,
    ) -> EvidenceRecord:
        acquired_at = datetime.now(UTC)
        identity = f"{mapping.evidence_id}\0{value}\0{acquired_at.isoformat()}"
        return EvidenceRecord(
            id="ev-human-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            predicate="human.correction",
            source_label=mapping.source_field,
            value=value,
            source_type=SourceType.HUMAN,
            source_uri="mia://conversation/review",
            source_content_sha256=hashlib.sha256(value.encode()).hexdigest(),
            source_location=SourceLocation(excerpt=value),
            extraction_method="human_review_correction",
            extractor_name="mia-human-review",
            extractor_version="1",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )

    def _reconcile_review(
        self,
        website: WebsiteIngestResponse,
        reviewed: list[SemanticReviewItem],
    ) -> WebsiteIngestResponse:
        base = [
            item
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
            if item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        ]
        approved = [
            item.mapping for item in reviewed if item.mapping.status is MappingStatus.APPROVED
        ]
        mapped_ids = {item.evidence_id for item in (*base, *approved)}
        unmatched = tuple(item.id for item in website.evidence if item.id not in mapped_ids)
        result = MappingResult(mapped=(*base, *approved), unmatched_evidence_ids=unmatched)
        coverage = self._coverage_analyzer.analyze(
            website.knowledge_package,
            website.coverage_report.inventory,
            mapping_result=result,
        )
        return website.model_copy(
            update={
                "proposal": website.proposal.model_copy(update={"mappings": result.mapped}),
                "mapping_result": result,
                "coverage_report": coverage,
                "completion_summary": build_completion_summary(
                    coverage,
                    result,
                    website.knowledge_package.evidence,
                    rejected_evidence_ids={
                        item.mapping.evidence_id
                        for item in reviewed
                        if item.mapping.status is MappingStatus.REJECTED
                    },
                ),
            }
        )
