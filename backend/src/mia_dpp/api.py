"""FastAPI entry point replacing the Next.js backend route."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mia_dpp.chat import demo_turn, live_turn
from mia_dpp.idta import build_dpp
from mia_dpp.models import ChatRequest, ChatResponse, DppBuildRequest, DppPackage

load_dotenv(Path(__file__).resolve().parents[3] / ".env.local")

app = FastAPI(title="MIA Digital Product Passport")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127[.]0[.]0[.]1|localhost):[0-9]+",
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Use deterministic demo mode unless an OpenRouter key is configured."""

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return demo_turn(request)
    try:
        return await live_turn(request, api_key)
    except Exception:
        return ChatResponse(
            reply=(
                "That request didn't reach the model. Check the OPENROUTER_API_KEY setting "
                "and try again — the rest of the workspace still works in demo mode."
            ),
            mode="error",
            nameplate_elements=demo_turn(ChatRequest()).nameplate_elements,
        )


@app.post("/api/dpp", response_model=DppPackage)
async def create_dpp(request: DppBuildRequest) -> DppPackage:
    """Build the current DPP JSON from accepted mappings in Python."""

    return build_dpp(request.product_name, list(request.mappings))
