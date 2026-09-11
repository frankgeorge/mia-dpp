# mypy: disable-error-code="attr-defined"
"""Mandatory and optional completion interview nodes."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Literal

from langgraph.types import interrupt

from mia_dpp.agent.state import AgentState
from mia_dpp.api.schemas import WebsiteIngestResponse
from mia_dpp.domain.completion import actionable_fixed_requirements, build_completion_summary
from mia_dpp.domain.evidence import EvidenceRecord, EvidenceStatus, SourceLocation, SourceType
from mia_dpp.domain.mappings import MappingResult, MappingStatus, ProposedFieldMapping
from mia_dpp.domain.targets import Requirement
from mia_dpp.idta import mapping_target
from mia_dpp.resolution.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping_confidence,
)

_URL = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)


class CompleteNodes:
    async def _assess_completion(self, state: AgentState) -> AgentState:
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        asked = set(state.get("asked_requirement_ids", []))
        mandatory = self._unfilled_requirements(website, required=True, asked=asked)
        if mandatory:
            requirement = mandatory[0]
            summary = website.completion_summary
            nameplate = next(
                (
                    item
                    for item in summary.fixed_templates
                    if item.template_key == "digital_nameplate"
                ),
                summary.fixed_templates[0],
            )
            label = self._requirement_label(requirement)
            return {
                "active_requirement_id": requirement.id,
                "completion_phase": "mandatory",
                "reply": (
                    "I have finished processing the available source information. "
                    f"Mandatory fields: {nameplate.mandatory_filled} / "
                    f"{nameplate.mandatory_total} filled. I could not establish "
                    f"{label}. What is the {label}?"
                ),
                "status": "awaiting_input",
            }

        unresolved_mandatory = self._unfilled_requirements(
            website,
            required=True,
            asked=set(),
        )
        if unresolved_mandatory:
            return {
                "reply": (
                    "Source processing is complete, but the remaining mandatory fields were "
                    "marked unavailable. MIA preserved those gaps and will not ask again in "
                    "this session."
                ),
                "status": "completed",
            }

        if state.get("optional_enabled", False):
            optional = self._unfilled_requirements(website, required=False, asked=asked)
            if optional:
                requirement = optional[0]
                label = self._requirement_label(requirement)
                return {
                    "active_requirement_id": requirement.id,
                    "completion_phase": "optional",
                    "reply": f"Optional field: what is the {label}?",
                    "status": "awaiting_input",
                }
            return {
                "reply": "The selected optional fields are complete. MIA is ready to compile.",
                "status": "completed",
            }

        summary = website.completion_summary
        nameplate = next(
            (item for item in summary.fixed_templates if item.template_key == "digital_nameplate"),
            summary.fixed_templates[0],
        )
        return {
            "reply": (
                "All mandatory information is available. "
                f"Mandatory: {nameplate.mandatory_filled} / {nameplate.mandatory_total}. "
                f"Optional: {nameplate.optional_filled} / {nameplate.optional_total}. "
                "Continue with current data, or add optional information?"
            ),
            "status": "awaiting_optional_choice",
        }

    async def _after_completion_assessment(
        self,
        state: AgentState,
    ) -> Literal["input", "optional", "done"]:
        if state["status"] == "awaiting_input":
            return "input"
        if state["status"] == "awaiting_optional_choice":
            return "optional"
        return "done"

    async def _human_completion(self, state: AgentState) -> AgentState:
        payload = interrupt(
            {
                "type": "requirement_answer",
                "requirementId": state["active_requirement_id"],
                "phase": state["completion_phase"],
            }
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
            raise ValueError("a human answer is required")
        answer = payload["answer"].strip()
        website = WebsiteIngestResponse.model_validate(state["website_result"])
        requirements = {item.id: item for item in website.coverage_report.inventory.requirements}
        requirement = requirements[state["active_requirement_id"]]
        asked = set(state.get("asked_requirement_ids", []))
        asked.update(self._same_concept_requirement_ids(website, requirement))

        if self._answer_is_unavailable(answer):
            return {
                "asked_requirement_ids": sorted(asked),
                "messages": [{"role": "user", "content": answer}],
                "reply": (
                    f"I recorded {self._requirement_label(requirement)} as unavailable and "
                    "will preserve the gap rather than ask repeatedly."
                ),
            }
        if not answer:
            return {
                "reply": f"Please provide a value for {self._requirement_label(requirement)}.",
                "status": "awaiting_input",
            }

        website = self._accept_human_answer(website, requirement, answer)
        return {
            "website_result": website.model_dump(mode="json"),
            "asked_requirement_ids": sorted(asked),
            "messages": [{"role": "user", "content": answer}],
            "reply": f"I validated and retained {self._requirement_label(requirement)}.",
        }

    async def _optional_choice(self, state: AgentState) -> AgentState:
        payload = interrupt(
            {
                "type": "optional_completion_choice",
                "choices": ["continue", "add_optional"],
            }
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("choice"), str):
            raise ValueError("an optional completion choice is required")
        choice = payload["choice"].strip().casefold()
        if "optional" not in choice and not choice.startswith("add"):
            return {
                "reply": "Continuing with the current evidence. MIA is ready to compile.",
                "messages": [{"role": "user", "content": payload["choice"]}],
                "status": "completed",
            }

        website = WebsiteIngestResponse.model_validate(state["website_result"])
        optional = self._unfilled_requirements(
            website,
            required=False,
            asked=set(state.get("asked_requirement_ids", [])),
        )
        if not optional:
            return {
                "reply": "No applicable optional fixed fields remain. MIA is ready to compile.",
                "status": "completed",
            }
        requirement = optional[0]
        return {
            "optional_enabled": True,
            "active_requirement_id": requirement.id,
            "completion_phase": "optional",
            "reply": f"Optional field: what is the {self._requirement_label(requirement)}?",
            "messages": [{"role": "user", "content": payload["choice"]}],
            "status": "awaiting_input",
        }

    async def _after_optional_choice(self, state: AgentState) -> Literal["input", "done"]:
        return "input" if state["status"] == "awaiting_input" else "done"

    def _accept_human_answer(
        self,
        website: WebsiteIngestResponse,
        requirement: Requirement,
        answer: str,
    ) -> WebsiteIngestResponse:
        if requirement.semantic_id is None or requirement.wildcard:
            raise ValueError("human completion requires a fixed semantic target")
        acquired_at = datetime.now(UTC)
        identity = f"{requirement.id}\0{answer}\0{acquired_at.isoformat()}"
        evidence = EvidenceRecord(
            id="ev-human-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            predicate="human.requirement_answer",
            source_label=requirement.id_short or self._requirement_label(requirement),
            canonical_predicate=None,
            value=answer,
            source_type=SourceType.HUMAN,
            source_uri=f"mia://conversation/requirement/{requirement.id}",
            source_content_sha256=hashlib.sha256(answer.encode()).hexdigest(),
            source_location=SourceLocation(excerpt=answer),
            extraction_method="human_requirement_answer",
            extractor_name="mia-human-completion",
            extractor_version="1",
            status=EvidenceStatus.VERIFIED,
            acquired_at=acquired_at,
        )
        target = mapping_target(
            self._repository.load(requirement.template_key),
            requirement.template_path,
        )
        assessment = assess_mapping_confidence(
            source_label=MatchQuality.EXACT,
            value_format=ValueFormatQuality.VALID,
            semantic_match=MatchQuality.EXACT,
            destination_candidates=1,
        )
        mapping = ProposedFieldMapping(
            evidence_id=evidence.id,
            source_field=f"Human answer: {self._requirement_label(requirement)}",
            source_value=answer,
            target_element=target.id_short,
            semantic_id=target.semantic_id.primary_value,
            target=target,
            confidence=assessment.score,
            confidence_assessment=assessment,
            reasoning=(
                "The human supplied this value for the explicit official requirement; "
                "MIA validated the target against the pinned template."
            ),
            status=MappingStatus.APPROVED,
        )
        package = website.knowledge_package.model_copy(
            update={"evidence": (*website.knowledge_package.evidence, evidence)}
        )
        accepted = [
            item
            for item in (*website.mapping_result.mapped, *website.mapping_result.ambiguous)
            if item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        ]
        accepted.append(mapping)
        mapped_ids = {item.evidence_id for item in accepted}
        result = MappingResult(
            mapped=tuple(accepted),
            unmatched_evidence_ids=tuple(
                item.id for item in package.evidence if item.id not in mapped_ids
            ),
        )
        coverage = self._coverage_analyzer.analyze(
            package,
            website.coverage_report.inventory,
            mapping_result=result,
        )
        return website.model_copy(
            update={
                "evidence": package.evidence,
                "knowledge_package": package,
                "proposal": website.proposal.model_copy(update={"mappings": result.mapped}),
                "mapping_result": result,
                "coverage_report": coverage,
                "completion_summary": build_completion_summary(
                    coverage,
                    result,
                    package.evidence,
                ),
            }
        )

    @staticmethod
    def _unfilled_requirements(
        website: WebsiteIngestResponse,
        *,
        required: bool,
        asked: set[str],
    ) -> list[Requirement]:
        accepted_targets = {
            (
                item.target.template_key,
                item.target.template_release,
                item.target.template_path,
            )
            for item in (
                *website.mapping_result.mapped,
                *website.mapping_result.ambiguous,
            )
            if item.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
        }
        candidates = [
            item
            for item in actionable_fixed_requirements(website.coverage_report)
            # The current deterministic compiler targets Digital Nameplate only.
            # Other selected templates remain analyzed, but are not interview gates yet.
            if item.template_key == "digital_nameplate"
            and item.required is required
            and item.id not in asked
            and (item.template_key, item.template_release, item.template_path)
            not in accepted_targets
        ]
        candidates.sort(
            key=lambda item: (
                item.template_key != "digital_nameplate",
                len(item.template_path),
                item.template_path,
            )
        )
        unique: list[Requirement] = []
        concepts: set[str] = set()
        for item in candidates:
            concept = (item.id_short or "/".join(item.template_path)).casefold()
            if concept not in concepts:
                concepts.add(concept)
                unique.append(item)
        return unique

    @staticmethod
    def _same_concept_requirement_ids(
        website: WebsiteIngestResponse,
        selected: Requirement,
    ) -> set[str]:
        concept = (selected.id_short or "/".join(selected.template_path)).casefold()
        return {
            item.id
            for item in actionable_fixed_requirements(website.coverage_report)
            if (item.id_short or "/".join(item.template_path)).casefold() == concept
        }

    @staticmethod
    def _answer_is_unavailable(answer: str) -> bool:
        normalized = " ".join(answer.casefold().strip(". ").split())
        return normalized in {
            "unknown",
            "unavailable",
            "not available",
            "not applicable",
            "n/a",
            "na",
            "i don't know",
            "i do not know",
        }

    @staticmethod
    def _requirement_label(requirement: Requirement) -> str:
        raw = requirement.id_short or requirement.template_path[-1]
        words = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", raw)
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", words).casefold()
