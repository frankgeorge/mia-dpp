"""FastAPI routes translating HTTP requests into MIA capabilities."""

from __future__ import annotations

import hashlib
import json
import uuid
from importlib.metadata import version

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from pydantic_ai.exceptions import UnexpectedModelBehavior

from mia_dpp import __version__
from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.models import AasArtifact, DppPackage, ValidationReport
from mia_dpp.aas.qr import passport_qr_png_b64
from mia_dpp.aas.requirements import build_template_index
from mia_dpp.aas.templates import (
    STANDARDS_REPOSITORY_COMMIT,
    TemplateRepositoryError,
)
from mia_dpp.agent.models import (
    AgentRequest,
    AgentResponse,
    AgentTraceEvent,
)
from mia_dpp.api.schemas import (
    DeployRequest,
    DeployResponse,
    DppBuildRequest,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
)
from mia_dpp.canonical import sha256_json
from mia_dpp.domain.mappings import (
    FieldMapping,
    MappingAssessment,
    MappingBasis,
    MappingOrigin,
    MappingStatus,
    MappingTarget,
)
from mia_dpp.domain.targets import RequirementKind, TemplateSummary
from mia_dpp.errors import DeploymentError, MiaError
from mia_dpp.integrations.basyx import BasyxAasRepository
from mia_dpp.mia import Mia
from mia_dpp.store import ArtifactKind, WorkspaceArtifact
from mia_dpp.tools.mapping.models import (
    MappingKnowledgeEntry,
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
    """Expose the pinned templates currently used."""

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
    """Run one document-extraction agent turn for a trusted thread."""

    try:
        return await _application(http_request).message(payload)
    except (
        UnexpectedModelBehavior,
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise HTTPException(status_code=502, detail=f"agent failed: {error}") from error


@router.post("/api/agent/generate", response_model=GenerateResponse)
async def generate_from_fields(
    payload: GenerateRequest,
    http_request: Request,
) -> GenerateResponse:
    """Build a DPP from simple extracted fields — no FieldMapping objects required.

    Converts {idta_field: value} pairs to proper FieldMapping objects by looking up
    each field name in the IDTA 02006 Digital Nameplate template requirements.
    """

    try:
        templates = _application(http_request).templates
        template = templates.load("digital_nameplate")
        index = build_template_index([template])
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    # Build requirements index by id_short for fast lookup
    req_by_id_short = {
        req.id_short: req
        for req in index.requirements
        if req.id_short and req.kind is RequirementKind.VALUE and req.semantic_id is not None
    }

    # Convert simple {field: value} dict to FieldMapping objects
    mappings: list[FieldMapping] = []
    for field_name, raw_value in payload.fields.items():
        value = str(raw_value).strip()
        if not value:
            continue
        req = req_by_id_short.get(field_name)
        if req is None or req.semantic_id is None:
            continue

        field_hash = hashlib.sha256(f"{field_name}:{value}".encode()).hexdigest()
        evidence_id = f"doc-{field_hash[:24]}"
        mapping_id = f"map-{field_hash[24:48]}"

        mappings.append(
            FieldMapping(
                id=mapping_id,
                evidence_id=evidence_id,
                source_field=field_name,
                source_value=value,
                target=MappingTarget(
                    template_key=req.template_key,
                    template_release=req.template_release,
                    template_path=req.template_path,
                    instance_path=req.template_path,
                    id_short=req.id_short,
                    semantic_id=req.semantic_id,
                ),
                assessment=MappingAssessment(
                    basis=MappingBasis.HUMAN,
                    review_required=False,
                    reason="Extracted from uploaded document by MIA",
                ),
                reasoning="Agent extracted this field from the document text.",
                status=MappingStatus.AUTO,
                mapping_origin=MappingOrigin.HUMAN,
                human_reviewed=False,
            )
        )

    if not mappings:
        raise HTTPException(
            status_code=422,
            detail="No fields matched IDTA 02006 template requirements. "
            "Ensure field names match exactly (e.g. ManufacturerName, Street).",
        )

    try:
        package = build_dpp(
            payload.product_name,
            mappings,
            repository=_application(http_request).templates,
            evidence=(),
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except MiaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    thread_id = payload.thread_id or f"thread-{uuid.uuid4().hex}"
    store = _application(http_request).store

    # Persist AAS + validation artifacts
    try:
        aas_artifact = store.write_json(
            thread_id,
            ArtifactKind.AAS,
            "aas.json",
            package.environment,
            created_by="generate_from_fields",
        )
        store.write_json(
            thread_id,
            ArtifactKind.VALIDATION,
            "validation.json",
            package.validation_report.model_dump(mode="json"),
            created_by="generate_from_fields",
            derived_from=(aas_artifact.id,),
        )
    except (ValueError, OSError):
        pass  # Non-blocking

    return GenerateResponse(
        thread_id=thread_id,
        passport_id=package.passport_id,
        artifact_sha256=package.artifact_sha256,
        deployable=package.deployable,
        validation_valid=package.validation_report.valid,
        dpp_json=package.environment,
    )


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
        package = build_dpp(
            payload.product_name,
            list(payload.mappings),
            repository=_application(http_request).templates,
            evidence=payload.evidence,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except MiaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # Persist AAS + validation artifacts so the deploy endpoint can find them
    if payload.thread_id:
        store = _application(http_request).store
        try:
            aas_artifact = store.write_json(
                payload.thread_id,
                ArtifactKind.AAS,
                "aas.json",
                package.environment,
                created_by="manual_generate",
            )
            store.write_json(
                payload.thread_id,
                ArtifactKind.VALIDATION,
                "validation.json",
                package.validation_report.model_dump(mode="json"),
                created_by="manual_generate",
                derived_from=(aas_artifact.id,),
            )
        except (ValueError, OSError):
            pass  # Non-blocking

    return package


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
    latest_aas = aas_artifacts[-1]

    validation_artifacts = [
        a
        for a in all_artifacts
        if a.kind is ArtifactKind.VALIDATION and latest_aas.id in a.derived_from
    ]

    _, aas_bytes = store.read_artifact(thread_id, latest_aas.id)
    environment: dict = json.loads(aas_bytes)

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

    validation: ValidationReport | None = None
    if validation_artifacts:
        _, val_bytes = store.read_artifact(thread_id, validation_artifacts[-1].id)
        try:
            validation = ValidationReport.model_validate_json(val_bytes)
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

    # Store the AAS in Supabase via passport registry — no external BaSyx dependency
    base = (payload.passport_base_url or "https://mia-dpp.vercel.app").rstrip("/")
    passport_url = f"{base}/passport/{thread_id}"
    qr_b64 = passport_qr_png_b64(passport_url)

    return DeployResponse(
        status="deployed",
        repository_url=base,
        shell_ids=[thread_id],
        submodel_ids=[],
        passport_url=passport_url,
        qr_code_png_b64=qr_b64,
        aas_json=environment,
    )
