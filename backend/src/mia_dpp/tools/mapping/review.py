"""Deterministic validation and application of semantic/human mapping decisions."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.domain.evidence import EvidenceRecord, EvidenceStatus, SourceLocation, SourceType
from mia_dpp.domain.mappings import (
    CoverageStatus,
    LlmReview,
    MappingAssessment,
    MappingBasis,
    MappingOrigin,
    MappingResult,
    MappingStatus,
    ProposedFieldMapping,
    SemanticReviewItem,
)
from mia_dpp.domain.targets import RequirementKind
from mia_dpp.tools.mapping.models import ProductResolution, SemanticMappingContext
from mia_dpp.tools.mapping.targets import mapping_target


class MappingReviewService:
    """Validate and apply semantic or human mapping decisions.

    Agent tools call this after deterministic mapping. It constrains proposals to
    retained evidence and official targets, then recalculates coverage after a
    human approval, correction, rejection, or missing-field answer.
    """

    def __init__(self, repository: OfficialTemplateRepository) -> None:
        self._repository = repository

    @staticmethod
    def pending_deterministic_reviews(
        result: ProductResolution,
    ) -> tuple[SemanticReviewItem, ...]:
        """Convert deterministic review mappings into stable frontend review items."""

        requirements = {
            (item.template_key, item.template_release, item.template_path): item
            for item in result.coverage_report.inventory.requirements
        }
        reviews: list[SemanticReviewItem] = []
        for mapping in (*result.mapping_result.mapped, *result.mapping_result.ambiguous):
            if mapping.status is not MappingStatus.REVIEW:
                continue
            requirement = requirements.get(
                (
                    mapping.target.template_key,
                    mapping.target.template_release,
                    mapping.target.template_path,
                )
            )
            if requirement is None:
                continue
            identity = f"{requirement.id}\0{mapping.evidence_id}"
            reviews.append(
                SemanticReviewItem(
                    id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    requirement_id=requirement.id,
                    mapping=mapping,
                )
            )
        return tuple(reviews)

    @staticmethod
    def semantic_context(result: ProductResolution) -> SemanticMappingContext:
        """Return only unmatched evidence and unresolved official value requirements."""

        unresolved = set(result.mapping_result.unmatched_evidence_ids)
        evidence = tuple(
            item for item in result.knowledge_package.evidence if item.id in unresolved
        )
        unresolved_requirements = {
            item.requirement_id
            for item in result.coverage_report.coverage
            if item.status is not CoverageStatus.SATISFIED
        }
        requirements = tuple(
            item
            for item in result.coverage_report.inventory.requirements
            if item.id in unresolved_requirements
            and item.semantic_id is not None
            and not item.wildcard
            and item.kind is RequirementKind.VALUE
        )
        return SemanticMappingContext(
            product_id=result.knowledge_package.product_id,
            evidence=evidence[:30],
            requirements=requirements[:80],
        )

    def propose(
        self,
        result: ProductResolution,
        *,
        evidence_id: str,
        requirement_id: str,
        reason_summary: str,
    ) -> SemanticReviewItem:
        """Validate one model-proposed evidence/requirement pair and queue review."""

        context = self.semantic_context(result)
        record = next((item for item in context.evidence if item.id == evidence_id), None)
        requirement = next(
            (item for item in context.requirements if item.id == requirement_id),
            None,
        )
        if record is None:
            raise ValueError("semantic proposal must use currently unresolved evidence")
        if requirement is None or requirement.semantic_id is None:
            raise ValueError("semantic proposal must use an allowed official requirement")
        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        assessment = MappingAssessment(
            basis=MappingBasis.SEMANTIC,
            review_required=True,
            reason="The semantic model proposed one allowed official target.",
            uncertainties=("Semantic proposals require human review.",),
        )
        identity = f"{requirement_id}\0{evidence_id}"
        return SemanticReviewItem(
            id="review-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            requirement_id=requirement_id,
            mapping=ProposedFieldMapping(
                evidence_id=record.id,
                source_field=record.source_label or record.predicate,
                source_value=self._display_value(record.value, record.unit),
                target_element=target.id_short,
                semantic_id=target.semantic_id.primary_value,
                target=target,
                assessment=assessment,
                reasoning=(
                    "Semantic proposal constrained to retained evidence and an official target. "
                    + reason_summary
                ),
                status=MappingStatus.REVIEW,
                mapping_origin=MappingOrigin.SEMANTIC_AGENT,
                llm_review=LlmReview(
                    conclusion=(
                        f'"{record.source_label or record.predicate}" most likely maps to '
                        f"{target.id_short}."
                    ),
                    rationale=reason_summary,
                    evidence_ids=(record.id,),
                    uncertainties=assessment.uncertainties,
                ),
            ),
        )

    def decide(
        self,
        result: ProductResolution,
        item: SemanticReviewItem,
        *,
        decision: Literal["approve", "correct", "reject"],
        thread_id: str,
        corrected_requirement_id: str | None = None,
        corrected_value: str | None = None,
        comment: str | None = None,
    ) -> tuple[ProductResolution, SemanticReviewItem]:
        """Apply one human decision and return recalculated mapping/coverage state."""

        mapping = item.mapping
        if decision == "reject":
            reviewed = item.model_copy(
                update={
                    "mapping": mapping.model_copy(
                        update={
                            "status": MappingStatus.REJECTED,
                            "human_reviewed": True,
                            "human_comment": comment,
                        }
                    )
                }
            )
            return self._reconcile(result, reviewed), reviewed

        requirement_id = corrected_requirement_id or item.requirement_id
        requirement = next(
            (
                requirement
                for requirement in result.coverage_report.inventory.requirements
                if requirement.id == requirement_id
            ),
            None,
        )
        if requirement is None or requirement.semantic_id is None or requirement.wildcard:
            raise ValueError("review target must be a fixed official requirement")
        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        if corrected_value is not None:
            record = self._human_evidence(mapping, corrected_value, thread_id)
            package = result.knowledge_package.model_copy(
                update={"evidence": (*result.knowledge_package.evidence, record)}
            )
            result = result.model_copy(update={"knowledge_package": package})
            mapping = mapping.model_copy(
                update={"evidence_id": record.id, "source_value": corrected_value}
            )
        reviewed = SemanticReviewItem(
            id=item.id,
            requirement_id=requirement_id,
            mapping=mapping.model_copy(
                update={
                    "target_element": target.id_short,
                    "semantic_id": target.semantic_id.primary_value,
                    "target": target,
                    "status": MappingStatus.APPROVED,
                    "mapping_origin": (
                        MappingOrigin.HUMAN if decision == "correct" else mapping.mapping_origin
                    ),
                    "human_reviewed": True,
                    "human_comment": comment,
                    "reasoning": "Validated and accepted through human mapping review.",
                }
            ),
        )
        return self._reconcile(result, reviewed), reviewed

    def record_human_value(
        self,
        result: ProductResolution,
        *,
        requirement_id: str,
        value: str,
        thread_id: str,
    ) -> ProductResolution:
        """Turn a missing-field answer into human evidence and recalculate coverage."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("human evidence value must not be empty")
        requirement = next(
            (
                item
                for item in result.coverage_report.inventory.requirements
                if item.id == requirement_id
            ),
            None,
        )
        if (
            requirement is None
            or requirement.semantic_id is None
            or requirement.wildcard
            or requirement.kind is not RequirementKind.VALUE
        ):
            raise ValueError("human answer must target a fixed official value requirement")
        current = next(
            item
            for item in result.coverage_report.coverage
            if item.requirement_id == requirement_id
        )
        if current.status is CoverageStatus.SATISFIED:
            raise ValueError("the requirement is already satisfied")

        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        evidence = self._human_requirement_evidence(
            requirement_id=requirement_id,
            source_label=requirement.id_short or target.id_short,
            value=cleaned,
            thread_id=thread_id,
        )
        assessment = MappingAssessment(
            basis=MappingBasis.HUMAN,
            review_required=False,
            reason="A trusted human supplied this value for the selected official target.",
        )
        mapping = ProposedFieldMapping(
            evidence_id=evidence.id,
            source_field=requirement.id_short or target.id_short,
            source_value=cleaned,
            target_element=target.id_short,
            semantic_id=target.semantic_id.primary_value,
            target=target,
            assessment=assessment,
            reasoning="Human supplied this value for the identified official requirement.",
            status=MappingStatus.APPROVED,
            mapping_origin=MappingOrigin.HUMAN,
            human_reviewed=True,
        )
        package = result.knowledge_package.model_copy(
            update={"evidence": (*result.knowledge_package.evidence, evidence)}
        )
        updated = result.model_copy(update={"knowledge_package": package})
        review_seed = f"{requirement_id}\0{evidence.id}"
        review = SemanticReviewItem(
            id="review-" + hashlib.sha256(review_seed.encode()).hexdigest()[:24],
            requirement_id=requirement_id,
            mapping=mapping,
        )
        return self._reconcile(updated, review)

    def _reconcile(
        self,
        result: ProductResolution,
        reviewed: SemanticReviewItem,
    ) -> ProductResolution:
        retained = [
            item
            for item in (
                *result.mapping_result.mapped,
                *result.mapping_result.ambiguous,
                *result.mapping_result.rejected,
            )
            if item.evidence_id != reviewed.mapping.evidence_id
            and item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        ]
        rejected = [
            item
            for item in result.mapping_result.rejected
            if item.evidence_id != reviewed.mapping.evidence_id
        ]
        if reviewed.mapping.status is MappingStatus.REJECTED:
            rejected.append(reviewed.mapping)
        else:
            retained.append(reviewed.mapping)
        mapped_ids = {
            item.evidence_id
            for item in retained
            if item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        }
        mapping_result = MappingResult(
            mapped=tuple(retained),
            rejected=tuple(rejected),
            unmatched_evidence_ids=tuple(
                item.id for item in result.knowledge_package.evidence if item.id not in mapped_ids
            ),
        )
        return result.model_copy(update={"mapping_result": mapping_result})

    @staticmethod
    def _human_evidence(
        mapping: ProposedFieldMapping,
        value: str,
        thread_id: str,
    ) -> EvidenceRecord:
        acquired_at = datetime.now(UTC)
        identity = f"{thread_id}\0{mapping.evidence_id}\0{value}\0{acquired_at.isoformat()}"
        return EvidenceRecord(
            id="ev-human-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            predicate="human.correction",
            source_label=mapping.source_field,
            value=value,
            source_type=SourceType.HUMAN,
            source_uri=f"mia://conversation/{thread_id}/review",
            source_content_sha256=hashlib.sha256(value.encode()).hexdigest(),
            source_location=SourceLocation(excerpt=value),
            extraction_method="human_review_correction",
            extractor_name="mia-agent",
            extractor_version="2",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )

    @staticmethod
    def _human_requirement_evidence(
        *,
        requirement_id: str,
        source_label: str,
        value: str,
        thread_id: str,
    ) -> EvidenceRecord:
        acquired_at = datetime.now(UTC)
        identity = f"{thread_id}\0{requirement_id}\0{value}\0{acquired_at.isoformat()}"
        return EvidenceRecord(
            id="ev-human-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            predicate="human.answer",
            source_label=source_label,
            value=value,
            source_type=SourceType.HUMAN,
            source_uri=f"mia://conversation/{thread_id}/requirement/{requirement_id}",
            source_content_sha256=hashlib.sha256(value.encode()).hexdigest(),
            source_location=SourceLocation(excerpt=value),
            extraction_method="human_requirement_answer",
            extractor_name="mia-agent",
            extractor_version="2",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )

    @staticmethod
    def _display_value(value: object, unit: str | None) -> str:
        text = str(value)
        return f"{text} {unit}" if unit and not text.endswith(unit) else text
