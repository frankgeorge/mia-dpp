"""Canonical ASGI entrypoint for MIA."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mia_dpp import __version__
from mia_dpp.api.routes import router
from mia_dpp.bootstrap import build_application


def create_app() -> FastAPI:
    """Create the production FastAPI application.

    The ASGI server calls this entrypoint, which asks ``bootstrap`` to assemble
    MIA's concrete dependencies and then exposes them through the API routes.
    """

    application = build_application()
    app = FastAPI(
        title="MIA Digital Product Passport",
        version=__version__,
        description="Deterministic product evidence to official IDTA/AAS compilation.",
    )
    app.state.mia = application
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=application.settings.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()
