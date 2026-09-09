"""Python implementation of the existing chat endpoint behavior."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from mia_dpp.idta import NAMEPLATE_ELEMENTS, demo_propose, semantic_id_for
from mia_dpp.models import (
    ChatRequest,
    ChatResponse,
    MappingProposal,
    MappingStatus,
    ProposedFieldMapping,
)

MODEL = "deepseek/deepseek-chat-v3-0324"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CONFIDENCE_THRESHOLD = 0.85


def _catalog() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "name": element.name,
            "semanticId": element.semantic_id,
            "hint": element.hint,
            "required": element.required,
        }
        for element in NAMEPLATE_ELEMENTS
    )


def _status(confidence: float) -> MappingStatus:
    return (
        MappingStatus.AUTO
        if confidence >= CONFIDENCE_THRESHOLD
        else MappingStatus.REVIEW
    )


def _clamp(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def demo_turn(request: ChatRequest) -> ChatResponse:
    """Run the current no-key chat behavior without external services."""

    text = request.messages[-1].content if request.messages else ""
    wants_generate = bool(
        re.search(
            r"\b(generate|build|create|export|make)\b.*\b(dpp|passport|package|aasx)\b",
            text,
            re.IGNORECASE,
        )
        or re.search(
            r"^(generate|export|build it|do it|yes)\b",
            text.strip(),
            re.IGNORECASE,
        )
    )
    looks_like_product = len(text.strip()) > 12 and bool(
        re.search(
            r"\d|model|typ|serial|ip\d|bar|product|gauge|clamp|table|sensor|valve",
            text,
            re.IGNORECASE,
        )
    )

    if wants_generate and not looks_like_product:
        return ChatResponse(
            reply="Building the passport from your approved mappings.",
            generate=True,
            mode="demo",
            nameplate_elements=_catalog(),
        )

    if not looks_like_product:
        return ChatResponse(
            reply=(
                "Describe the product and I'll map it — manufacturer, model, serial number, "
                "year, plant, and any technical values you have. Or press one of the sample "
                "products above."
            ),
            mode="demo",
            nameplate_elements=_catalog(),
        )

    draft = demo_propose(text)
    mappings: list[ProposedFieldMapping] = []
    for mapping in draft.mappings:
        graph_match = next(
            (
                entry
                for entry in request.graph
                if entry.source_field.casefold() == mapping.source_field.casefold()
                and entry.target_element == mapping.target_element
            ),
            None,
        )
        if graph_match:
            confidence = min(0.99, mapping.confidence + 0.22)
            reasoning = (
                "Verified on an earlier product, so this is reused from the Integration "
                f"Graph. {mapping.reasoning}"
            )
            from_graph = True
        else:
            confidence = mapping.confidence
            reasoning = mapping.reasoning
            from_graph = False
        mappings.append(
            ProposedFieldMapping(
                **mapping.model_dump(exclude={"confidence", "reasoning", "from_graph"}),
                confidence=confidence,
                reasoning=reasoning,
                from_graph=from_graph,
                status=_status(confidence),
            )
        )

    low = sum(mapping.confidence < CONFIDENCE_THRESHOLD for mapping in mappings)
    reused = sum(mapping.from_graph for mapping in mappings)
    reply = f"Found {len(mappings)} field{'s' if len(mappings) != 1 else ''} in that description."
    if reused:
        reply += f" {reused} came straight from the Integration Graph."
    if low:
        verb = "is" if low == 1 else "are"
        need = "needs" if low == 1 else "need"
        reply += f" {low} {verb} below the confidence line and {need} your decision."
    else:
        reply += " All of them cleared the confidence line."

    return ChatResponse(
        reply=reply,
        proposal=MappingProposal(product_name=draft.product_name, mappings=tuple(mappings)),
        mode="demo",
        nameplate_elements=_catalog(),
    )


def _system_prompt() -> str:
    elements = "\n".join(
        f"- {item.name}{' (required)' if item.required else ''} — {item.hint}"
        for item in NAMEPLATE_ELEMENTS
    )
    return "\n".join(
        (
            "You are MIA, an integration agent that turns a manufacturer's messy product "
            "data into a standards-compliant Digital Product Passport.",
            "",
            "You map source fields onto the IDTA Digital Nameplate submodel. These are "
            "the only valid target elements:",
            "",
            elements,
            "",
            "Rules you must follow:",
            "1. When the user describes a product, call propose_mappings once with every "
            "field you can identify.",
            "2. Give each mapping an honest confidence between 0 and 1. Be genuinely "
            "uncertain when the evidence is weak — a guessed field at 0.55 is far more useful "
            "than a false 0.95. Reserve above 0.9 for cases where the label is explicit and "
            "unambiguous.",
            "3. sourceField should be the field name as it would appear in a German "
            "manufacturer's SAP system (WERKS, MATNR, SERNR, BAUJAHR, NAME1, LAND1) when "
            "you can infer it, otherwise a plain descriptive name.",
            "4. Never invent values the user did not provide. Missing data is a gap to "
            "report, not to fill.",
            "5. After proposing, tell the user in one or two short sentences what you mapped "
            "and what still needs their decision. Do not repeat the whole table back — the "
            "interface already shows it.",
            "6. Only call generate_dpp when the user explicitly asks to generate, build, "
            "or export the passport.",
            "",
            "Be brief and concrete. You are a working tool, not a chatbot.",
        )
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_mappings",
            "description": (
                "Propose field mappings from product data onto the IDTA Digital Nameplate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "productName": {"type": "string"},
                    "mappings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sourceField": {"type": "string"},
                                "sourceValue": {"type": "string"},
                                "targetElement": {"type": "string"},
                                "confidence": {"type": "number"},
                                "reasoning": {"type": "string"},
                            },
                            "required": [
                                "sourceField",
                                "sourceValue",
                                "targetElement",
                                "confidence",
                                "reasoning",
                            ],
                        },
                    },
                },
                "required": ["productName", "mappings"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_dpp",
            "description": "Assemble the DPP from mappings the user has approved.",
            "parameters": {
                "type": "object",
                "properties": {"confirm": {"type": "boolean"}},
                "required": ["confirm"],
            },
        },
    },
]


async def live_turn(request: ChatRequest, api_key: str) -> ChatResponse:
    """Call the same OpenRouter model previously used by the Next.js route."""

    graph_hint = ""
    if request.graph:
        mappings = "\n".join(
            f"- {entry.source_field} maps to {entry.target_element} (verified)"
            for entry in request.graph
        )
        graph_hint = (
            "\n\nIntegration Graph — mappings a human already verified on earlier products. "
            "Reuse these when the same source field appears again, and raise your confidence "
            f"accordingly:\n{mappings}"
        )

    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "tools": TOOLS,
        "tool_choice": "auto",
        "messages": [
            {"role": "system", "content": _system_prompt() + graph_hint},
            *[message.model_dump() for message in request.messages],
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://mia-dpp.vercel.app",
        "X-Title": "MIA Digital Product Passport",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    reply = message.get("content") or ""
    proposal: MappingProposal | None = None
    generate = False

    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        arguments = json.loads(function.get("arguments") or "{}")
        if function.get("name") == "propose_mappings":
            proposed = []
            for item in arguments.get("mappings") or []:
                confidence = _clamp(item.get("confidence", 0.5))
                proposed.append(
                    ProposedFieldMapping(
                        source_field=str(item.get("sourceField") or "unknown"),
                        source_value=str(item.get("sourceValue") or ""),
                        target_element=str(item.get("targetElement") or ""),
                        semantic_id=semantic_id_for(str(item.get("targetElement") or "")),
                        confidence=confidence,
                        reasoning=str(item.get("reasoning") or ""),
                        status=_status(confidence),
                    )
                )
            proposal = MappingProposal(
                product_name=str(arguments.get("productName") or "Product"),
                mappings=tuple(proposed),
            )
        if function.get("name") == "generate_dpp":
            generate = True

    if not reply:
        if proposal:
            reply = (
                "Mapped what I could from that. Anything below the confidence line is "
                "waiting on your decision."
            )
        elif generate:
            reply = "Building the passport from your approved mappings."
        else:
            reply = "Tell me about the product and I'll map it."

    return ChatResponse(
        reply=reply,
        proposal=proposal,
        generate=generate,
        mode="live",
        nameplate_elements=_catalog(),
    )
