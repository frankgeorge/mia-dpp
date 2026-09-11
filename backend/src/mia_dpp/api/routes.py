"""FastAPI routes translating HTTP requests into MIA capabilities."""

from __future__ import annotations

import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mia_dpp import __version__
from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.models import DppPackage
from mia_dpp.aas.templates import (
    STANDARDS_REPOSITORY_COMMIT,
    TemplateRepositoryError,
)
from mia_dpp.api.schemas import (
    AgentMessageRequest,
    AgentResponse,
    AgentReviewRequest,
    ChatRequest,
    ChatResponse,
    DppBuildRequest,
    HealthResponse,
    WebsiteIngestRequest,
    WebsiteIngestResponse,
)
from mia_dpp.bootstrap import build_application
from mia_dpp.chat import demo_turn, live_turn
from mia_dpp.domain.targets import TemplateSummary
from mia_dpp.errors import ExtractionError, MiaError
from mia_dpp.sources.extraction import (
    ExtractionDependencyError,
    PageLoadError,
    ProductUrlRejectedError,
)

application = build_application()
settings = application.settings
templates = application.templates
website_ingestion = application.website_ingestion
reasoning = application.reasoning
agent_workflow = application.agent_workflow

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


@app.post("/api/agent/messages", response_model=AgentResponse)
async def agent_message(request: AgentMessageRequest) -> AgentResponse:
    """Run or continue one conversational MIA workflow thread."""

    try:
        import mia_dpp.api as api_package

        workflow = getattr(api_package, "agent_workflow", agent_workflow)
        return await workflow.message(request)
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


@app.post("/api/agent/review", response_model=AgentResponse)
async def agent_review(request: AgentReviewRequest) -> AgentResponse:
    """Resume a paused workflow with explicit human semantic decisions."""

    try:
        return await agent_workflow.review(request)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"review could not be applied: {error}",
        ) from error


@app.post("/api/dpp", response_model=DppPackage)
async def create_dpp(request: DppBuildRequest) -> DppPackage:
    """Build and validate an official-template-backed AAS environment."""

    try:
        return build_dpp(
            request.product_name,
            list(request.mappings),
            repository=templates,
            evidence=request.evidence,
        )
    except TemplateRepositoryError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except MiaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/website", response_model=WebsiteIngestResponse)
async def ingest_website(request: WebsiteIngestRequest) -> WebsiteIngestResponse:
    """Fetch a public product page with Crawl4AI and propose reviewed mappings."""

    try:
        import mia_dpp.api as api_package

        ingestion = getattr(api_package, "website_ingestion", website_ingestion)
        return await ingestion.ingest(request)
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
