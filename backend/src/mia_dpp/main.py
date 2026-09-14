"""Canonical ASGI entrypoint for MIA."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mia_dpp import __version__
from mia_dpp.api.routes import router
from mia_dpp.mia import Mia


def create_app(mia: Mia | None = None) -> FastAPI:
    """Create the production FastAPI application.

    The ASGI server calls this entrypoint. ``Mia`` assembles and orchestrates
    the application; this function only exposes it through FastAPI routes.
    """

    application = mia or Mia()
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
