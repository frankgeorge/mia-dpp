"""Small model-visible tool surface over MIA's typed capabilities."""

from __future__ import annotations

import hashlib
import time
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_ai import CallDeferred, RunContext, Tool

from mia_dpp.agent.dependencies import MiaDependencies
from mia_dpp.agent.models import (
    AgentStatus,
    HumanRequest,
    HumanRequestKind,
    ProductStatus,
    ProductWork,
    TraceStatus,
)
from mia_dpp.domain.base import WireModel
from mia_dpp.domain.mappings import FieldMapping, MappingStatus
from mia_dpp.tools.search import (
    SearchUnavailableError,
    find_companies,
    find_product_sources,
    find_products,
)
from mia_dpp.workspace.models import ArtifactKind


class ToolObservation(WireModel):
    """Small typed result returned to the model after a tool action."""

    outcome: str
    summary: str
    count: int = Field(ge=0)
    identifiers: tuple[str, ...] = ()


class SemanticContextObservation(WireModel):
    """Bounded unresolved evidence and official targets shown to the model."""

    outcome: str
    product_id: str
    evidence: tuple[dict[str, object], ...]
    requirements: tuple[dict[str, object], ...]
    reviewed_knowledge: tuple[dict[str, object], ...] = ()


async def search_companies(
    ctx: RunContext[MiaDependencies],
    company_name: str,
) -> ToolObservation:
    """Find plausible company identities before product discovery.

    The agent calls this when a user's company name is not an exact identity.
    It stores structured candidates and pauses the job for selection.
    """

    extracted_products = [
        product_id for product_id, work in ctx.deps.state.products.items() if work.extractions
    ]
    if extracted_products:
        ctx.deps.add_event(
            "company.search_skipped",
            "Skipped company discovery because a direct product source is already selected.",
            tool_name="search_companies",
            input_summary=company_name,
            metadata={"extractedProducts": len(extracted_products)},
        )
        return ToolObservation(
            outcome="source_already_selected",
            summary=(
                "Do not ask for company confirmation. Continue resolving the already extracted "
                "product source."
            ),
            count=len(extracted_products),
            identifiers=tuple(extracted_products),
        )

    started = time.monotonic()
    try:
        candidates = await find_companies(ctx.deps.search, company_name)
    except SearchUnavailableError as error:
        ctx.deps.add_event(
            "company.search",
            str(error),
            status=TraceStatus.FAILED,
            tool_name="search_companies",
            input_summary=company_name,
        )
        return ToolObservation(outcome="unavailable", summary=str(error), count=0)
    ctx.deps.state.company_candidates = candidates
    ctx.deps.state.status = AgentStatus.AWAITING_COMPANY
    ctx.deps.add_event(
        "company.candidates",
        f"Found {len(candidates)} candidate companies.",
        tool_name="search_companies",
        input_summary=company_name,
        output_summary=f"{len(candidates)} structured candidates",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={"count": len(candidates)},
    )
    ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.SEARCH,
        "company-candidates.json",
        [item.model_dump(mode="json") for item in candidates],
        created_by="search_companies",
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
    """Select one company from the current trusted candidate set.

    The agent calls this after the user resolves an ambiguous identity. It saves
    the selection in ``MiaState`` and allows product discovery to continue.
    """

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
    ctx.deps.state.selected_company = candidate.model_copy(update={"identity_verified": True})
    ctx.deps.state.status = AgentStatus.RUNNING
    ctx.deps.add_event(
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
    """Discover product pages for the selected company.

    A company must already be selected. Results are restricted to its domain,
    stored as structured candidates, and normally shown for product selection.
    """

    company = ctx.deps.state.selected_company
    if company is None:
        return ToolObservation(
            outcome="company_required",
            summary="Select a company before discovering products.",
            count=0,
        )
    started = time.monotonic()
    try:
        candidates = await find_products(ctx.deps.search, company, query=query)
    except SearchUnavailableError as error:
        ctx.deps.add_event(
            "product.search",
            str(error),
            status=TraceStatus.FAILED,
            tool_name="discover_products",
            input_summary=query or company.name,
        )
        return ToolObservation(outcome="unavailable", summary=str(error), count=0)
    ctx.deps.state.product_candidates = candidates
    ctx.deps.state.status = AgentStatus.AWAITING_PRODUCT
    ctx.deps.add_event(
        "product.candidates",
        f"Found {len(candidates)} official-domain product candidates.",
        tool_name="discover_products",
        input_summary=query or "industrial products catalogue",
        output_summary=f"{len(candidates)} structured candidates",
        duration_ms=int((time.monotonic() - started) * 1000),
        metadata={"count": len(candidates)},
    )
    ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.SEARCH,
        "product-candidates.json",
        [item.model_dump(mode="json") for item in candidates],
        created_by="discover_products",
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
    """Select and queue previously discovered products for processing.

    The tool validates IDs against trusted candidates, creates each product's
    ``ProductWork``, and points the agent at the first queued product.
    """

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
    ctx.deps.state.status = AgentStatus.RUNNING
    ctx.deps.add_event(
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
    """Extract provenance-rich evidence from one product page.

    The agent calls this after identifying a useful URL. The extraction is
    appended to that product's ``ProductWork`` so further sources can be added.
    """

    normalized_url = url.rstrip("/")
    for existing_product_id, existing_work in ctx.deps.state.products.items():
        if any(
            extraction.source_url.rstrip("/") == normalized_url
            for extraction in existing_work.extractions
        ):
            ctx.deps.state.current_product_id = existing_product_id
            ctx.deps.state.status = AgentStatus.RUNNING
            next_action = (
                "Inspect the existing mapping and coverage next."
                if existing_work.resolution is not None
                else "Run deterministic mapping for this product next."
            )
            ctx.deps.add_event(
                "web.extraction_reused",
                "Reused the product source already stored in this thread.",
                tool_name="extract_product_page",
                product_id=existing_product_id,
                input_summary=url,
            )
            return ToolObservation(
                outcome="already_extracted",
                summary=next_action,
                count=len(
                    {
                        record.id
                        for extraction in existing_work.extractions
                        for record in extraction.knowledge_package.evidence
                    }
                ),
                identifiers=(existing_product_id,),
            )

    started = time.monotonic()
    extraction = await ctx.deps.web_tool.extract(url)
    source_candidate_owner = next(
        (
            existing_product_id
            for existing_product_id, existing_work in ctx.deps.state.products.items()
            if any(
                item.url.rstrip("/") == normalized_url for item in existing_work.source_candidates
            )
        ),
        None,
    )
    resolved_id = product_id or source_candidate_owner or extraction.knowledge_package.product_id
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
    work.status = ProductStatus.IN_PROGRESS
    source_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.SOURCE,
        "source.json",
        {
            "url": extraction.source_url,
            "productName": extraction.product_name,
            "sourceArtifactIds": extraction.knowledge_package.source_artifact_ids,
        },
        created_by="extract_product_page",
        product_id=resolved_id,
        source_url=extraction.source_url,
    )
    evidence_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.EVIDENCE,
        "evidence.json",
        extraction.knowledge_package.model_dump(mode="json"),
        created_by="extract_product_page",
        product_id=resolved_id,
        source_url=extraction.source_url,
        derived_from=(source_artifact.id,),
    )
    work.artifact_ids = (*work.artifact_ids, source_artifact.id, evidence_artifact.id)
    ctx.deps.state.products[resolved_id] = work
    if resolved_id not in ctx.deps.state.selected_product_ids:
        ctx.deps.state.selected_product_ids = (*ctx.deps.state.selected_product_ids, resolved_id)
    ctx.deps.state.current_product_id = resolved_id
    ctx.deps.state.status = AgentStatus.RUNNING
    evidence = extraction.knowledge_package.evidence
    ctx.deps.add_event(
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
    """Deterministically map evidence already collected for one product.

    Extraction must run first. This updates mappings, target coverage, pending
    reviews, and workflow status; unresolved evidence remains available.
    """

    work = ctx.deps.state.products.get(product_id)
    extraction = work.combined_extraction() if work is not None else None
    if work is None or extraction is None:
        return ToolObservation(
            outcome="evidence_required",
            summary="Extract product evidence before mapping it.",
            count=0,
        )
    if work.resolution is not None:
        current_evidence_ids = {item.id for item in extraction.knowledge_package.evidence}
        mapped_evidence_ids = {item.id for item in work.resolution.evidence}
        if current_evidence_ids == mapped_evidence_ids:
            resolution = work.resolution
            ctx.deps.add_event(
                "mapping.reused",
                "Reused the current deterministic mapping because no new evidence was added.",
                tool_name="map_product_evidence",
                product_id=product_id,
                metadata={"evidenceCount": len(current_evidence_ids)},
            )
            return ToolObservation(
                outcome="already_mapped",
                summary=(
                    "Do not map this evidence again. Inspect unresolved mappings, request review, "
                    "research a genuinely new source, or continue completion."
                ),
                count=len(resolution.mapping_result.mapped),
                identifiers=(product_id,),
            )
    started = time.monotonic()
    resolution = await ctx.deps.mapping_tool.resolve_package(
        extraction.knowledge_package,
        template_keys=ctx.deps.state.target_submodels,
        source_url=extraction.source_url,
        workflow_events=extraction.workflow_events,
    )
    work.resolution = resolution
    work.pending_reviews = ctx.deps.mapping_review.pending_deterministic_reviews(resolution)
    ctx.deps.state.products[product_id] = work
    mapping_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.MAPPING,
        "mapping.json",
        resolution.mapping_result.model_dump(mode="json"),
        created_by="map_product_evidence",
        product_id=product_id,
        derived_from=work.artifact_ids,
    )
    coverage_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.COVERAGE,
        "coverage.json",
        resolution.coverage_report.model_dump(mode="json"),
        created_by="map_product_evidence",
        product_id=product_id,
        derived_from=(mapping_artifact.id,),
    )
    work.artifact_ids = (*work.artifact_ids, mapping_artifact.id, coverage_artifact.id)
    stats = resolution.coverage_report.statistics
    ctx.deps.state.status = (
        AgentStatus.AWAITING_REVIEW if work.pending_reviews else AgentStatus.AWAITING_INPUT
    )
    work.status = (
        ProductStatus.AWAITING_REVIEW if work.pending_reviews else ProductStatus.IN_PROGRESS
    )
    ctx.deps.state.products[product_id] = work
    ctx.deps.add_event(
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
    """Find additional sources for an identified product.

    The agent uses this after extraction or coverage reveals a gap. Candidate
    pages are stored in ``ProductWork`` for a later extraction tool call.
    """

    work = ctx.deps.state.products.get(product_id)
    if work is None:
        return ToolObservation(
            outcome="product_required",
            summary="Select or extract a product before researching additional sources.",
            count=0,
        )
    if work.pending_reviews:
        return ToolObservation(
            outcome="source_review_required",
            summary=(
                "Request human review for the existing semantic proposals before researching "
                "additional sources."
            ),
            count=len(work.pending_reviews),
            identifiers=tuple(item.id for item in work.pending_reviews),
        )
    extraction = work.combined_extraction()
    product_name = (
        work.candidate.name
        if work.candidate is not None
        else extraction.product_name
        if extraction is not None
        else product_id
    )
    company = ctx.deps.state.selected_company
    domain = company.domain if company is not None and company.identity_verified else None
    if domain is None and extraction is not None:
        domain = (urlsplit(extraction.source_url).hostname or "").removeprefix("www.").casefold()
    started = time.monotonic()
    try:
        candidates = await find_product_sources(
            ctx.deps.search,
            product_id=product_id,
            product_name=product_name,
            query=query,
            manufacturer_domain=domain,
        )
    except SearchUnavailableError as error:
        ctx.deps.add_event(
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
    ctx.deps.add_event(
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
    """Prepare bounded inputs for semantic mapping.

    Deterministic mapping must already exist. The model receives only unmatched
    evidence and unresolved official requirements, not the whole source page.
    """

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return SemanticContextObservation(
            outcome="mapping_required",
            product_id=product_id,
            evidence=(),
            requirements=(),
            reviewed_knowledge=(),
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
    company = ctx.deps.state.selected_company
    knowledge = tuple(
        {
            "sourceField": item.source_field,
            "targetTemplate": item.target_template,
            "targetPath": list(item.target_path),
            "semanticId": item.semantic_id,
            "confirmations": item.confirmations,
            "humanComments": list(item.human_comments),
        }
        for record in context.evidence
        for item in ctx.deps.mapping_knowledge.relevant(
            record.source_label or record.predicate,
            manufacturer=company.name if company else None,
            domain=company.domain if company else None,
            template_keys=ctx.deps.state.target_submodels,
        )
    )
    ctx.deps.add_event(
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
        reviewed_knowledge=knowledge,
    )


async def propose_semantic_mapping(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    evidence_id: str,
    requirement_id: str,
    reason_summary: str,
) -> ToolObservation:
    """Propose one semantic match between allowed evidence and target IDs.

    Python validates both IDs, calculates confidence, and stores the proposal as
    a pending review. The proposal cannot become authoritative by model choice.
    """

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
    company = ctx.deps.state.selected_company
    ctx.deps.mapping_knowledge.remember_candidate(
        review.mapping,
        manufacturer=company.name if company else None,
        domain=company.domain if company else None,
        product_family=work.candidate.family if work.candidate else None,
    )
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.status = AgentStatus.AWAITING_REVIEW
    ctx.deps.add_event(
        "mapping.semantic_proposed",
        "Created a constrained semantic proposal requiring human review.",
        tool_name="propose_semantic_mapping",
        product_id=product_id,
        source_ids=(evidence_id,),
        metadata={
            "reviewId": review.id,
            "basis": review.mapping.assessment.basis.value,
            "reviewRequired": review.mapping.assessment.review_required,
            "authoritative": False,
        },
    )
    return ToolObservation(
        outcome="review_required",
        summary="The semantic proposal is validated but awaits human approval.",
        count=1,
        identifiers=(review.id,),
    )


async def request_human_review(
    ctx: RunContext[MiaDependencies],
    product_id: str,
) -> ToolObservation:
    """Pause for trusted human decisions on the product's pending proposals.

    This tool can only request input. Approval, correction, and rejection are
    applied by the LangGraph resume path after an authenticated API action.
    """

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="No mapped product exists for this review.",
            count=0,
        )
    if not work.pending_reviews:
        return ToolObservation(
            outcome="nothing_pending",
            summary="No mapping proposal currently needs human review.",
            count=0,
        )
    ctx.deps.state.pending_human_request = HumanRequest(
        kind=HumanRequestKind.MAPPING_REVIEW,
        product_id=product_id,
        summary=f"{len(work.pending_reviews)} mapping proposals need a human decision.",
    )
    work.status = ProductStatus.AWAITING_REVIEW
    ctx.deps.state.products[product_id] = work
    ctx.deps.state.status = AgentStatus.AWAITING_REVIEW
    ctx.deps.add_event(
        "human.input_requested",
        "Requested trusted human review for semantic mappings.",
        tool_name="request_human_review",
        product_id=product_id,
        metadata={"count": len(work.pending_reviews)},
    )
    raise CallDeferred


async def request_human_value(
    ctx: RunContext[MiaDependencies],
    product_id: str,
    requirement_id: str,
    question: str,
) -> ToolObservation:
    """Pause for a value that public evidence and deterministic mapping could not supply.

    The tool validates that the target is genuinely missing but cannot create
    human evidence. Only the trusted API resume action may record the answer.
    """

    work = ctx.deps.state.products.get(product_id)
    if work is None or work.resolution is None:
        return ToolObservation(
            outcome="mapping_required",
            summary="No product coverage exists for this answer.",
            count=0,
        )
    if work.pending_reviews:
        return ToolObservation(
            outcome="source_review_required",
            summary=(
                "Resolve the pending source-derived mapping reviews before asking for missing "
                "requirement values."
            ),
            count=len(work.pending_reviews),
            identifiers=tuple(item.id for item in work.pending_reviews),
        )
    if ctx.deps.state.pending_human_request is not None:
        return ToolObservation(
            outcome="human_input_already_requested",
            summary="Wait for the existing trusted human request instead of creating another one.",
            count=1,
            identifiers=(ctx.deps.state.pending_human_request.product_id,),
        )
    missing = {
        item.requirement_id
        for item in work.resolution.coverage_report.coverage
        if item.status.value == "missing"
    }
    if requirement_id not in missing:
        return ToolObservation(
            outcome="invalid",
            summary="The requested requirement is not currently missing.",
            count=0,
        )
    ctx.deps.state.pending_human_request = HumanRequest(
        kind=HumanRequestKind.REQUIREMENT_VALUE,
        product_id=product_id,
        requirement_id=requirement_id,
        summary=question,
    )
    ctx.deps.state.status = AgentStatus.AWAITING_INPUT
    ctx.deps.add_event(
        "human.input_requested",
        question,
        tool_name="request_human_value",
        product_id=product_id,
        metadata={"requirementId": requirement_id},
    )
    raise CallDeferred


async def build_product_aas(
    ctx: RunContext[MiaDependencies],
    product_id: str,
) -> ToolObservation:
    """Build and validate the product AAS after deterministic readiness checks.

    Mapping and coverage must already exist without unresolved mandatory fields.
    The AAS pipeline remains authoritative and stores the resulting artifact ID.
    """

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
    aas_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.AAS,
        "aas.json",
        package.environment,
        created_by="build_product_aas",
        product_id=product_id,
        derived_from=work.artifact_ids,
    )
    validation_artifact = ctx.deps.workspace.write_json(
        ctx.deps.state.thread_id,
        ArtifactKind.VALIDATION,
        "validation.json",
        package.validation_report.model_dump(mode="json"),
        created_by="build_product_aas",
        product_id=product_id,
        derived_from=(aas_artifact.id,),
    )
    work.artifact_ids = (*work.artifact_ids, aas_artifact.id, validation_artifact.id)
    work.status = ProductStatus.COMPLETED if package.deployable else ProductStatus.FAILED
    ctx.deps.state.products[product_id] = work
    remaining = tuple(item for item in ctx.deps.state.product_queue if item != product_id)
    ctx.deps.state.product_queue = remaining
    ctx.deps.state.current_product_id = remaining[0] if remaining else product_id
    ctx.deps.state.status = (
        AgentStatus.COMPLETED
        if all(
            item.status in {ProductStatus.COMPLETED, ProductStatus.FAILED}
            for item in ctx.deps.state.products.values()
        )
        else AgentStatus.RUNNING
    )
    ctx.deps.add_event(
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
    Tool(request_human_review, sequential=True),
    Tool(request_human_value, sequential=True),
    Tool(build_product_aas, sequential=True),
)
