"""FastAPI routes translating HTTP requests into MIA capabilities."""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request

from mia_dpp import __version__
from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.models import DppPackage
from mia_dpp.aas.templates import (
    STANDARDS_REPOSITORY_COMMIT,
    TemplateRepositoryError,
)
from mia_dpp.agent.models import AgentMessageRequest, AgentResponse, AgentReviewRequest
from mia_dpp.api.schemas import (
    DppBuildRequest,
    HealthResponse,
)
from mia_dpp.bootstrap import Application
from mia_dpp.chat import demo_turn, live_turn
from mia_dpp.domain.targets import TemplateSummary
from mia_dpp.errors import ExtractionError, MiaError
from mia_dpp.llm.chat import ChatRequest, ChatResponse
from mia_dpp.resolution.models import WebsiteIngestRequest, WebsiteIngestResponse
from mia_dpp.tools.web.models import (
    ExtractionDependencyError,
    PageLoadError,
    ProductUrlRejectedError,
)

router = APIRouter()


def _application(request: Request) -> Application:
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


@router.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, http_request: Request) -> ChatResponse:
    """Use deterministic demo mode unless an OpenRouter key is configured."""

    try:
        application = _application(http_request)
        if application.settings.openrouter_api_key is None:
            return demo_turn(payload, application.templates)
        return await live_turn(
            payload,
            application.settings.openrouter_api_key.get_secret_value(),
            application.templates,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ChatResponse(
            reply=(
                "The semantic proposal service failed. Your local deterministic template, "
                "review and AAS build tools remain available."
            ),
            mode="error",
            nameplate_elements=demo_turn(ChatRequest(), application.templates).nameplate_elements,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/api/agent/messages", response_model=AgentResponse)
async def agent_message(payload: AgentMessageRequest, http_request: Request) -> AgentResponse:
    """Run or continue one conversational MIA workflow thread."""

    try:
        return await _application(http_request).agent_workflow.message(payload)
    except ProductUrlRejectedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExtractionDependencyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PageLoadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"agent reasoning failed: {error}") from error
    except ExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/api/agent/review", response_model=AgentResponse)
async def agent_review(payload: AgentReviewRequest, http_request: Request) -> AgentResponse:
    """Resume a paused workflow with explicit human semantic decisions."""

    try:
        return await _application(http_request).agent_workflow.review(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"review could not be applied: {error}",
        ) from error


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


@router.post("/api/website", response_model=WebsiteIngestResponse)
async def ingest_website(
    payload: WebsiteIngestRequest, http_request: Request
) -> WebsiteIngestResponse:
    """Fetch a public product page with Crawl4AI and propose reviewed mappings."""

    try:
        return await _application(http_request).website_workflow.ingest(payload)
    except ProductUrlRejectedError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ExtractionDependencyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PageLoadError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ExtractionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
