"""Human-oriented completion accounting over retained evidence and targets."""

from __future__ import annotations

from collections.abc import Sequence

from mia_dpp.models import (
    CompletionSummary,
    CoverageReport,
    CoverageStatus,
    FixedTemplateCompletion,
    MappingResult,
    MappingStatus,
    Requirement,
    RequirementKind,
    SourceFactStatistics,
    TechnicalDataCompletion,
)


def actionable_fixed_requirements(report: CoverageReport) -> tuple[Requirement, ...]:
    """Return fillable fixed fields, excluding structure and extension placeholders."""

    return tuple(
        requirement
        for requirement in report.inventory.requirements
        if requirement.kind is RequirementKind.VALUE and not requirement.wildcard
    )


def build_completion_summary(
    report: CoverageReport,
    mapping_result: MappingResult,
) -> CompletionSummary:
    """Summarize real completion without treating wildcard slots as form fields."""

    fixed = actionable_fixed_requirements(report)
    fixed_ids = {item.id for item in fixed}
    requirement_by_id = {item.id: item for item in report.inventory.requirements}
    coverage_by_id = {item.requirement_id: item for item in report.coverage}

    fixed_summaries: list[FixedTemplateCompletion] = []
    for template in report.inventory.selected_templates:
        requirements = [item for item in fixed if item.template_key == template.key]
        mandatory = [item for item in requirements if item.required]
        optional = [item for item in requirements if not item.required]

        def filled(items: Sequence[Requirement]) -> int:
            return sum(coverage_by_id[item.id].status is CoverageStatus.SATISFIED for item in items)

        mandatory_filled = filled(mandatory)
        optional_filled = filled(optional)
        fixed_summaries.append(
            FixedTemplateCompletion(
                template_key=template.key,
                template_name=template.family,
                mandatory_total=len(mandatory),
                mandatory_filled=mandatory_filled,
                mandatory_missing=len(mandatory) - mandatory_filled,
                optional_total=len(optional),
                optional_filled=optional_filled,
                optional_missing=len(optional) - optional_filled,
            )
        )

    outcomes = (*mapping_result.mapped, *mapping_result.ambiguous)
    auto_ids = {item.evidence_id for item in outcomes if item.status is MappingStatus.AUTO}
    approved_ids = {item.evidence_id for item in outcomes if item.status is MappingStatus.APPROVED}
    pending_ids = {item.evidence_id for item in outcomes if item.status is MappingStatus.REVIEW}
    rejected_ids = {item.evidence_id for item in outcomes if item.status is MappingStatus.REJECTED}
    analyzed = set(report.analyzed_evidence_ids)
    unresolved_ids = analyzed - auto_ids - approved_ids - pending_ids

    fixed_related_ids = {
        evidence_id
        for item in report.coverage
        if item.requirement_id in fixed_ids
        for evidence_id in (*item.supporting_evidence_ids, *item.candidate_evidence_ids)
    }
    technical_ids = analyzed - fixed_related_ids
    technical_resolved_ids = {
        item.evidence_id
        for item in outcomes
        if item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        and item.target.template_key == "technical_data"
        and item.evidence_id in technical_ids
    }

    assert all(item.id in requirement_by_id for item in fixed)
    return CompletionSummary(
        source=SourceFactStatistics(
            total_discovered=len(analyzed),
            automatically_resolved=len(auto_ids),
            accepted_after_review=len(approved_ids),
            pending_review=len(pending_ids),
            unresolved=len(unresolved_ids),
            rejected_proposals=len(rejected_ids),
        ),
        fixed_templates=tuple(fixed_summaries),
        technical_data=TechnicalDataCompletion(
            discovered=len(technical_ids),
            resolved=len(technical_resolved_ids),
            unresolved=len(technical_ids - technical_resolved_ids),
        ),
    )
