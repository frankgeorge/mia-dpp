"""FastAPI boundary for the deterministic MIA backend."""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mia_dpp import __version__
from mia_dpp.chat import demo_turn, live_turn
from mia_dpp.config import Settings
from mia_dpp.errors import MiaError
from mia_dpp.models import (
    ChatRequest,
    ChatResponse,
    DppBuildRequest,
    DppPackage,
    HealthResponse,
    TemplateSummary,
)
from mia_dpp.pipeline import build_dpp
from mia_dpp.templates import (
    STANDARDS_REPOSITORY_COMMIT,
    OfficialTemplateRepository,
    TemplateRepositoryError,
)

settings = Settings()
templates = OfficialTemplateRepository(settings.standards_root)

app = FastAPI(
    title="MIA Digital Product Passport",
    version=__version__,
    description="Deterministic product evidence to official IDTA/AAS compilation.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report readiness of both the process and its pinned standards data."""

    try:
        templates.load("digital_nameplate")
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


@app.get("/api/templates", response_model=tuple[TemplateSummary, ...])
async def template_catalog() -> tuple[TemplateSummary, ...]:
    """Expose the two pinned templates currently used to prove generic loading."""

    try:
        return tuple(templates.summary(key) for key in templates.keys())
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Use deterministic demo mode unless an OpenRouter key is configured."""

    try:
        if settings.openrouter_api_key is None:
            return demo_turn(request, templates)
        return await live_turn(
            request,
            settings.openrouter_api_key.get_secret_value(),
            templates,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ChatResponse(
            reply=(
                "The semantic proposal service failed. Your local deterministic template, "
                "review and AAS build tools remain available."
            ),
            mode="error",
            nameplate_elements=demo_turn(ChatRequest(), templates).nameplate_elements,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/dpp", response_model=DppPackage)
async def create_dpp(request: DppBuildRequest) -> DppPackage:
    """Build and validate an official-template-backed AAS environment."""

    try:
        return build_dpp(
            request.product_name,
            list(request.mappings),
            repository=templates,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except MiaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
