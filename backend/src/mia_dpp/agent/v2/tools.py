"""Small model-visible tool surface over MIA's typed capabilities."""

from __future__ import annotations

import hashlib
import time

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
    work.extraction = extraction
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
    if work is None or work.extraction is None:
        return ToolObservation(
            outcome="evidence_required",
            summary="Extract product evidence before mapping it.",
            count=0,
        )
    started = time.monotonic()
    request = WebsiteIngestRequest(
        url=work.extraction.source_url,
        template_keys=ctx.deps.state.target_submodels,
    )
    resolution = await ctx.deps.mapping_tool.resolve(work.extraction, request)
    work.resolution = resolution
    review_mappings = tuple(
        item
        for item in (*resolution.mapping_result.mapped, *resolution.mapping_result.ambiguous)
        if item.status is MappingStatus.REVIEW
    )
    work.pending_reviews = ()
    ctx.deps.state.products[product_id] = work
    stats = resolution.coverage_report.statistics
    ctx.deps.state.status = (
        AgentV2Status.AWAITING_REVIEW if review_mappings else AgentV2Status.AWAITING_INPUT
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
    Tool(build_product_aas, sequential=True),
)
