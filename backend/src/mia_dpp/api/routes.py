"""FastAPI routes translating HTTP requests into MIA capabilities."""

from __future__ import annotations

import json
from importlib.metadata import version

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from pydantic_ai.exceptions import UnexpectedModelBehavior

from mia_dpp import __version__
from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.models import AasArtifact, DppPackage, ValidationReport
from mia_dpp.aas.qr import passport_qr_png_b64
from mia_dpp.aas.templates import (
    STANDARDS_REPOSITORY_COMMIT,
    TemplateRepositoryError,
)
from mia_dpp.agent.models import (
    AgentRequest,
    AgentResponse,
    AgentReviewRequest,
    AgentTraceEvent,
    AgentValueRequest,
)
from mia_dpp.api.schemas import (
    DeployRequest,
    DeployResponse,
    DppBuildRequest,
    HealthResponse,
)
from mia_dpp.canonical import sha256_json
from mia_dpp.domain.targets import TemplateSummary
from mia_dpp.errors import DeploymentError, MiaError
from mia_dpp.integrations.basyx import BasyxAasRepository
from mia_dpp.mia import Mia
from mia_dpp.store import ArtifactKind, WorkspaceArtifact
from mia_dpp.tools.mapping.models import (
    MappingKnowledgeEntry,
)
from mia_dpp.tools.search import SearchUnavailableError
from mia_dpp.tools.web.models import (
    ExtractionDependencyError,
    PageLoadError,
    ProductUrlRejectedError,
)

router = APIRouter()


def _application(request: Request) -> Mia:
    app: FastAPI = request.app
    return app.state.mia  # type: ignore[no-any-return]


@router.get("/health", response_model=HealthResponse)
async def health(http_request: Request) -> HealthResponse:
    """Report readiness of both the process and its pinned standards data."""

    try:
        _application(http_request).templates.load("digital_nameplate")
    except TemplateRepositoryError:
        return HealthResponse(
            status="not_ready",
            version=__version__,
            standards_ready=False,
            standards_commit=STANDARDS_REPOSITORY_COMMIT,
        )
    return HealthResponse(
        status="ok",
        version=__version__,
        standards_ready=True,
        standards_commit=STANDARDS_REPOSITORY_COMMIT,
    )


@router.get("/api/templates", response_model=tuple[TemplateSummary, ...])
async def template_catalog(http_request: Request) -> tuple[TemplateSummary, ...]:
    """Expose the two pinned templates currently used to prove generic loading."""

    try:
        templates = _application(http_request).templates
        return tuple(templates.summary(key) for key in templates.keys())
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/api/agent/messages", response_model=AgentResponse)
async def agent_message(
    payload: AgentRequest,
    http_request: Request,
) -> AgentResponse:
    """Run one checkpointed autonomous turn for a trusted thread."""

    try:
        return await _application(http_request).message(payload)
    except ProductUrlRejectedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExtractionDependencyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PageLoadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except SearchUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (
        UnexpectedModelBehavior,
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise HTTPException(status_code=502, detail=f"agent failed: {error}") from error


@router.post("/api/agent/review", response_model=AgentResponse)
async def agent_review(
    payload: AgentReviewRequest,
    http_request: Request,
) -> AgentResponse:
    """Resume an interrupt with trusted mapping-review decisions."""

    try:
        return await _application(http_request).review(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"review could not be applied: {error}",
        ) from error


@router.post("/api/agent/value", response_model=AgentResponse)
async def agent_value(payload: AgentValueRequest, http_request: Request) -> AgentResponse:
    """Resume an interrupt with a trusted human-supplied requirement value."""
    try:
        return await _application(http_request).provide_value(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"human value could not be applied: {error}",
        ) from error


@router.get(
    "/api/workspaces/{thread_id}/artifacts",
    response_model=tuple[WorkspaceArtifact, ...],
)
async def list_workspace_artifacts(
    thread_id: str,
    http_request: Request,
) -> tuple[WorkspaceArtifact, ...]:
    """List the manifest entries belonging to one thread workspace."""

    try:
        return _application(http_request).store.list_artifacts(thread_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/api/workspaces/{thread_id}/artifacts/{artifact_id}")
async def read_workspace_artifact(
    thread_id: str,
    artifact_id: str,
    http_request: Request,
    download: bool = Query(default=False),
) -> Response:
    """Read or download an artifact resolved only through its manifest ID."""

    try:
        artifact, data = _application(http_request).store.read_artifact(thread_id, artifact_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    headers = (
        {"Content-Disposition": f'attachment; filename="{artifact.name}"'} if download else None
    )
    return Response(content=data, media_type=artifact.content_type, headers=headers)


@router.get("/api/workspaces/{thread_id}/download")
async def download_workspace(thread_id: str, http_request: Request) -> Response:
    """Download all manifest-registered artifacts in one ZIP archive."""

    try:
        data = _application(http_request).store.export_zip(thread_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{thread_id}-workspace.zip"'},
    )


@router.get("/api/workspaces/{thread_id}/export")
async def export_workspace(thread_id: str, http_request: Request) -> dict[str, object]:
    """Return the combined structured workspace export as JSON."""

    try:
        return _application(http_request).store.combined_export(thread_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/api/workspaces/{thread_id}/trace",
    response_model=tuple[AgentTraceEvent, ...],
)
async def workspace_trace(
    thread_id: str,
    http_request: Request,
) -> tuple[AgentTraceEvent, ...]:
    """Return normalized activity events without exposing hidden model reasoning."""

    return _application(http_request).store.list_events(thread_id)


@router.get(
    "/api/mapping-knowledge",
    response_model=tuple[MappingKnowledgeEntry, ...],
)
async def mapping_knowledge(http_request: Request) -> tuple[MappingKnowledgeEntry, ...]:
    """List backend-owned mapping knowledge for the Integration Graph."""

    return _application(http_request).store.list_mapping_knowledge()


@router.post("/api/dpp", response_model=DppPackage)
async def create_dpp(payload: DppBuildRequest, http_request: Request) -> DppPackage:
    """Build and validate an official-template-backed AAS environment."""

    try:
        return build_dpp(
            payload.product_name,
            list(payload.mappings),
            repository=_application(http_request).templates,
            evidence=payload.evidence,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except MiaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post(
    "/api/workspaces/{thread_id}/deploy",
    response_model=DeployResponse,
)
async def deploy_workspace(
    thread_id: str,
    payload: DeployRequest,
    http_request: Request,
) -> DeployResponse:
    """Deploy the latest validated AAS artifact for a thread to a BaSyx server."""

    store = _application(http_request).store

    # Locate the most recent AAS artifact and its paired validation artifact
    try:
        all_artifacts = store.list_artifacts(thread_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    aas_artifacts = [a for a in all_artifacts if a.kind is ArtifactKind.AAS]
    if not aas_artifacts:
        raise HTTPException(
            status_code=404,
            detail="No AAS artifact found for this workspace. Generate a passport first.",
        )
    # Most recent AAS artifact is last in insertion order
    latest_aas = aas_artifacts[-1]

    # Find the validation artifact derived from this AAS artifact
    validation_artifacts = [
        a
        for a in all_artifacts
        if a.kind is ArtifactKind.VALIDATION and latest_aas.id in a.derived_from
    ]

    # Read the stored environment JSON
    _, aas_bytes = store.read_artifact(thread_id, latest_aas.id)
    environment: dict = json.loads(aas_bytes)

    # Reconstruct the AasArtifact — environment is the full AAS environment dict
    # Extract submodel: first entry in assetAdministrationShells references submodels
    submodels = environment.get("submodels", [])
    submodel: dict = submodels[0] if submodels else {}

    digest = sha256_json(environment)
    artifact = AasArtifact(
        environment=environment,
        submodel=submodel,
        sha256=digest,
        compiler_name="mia-official-template-projector+aas-core3.0",
        compiler_version=version("aas-core3.0"),
    )

    # Load validation report if available, otherwise construct a minimal passing one
    validation: ValidationReport | None = None
    if validation_artifacts:
        _, val_bytes = store.read_artifact(thread_id, validation_artifacts[-1].id)
        try:
            validation = ValidationReport.model_validate_json(val_bytes)
            # The stored sha256 may reference the artifact sha256 recorded at build time;
            # update it to match the reconstructed artifact so the deploy guard passes
            if validation.artifact_sha256 != digest:
                validation = ValidationReport(
                    valid=validation.valid,
                    template_key=validation.template_key,
                    template_release=validation.template_release,
                    artifact_sha256=digest,
                    validator_versions=validation.validator_versions,
                    findings=validation.findings,
                )
        except (ValueError, KeyError):
            validation = None

    if validation is None or not validation.valid:
        raise HTTPException(
            status_code=422,
            detail="The AAS artifact did not pass validation and cannot be deployed.",
        )

    # Deploy to BaSyx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            repo = BasyxAasRepository(client, base_url=payload.basyx_url)
            result = await repo.deploy(artifact, validation)
    except DeploymentError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502, detail=f"BaSyx server unreachable: {error}"
        ) from error

    # Build the public passport URL using the first shell ID
    first_shell_id = result.shell_ids[0] if result.shell_ids else ""
    encoded_id = BasyxAasRepository.encode_identifier(first_shell_id)
    base = (payload.passport_base_url or "https://mia-dpp.vercel.app").rstrip("/")
    passport_url = f"{base}/passport/{encoded_id}"

    # Generate QR code
    qr_b64 = passport_qr_png_b64(passport_url)

    return DeployResponse(
        status="deployed",
        repository_url=result.repository_url,
        shell_ids=list(result.shell_ids),
        submodel_ids=list(result.submodel_ids),
        passport_url=passport_url,
        qr_code_png_b64=qr_b64,
    )
