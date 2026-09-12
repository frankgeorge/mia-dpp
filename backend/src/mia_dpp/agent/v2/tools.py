"""Small model-visible tool surface over MIA's typed capabilities."""

from __future__ import annotations

import hashlib
import time
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_ai import RunContext, Tool

from mia_dpp.agent.v2.dependencies import MiaDependencies
from mia_dpp.agent.v2.models import AgentV2Status, ProductWork, TraceStatus
from mia_dpp.domain.base import WireModel
from mia_dpp.domain.mappings import FieldMapping, MappingStatus
from mia_dpp.tools.mapping.models import WebsiteIngestRequest
from mia_dpp.tools.search import SearchUnavailableError


class ToolObservation(WireModel):
    outcome: str
    summary: str
    count: int = Field(ge=0)
    identifiers: tuple[str, ...] = ()


class SemanticContextObservation(WireModel):
    outcome: str
    product_id: str
    evidence: tuple[dict[str, object], ...]
    requirements: tuple[dict[str, object], ...]


async def search_companies(
    ctx: RunContext[MiaDependencies],
    company_name: str,
) -> ToolObservation:
    """Find plausible legal/manufacturer identities for a company name."""

    started = time.monotonic()
    try:
        candidates = await ctx.deps.company_tool.search(company_name)
    except SearchUnavailableError as error:
        ctx.deps.state.add_event(
            "company.search",
            str(error),
            status=TraceStatus.FAILED,
            tool_name="search_companies",
            input_summary=company_name,
        )
        return ToolObservation(outcome="unavailable", summary=str(error), count=0)
    ctx.deps.state.company_candidates = candidates
    ctx.deps.state.status = AgentV2Status.AWAITING_COMPANY
    ctx.deps.state.add_event(
        "company.candidates",
        f"Found {len(candidates)} candidate companies.",
        tool_name="search_companies",
        input_summary=company_name,
        output_summary=f"{len(candidates)} structured candidates",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={"count": len(candidates)},
    )
    return ToolObservation(
        outcome="candidates_found" if candidates else "no_results",
        summary="Ask the user to select a candidate." if candidates else "No company found.",
        count=len(candidates),
        identifiers=tuple(item.id for item in candidates),
    )


async def select_company(
    ctx: RunContext[MiaDependencies],
    company_id: str,
) -> ToolObservation:
    """Select one previously discovered company by its exact candidate ID."""

    candidate = next(
        (item for item in ctx.deps.state.company_candidates if item.id == company_id),
        None,
    )
    if candidate is None:
        return ToolObservation(
            outcome="invalid_selection",
            summary="The company ID is not in the current candidate set.",
            count=0,
        )
    ctx.deps.state.selected_company = candidate
    ctx.deps.state.status = AgentV2Status.RUNNING
    ctx.deps.state.add_event(
        "company.selected",
        f"Selected {candidate.name}.",
        tool_name="select_company",
        output_summary=candidate.domain,
    )
    return ToolObservation(
        outcome="selected",
        summary=f"Selected {candidate.name}; product discovery can continue.",
        count=1,
        identifiers=(candidate.id,),
    )


async def discover_products(
    ctx: RunContext[MiaDependencies],
    query: str = "",
) -> ToolObservation:
    """Find official product pages for the currently selected company."""

    company = ctx.deps.state.selected_company
    if company is None:
        return ToolObservation(
            outcome="company_required",
            summary="Select a company before discovering products.",
            count=0,
        )
    started = time.monotonic()
    try:
        candidates = await ctx.deps.product_tool.discover(company, query=query)
    except SearchUnavailableError as error:
        ctx.deps.state.add_event(
            "product.search",
            str(error),
            status=TraceStatus.FAILED,
            tool_name="discover_products",
            input_summary=query or company.name,
        )
        return ToolObservation(outcome="unavailable", summary=str(error), count=0)
    ctx.deps.state.product_candidates = candidates
    ctx.deps.state.status = AgentV2Status.AWAITING_PRODUCT
    ctx.deps.state.add_event(
        "product.candidates",
        f"Found {len(candidates)} official-domain product candidates.",
        tool_name="discover_products",
        input_summary=query or "industrial products catalogue",
        output_summary=f"{len(candidates)} structured candidates",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={"count": len(candidates)},
    )
    return ToolObservation(
        outcome="candidates_found" if candidates else "no_results",
        summary="Ask the user to select products." if candidates else "No products found.",
        count=len(candidates),
        identifiers=tuple(item.id for item in candidates),
    )


async def select_products(
    ctx: RunContext[MiaDependencies],
    product_ids: list[str],
) -> ToolObservation:
    """Queue one or more previously discovered products by exact candidate IDs."""

    by_id = {item.id: item for item in ctx.deps.state.product_candidates}
    unknown = [item for item in product_ids if item not in by_id]
    if unknown:
        return ToolObservation(
            outcome="invalid_selection",
            summary=f"Unknown product IDs: {', '.join(unknown)}",
            count=0,
        )
    unique = tuple(dict.fromkeys(product_ids))
    ctx.deps.state.selected_product_ids = unique
    ctx.deps.state.product_queue = unique
    ctx.deps.state.current_product_id = unique[0] if unique else None
    for product_id in unique:
        ctx.deps.state.products.setdefault(
            product_id,
            ProductWork(product_id=product_id, candidate=by_id[product_id]),
        )
    ctx.deps.state.status = AgentV2Status.RUNNING
    ctx.deps.state.add_event(
        "product.selected",
        f"Queued {len(unique)} product{'s' if len(unique) != 1 else ''}.",
        tool_name="select_products",
        metadata={"count": len(unique)},
    )
    return ToolObservation(
        outcome="selected",
        summary="Selected products are ready for evidence extraction.",
        count=len(unique),
        identifiers=unique,
    )


async def extract_product_page(
    ctx: RunContext[MiaDependencies],
    url: str,
    product_id: str | None = None,
) -> ToolObservation:
    """Extract provenance-rich evidence from one exact public product-page URL."""

    started = time.monotonic()
    extraction = await ctx.deps.web_tool.extract(url)
    resolved_id = product_id or extraction.knowledge_package.product_id
    candidate = next(
        (item for item in ctx.deps.state.product_candidates if item.id == resolved_id),
        None,
    )
    work = ctx.deps.state.products.get(resolved_id) or ProductWork(
        product_id=resolved_id,
        candidate=candidate,
    )
    if extraction.source_url not in {item.source_url for item in work.extractions}:
        work.extractions = (*work.extractions, extraction)
    ctx.deps.state.products[resolved_id] = work
    if resolved_id not in ctx.deps.state.selected_product_ids:
        ctx.deps.state.selected_product_ids = (*ctx.deps.state.selected_product_ids, resolved_id)
    ctx.deps.state.current_product_id = resolved_id
    ctx.deps.state.status = AgentV2Status.RUNNING
    evidence = extraction.knowledge_package.evidence
    ctx.deps.state.add_event(
        "web.evidence_extracted",
        f"Retained {len(evidence)} facts from {extraction.source_url}.",
        tool_name="extract_product_page",
        product_id=resolved_id,
        input_summary=url,
        output_summary=f"{len(evidence)} evidence records",
        source_ids=extraction.knowledge_package.source_artifact_ids,
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={"evidenceCount": len(evidence)},
    )
    return ToolObservation(
        outcome="evidence_extracted",
        summary="Run deterministic mapping for this product next.",
        count=len(evidence),
        identifiers=(resolved_id,),
    )


async def map_product_evidence(
    ctx: RunContext[MiaDependencies],
    product_id: str,
) -> ToolObservation:
    """Map existing evidence against selected official templates deterministically."""

    work = ctx.deps.state.products.get(product_id)
    extraction = work.combined_extraction() if work is not None else None
    if work is None or extraction is None:
        return ToolObservation(
            outcome="evidence_required",
            summary="Extract product evidence before mapping it.",
            count=0,
        )
    started = time.monotonic()
    request = WebsiteIngestRequest(
        url=extraction.source_url,
        template_keys=ctx.deps.state.target_submodels,
    )
    resolution = await ctx.deps.mapping_tool.resolve(extraction, request)
    work.resolution = resolution
    work.pending_reviews = ctx.deps.mapping_review.pending_deterministic_reviews(resolution)
    ctx.deps.state.products[product_id] = work
    stats = resolution.coverage_report.statistics
    ctx.deps.state.status = (
        AgentV2Status.AWAITING_REVIEW if work.pending_reviews else AgentV2Status.AWAITING_INPUT
    )
    ctx.deps.state.add_event(
        "mapping.completed",
        (
            f"Mapped {len(resolution.mapping_result.mapped)}, found "
            f"{len(resolution.mapping_result.ambiguous)} ambiguous, and retained "
            f"{len(resolution.mapping_result.unmatched_evidence_ids)} unmatched facts."
        ),
        tool_name="map_product_evidence",
        product_id=product_id,
        input_summary=f"{len(resolution.evidence)} evidence records",
        output_summary=f"{stats.required_satisfied} required requirements satisfied",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={
            "mapped": len(resolution.mapping_result.mapped),
            "ambiguous": len(resolution.mapping_result.ambiguous),
            "unmatched": len(resolution.mapping_result.unmatched_evidence_ids),
            "requiredMissing": stats.required_missing,
        },
    )
    return ToolObservation(
        outcome="mapping_complete",
        summary=(
            f"Required satisfied: {stats.required_satisfied}; required missing: "
            f"{stats.required_missing}; unmatched evidence: {stats.unmatched_evidence}."
        ),
        count=len(resolution.mapping_result.mapped),
        identifiers=(product_id,),
    )


async def research_product_sources(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    query: str,
) -> ToolObservation:
    """Find additional pages that may resolve a product's current evidence or coverage gaps."""

    work = ctx.deps.state.products.get(product_id)
    if work is None:
        return ToolObservation(
            outcome="product_required",
            summary="Select or extract a product before researching additional sources.",
            count=0,
        )
    extraction = work.combined_extraction()
    product_name = (
        work.candidate.name
        if work.candidate is not None
        else extraction.product_name
        if extraction is not None
        else product_id
    )
    domain = ctx.deps.state.selected_company.domain if ctx.deps.state.selected_company else None
    if domain is None and extraction is not None:
        domain = (urlsplit(extraction.source_url).hostname or "").removeprefix("www.").casefold()
    started = time.monotonic()
    try:
        candidates = await ctx.deps.product_research_tool.search(
            product_id=product_id,
            product_name=product_name,
            query=query,
            manufacturer_domain=domain,
        )
    except SearchUnavailableError as error:
        ctx.deps.state.add_event(
            "source.research",
            str(error),
            status=TraceStatus.FAILED,
            tool_name="research_product_sources",
            product_id=product_id,
            input_summary=query,
        )
        return ToolObservation(outcome="unavailable", summary=str(error), count=0)
    existing_urls = {item.source_url for item in work.extractions}
    work.source_candidates = tuple(item for item in candidates if item.url not in existing_urls)
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.add_event(
        "source.candidates",
        f"Found {len(work.source_candidates)} additional source candidates.",
        tool_name="research_product_sources",
        product_id=product_id,
        input_summary=query,
        output_summary=f"{len(work.source_candidates)} candidate pages",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={
            "count": len(work.source_candidates),
            "authoritative": sum(item.authoritative_domain for item in work.source_candidates),
        },
    )
    return ToolObservation(
        outcome="candidates_found" if work.source_candidates else "no_results",
        summary=(
            "Inspect a relevant authoritative candidate with extract_product_page."
            if work.source_candidates
            else "No additional source was found for this query."
        ),
        count=len(work.source_candidates),
        identifiers=tuple(item.id for item in work.source_candidates),
    )


async def inspect_unresolved_mappings(
    ctx: RunContext[MiaDependencies],
    product_id: str,
) -> SemanticContextObservation:
    """Inspect bounded unmatched evidence and allowed official targets for semantic reasoning."""

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return SemanticContextObservation(
            outcome="mapping_required",
            product_id=product_id,
            evidence=(),
            requirements=(),
        )
    context = ctx.deps.mapping_review.semantic_context(work.resolution)
    evidence = tuple(
        {
            "id": item.id,
            "label": item.source_label or item.predicate,
            "value": item.value,
            "unit": item.unit,
            "context": (item.source_location.excerpt or "")[:240],
        }
        for item in context.evidence
    )
    requirements = tuple(
        {
            "id": item.id,
            "name": item.id_short,
            "template": item.template_key,
            "path": list(item.template_path),
            "description": (item.description or "")[:360],
            "valueType": item.value_type,
            "unit": item.unit,
            "required": item.required,
        }
        for item in context.requirements
    )
    ctx.deps.state.add_event(
        "mapping.semantic_context",
        (
            f"Prepared {len(evidence)} unresolved facts and {len(requirements)} allowed "
            "official requirements."
        ),
        tool_name="inspect_unresolved_mappings",
        product_id=product_id,
        metadata={"evidence": len(evidence), "requirements": len(requirements)},
    )
    return SemanticContextObservation(
        outcome="context_ready",
        product_id=product_id,
        evidence=evidence,
        requirements=requirements,
    )


async def propose_semantic_mapping(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    evidence_id: str,
    requirement_id: str,
    reason_summary: str,
) -> ToolObservation:
    """Propose one bounded semantic match; Python validates IDs and requires human review."""

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="Run deterministic mapping before semantic proposals.",
            count=0,
        )
    if any(
        item.mapping.evidence_id == evidence_id or item.requirement_id == requirement_id
        for item in work.pending_reviews
    ):
        return ToolObservation(
            outcome="duplicate",
            summary="This evidence already has a pending semantic proposal.",
            count=0,
        )
    try:
        review = ctx.deps.mapping_review.propose(
            work.resolution,
            evidence_id=evidence_id,
            requirement_id=requirement_id,
            reason_summary=reason_summary,
        )
    except ValueError as error:
        return ToolObservation(outcome="invalid", summary=str(error), count=0)
    work.pending_reviews = (*work.pending_reviews, review)
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.status = AgentV2Status.AWAITING_REVIEW
    ctx.deps.state.add_event(
        "mapping.semantic_proposed",
        "Created a constrained semantic proposal requiring human review.",
        tool_name="propose_semantic_mapping",
        product_id=product_id,
        source_ids=(evidence_id,),
        metadata={
            "reviewId": review.id,
            "confidence": review.mapping.confidence,
            "authoritative": False,
        },
    )
    return ToolObservation(
        outcome="review_required",
        summary="The semantic proposal is validated but awaits human approval.",
        count=1,
        identifiers=(review.id,),
    )


async def review_semantic_mapping(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    review_id: str,
    decision: Literal["approve", "correct", "reject"],
    corrected_requirement_id: str | None = None,
    corrected_value: str | None = None,
) -> ToolObservation:
    """Apply a human approve/correct/reject decision to a pending semantic proposal."""

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="No mapped product exists for this review.",
            count=0,
        )
    item = next((item for item in work.pending_reviews if item.id == review_id), None)
    if item is None:
        return ToolObservation(
            outcome="invalid_review",
            summary="The review ID is not pending for this product.",
            count=0,
        )
    try:
        result, reviewed = ctx.deps.mapping_review.decide(
            work.resolution,
            item,
            decision=decision,
            thread_id=ctx.deps.state.thread_id,
            corrected_requirement_id=corrected_requirement_id,
            corrected_value=corrected_value,
        )
    except ValueError as error:
        return ToolObservation(outcome="invalid", summary=str(error), count=0)
    work.resolution = result
    work.pending_reviews = tuple(
        pending for pending in work.pending_reviews if pending.id != review_id
    )
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.status = (
        AgentV2Status.AWAITING_REVIEW if work.pending_reviews else AgentV2Status.AWAITING_INPUT
    )
    ctx.deps.state.add_event(
        "human.review_received",
        f"Human review decision recorded: {decision}.",
        tool_name="review_semantic_mapping",
        product_id=product_id,
        source_ids=(reviewed.mapping.evidence_id,),
        metadata={"reviewId": review_id, "decision": decision},
    )
    return ToolObservation(
        outcome="review_applied",
        summary="The decision was applied and source evidence was retained.",
        count=1,
        identifiers=(review_id,),
    )


async def record_human_requirement_value(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    requirement_id: str,
    value: str,
) -> ToolObservation:
    """Record a user's answer for one missing official requirement as auditable evidence."""

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="No product coverage exists for this answer.",
            count=0,
        )
    try:
        work.resolution = ctx.deps.mapping_review.record_human_value(
            work.resolution,
            requirement_id=requirement_id,
            value=value,
            thread_id=ctx.deps.state.thread_id,
        )
    except ValueError as error:
        return ToolObservation(outcome="invalid", summary=str(error), count=0)
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.add_event(
        "human.evidence_recorded",
        "Recorded a human-supplied value as provenance-aware evidence.",
        tool_name="record_human_requirement_value",
        product_id=product_id,
        metadata={"requirementId": requirement_id},
    )
    missing = sum(
        item.mandatory_missing for item in work.resolution.completion_summary.fixed_templates
    )
    ctx.deps.state.status = (
        AgentV2Status.AWAITING_INPUT if missing else AgentV2Status.READY_TO_BUILD
    )
    return ToolObservation(
        outcome="evidence_recorded",
        summary=f"The answer was validated and mapped. {missing} mandatory fields remain.",
        count=1,
        identifiers=(requirement_id,),
    )


async def build_product_aas(
    ctx: RunContext[MiaDependencies],
    product_id: str,
) -> ToolObservation:
    """Build and validate an AAS only after mandatory deterministic gates pass."""

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="Map the product evidence before building an AAS.",
            count=0,
        )
    stats = work.resolution.coverage_report.statistics
    if stats.required_missing or stats.required_candidate or stats.required_ambiguous:
        return ToolObservation(
            outcome="incomplete",
            summary=(
                "AAS build refused: mandatory target requirements remain missing or unresolved."
            ),
            count=stats.required_missing + stats.required_candidate + stats.required_ambiguous,
        )
    accepted = [
        FieldMapping(
            **mapping.model_dump(),
            id="mapping-"
            + hashlib.sha256(
                f"{mapping.evidence_id}\0{mapping.target.instance_path}".encode()
            ).hexdigest()[:24],
        )
        for mapping in work.resolution.mapping_result.mapped
        if mapping.status in {MappingStatus.AUTO, MappingStatus.APPROVED}
    ]
    package = ctx.deps.dpp_pipeline.build(
        work.resolution.knowledge_package.product_name,
        accepted,
        evidence=work.resolution.evidence,
    )
    work.aas_artifact_sha256 = package.artifact_sha256
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.status = AgentV2Status.COMPLETED
    ctx.deps.state.add_event(
        "aas.validation_completed",
        "Built and deterministically validated the AAS artifact.",
        tool_name="build_product_aas",
        product_id=product_id,
        output_summary=package.artifact_sha256,
        metadata={"deployable": package.deployable},
    )
    return ToolObservation(
        outcome="built" if package.deployable else "validation_failed",
        summary="AAS artifact built and validated.",
        count=1,
        identifiers=(package.artifact_sha256,),
    )


AGENT_TOOLS = (
    Tool(search_companies, sequential=True),
    Tool(select_company, sequential=True),
    Tool(discover_products, sequential=True),
    Tool(select_products, sequential=True),
    Tool(extract_product_page, sequential=True),
    Tool(map_product_evidence, sequential=True),
    Tool(research_product_sources, sequential=True),
    Tool(inspect_unresolved_mappings, sequential=True),
    Tool(propose_semantic_mapping, sequential=True),
    Tool(review_semantic_mapping, sequential=True),
    Tool(record_human_requirement_value, sequential=True),
    Tool(build_product_aas, sequential=True),
)
