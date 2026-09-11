"""Chat boundary: AI may propose, deterministic Python scores and validates targets."""

from __future__ import annotations

import json
import re

import httpx

from mia_dpp.confidence import (
    MatchQuality,
    ValueFormatQuality,
    assess_mapping_confidence,
)
from mia_dpp.idta import (
    ARBITRARY_PROPERTY_PATH,
    demo_propose,
    mapping_target,
    selectable_elements,
)
from mia_dpp.models import (
    ChatRequest,
    ChatResponse,
    MappingProposal,
    MappingStatus,
    NameplateElement,
    ProposedFieldMapping,
)
from mia_dpp.templates import OfficialTemplateRepository

MODEL = "deepseek/deepseek-v3.2"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CONFIDENCE_THRESHOLD = 0.85

_KNOWN_ARBITRARY_TARGETS = (
    (
        "DegreeOfProtection",
        "0173-1#02-AAM634#003",
        "IP ingress-protection rating.",
    ),
    (
        "MeasuringRange",
        "0173-1#02-AAN401#003",
        "Operating or measuring range with unit.",
    ),
    (
        "ManufacturingSite",
        "0173-1#02-AAW336#001",
        "Plant or site where the product was manufactured.",
    ),
)


def nameplate_catalog(repository: OfficialTemplateRepository) -> tuple[NameplateElement, ...]:
    template = repository.load("digital_nameplate")
    result: list[NameplateElement] = []
    for element in selectable_elements(template):
        target = mapping_target(template, element.path)
        result.append(
            NameplateElement(
                name=target.id_short,
                path=target.instance_path,
                semantic_id=target.semantic_id.primary_value,
                hint=element.description or f"Official {target.model_type} target.",
                required=bool(element.cardinality and element.cardinality.minimum),
                model_type=target.model_type,
                value_type=target.value_type,
                target=target,
            )
        )
    for name, semantic_id, hint in _KNOWN_ARBITRARY_TARGETS:
        target = mapping_target(
            template,
            ARBITRARY_PROPERTY_PATH,
            id_short=name,
            semantic_id=semantic_id,
        )
        result.append(
            NameplateElement(
                name=name,
                path=target.instance_path,
                semantic_id=semantic_id,
                hint=hint,
                required=False,
                model_type=target.model_type,
                value_type=target.value_type,
                target=target,
            )
        )
    return tuple(result)


def _status(confidence: float) -> MappingStatus:
    return MappingStatus.AUTO if confidence >= CONFIDENCE_THRESHOLD else MappingStatus.REVIEW


def _history(request: ChatRequest) -> dict[tuple[str, str], int]:
    return {
        (entry.source_field.casefold(), entry.target_element): max(entry.corrections, 1)
        for entry in request.graph
    }


def demo_turn(
    request: ChatRequest,
    repository: OfficialTemplateRepository | None = None,
) -> ChatResponse:
    """Run the offline deterministic path without any external service."""

    repository = repository or OfficialTemplateRepository()
    catalog = nameplate_catalog(repository)
    text = request.messages[-1].content if request.messages else ""
    wants_generate = bool(
        re.search(
            r"\b(generate|build|create|export|make)\b.*\b(dpp|passport|package|aasx)\b",
            text,
            re.IGNORECASE,
        )
        or re.search(r"^(generate|export|build it|do it|yes)\b", text.strip(), re.IGNORECASE)
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
            reply="Building the passport from the mappings currently accepted in the table.",
            generate=True,
            mode="demo",
            nameplate_elements=catalog,
        )
    if not looks_like_product:
        return ChatResponse(
            reply=(
                "Describe the product and I'll extract evidence and propose official IDTA "
                "targets. Include manufacturer, model, serial number, year and order code."
            ),
            mode="demo",
            nameplate_elements=catalog,
        )

    draft = demo_propose(text, repository, history=_history(request))
    mappings = tuple(
        ProposedFieldMapping(
            **mapping.model_dump(),
            status=_status(mapping.confidence),
        )
        for mapping in draft.mappings
    )
    low = sum(item.status is MappingStatus.REVIEW for item in mappings)
    reused = sum(item.from_graph for item in mappings)
    reply = f"Found {len(mappings)} evidence-backed mapping{'s' if len(mappings) != 1 else ''}."
    if reused:
        reply += f" Prior review history reduced target ambiguity for {reused}."
    if low:
        reply += f" {low} still need{'s' if low == 1 else ''} your decision."
    else:
        reply += " Their deterministic evidence scores cleared the review line."
    return ChatResponse(
        reply=reply,
        proposal=MappingProposal(product_name=draft.product_name, mappings=mappings),
        mode="demo",
        nameplate_elements=catalog,
    )


def _system_prompt(catalog: tuple[NameplateElement, ...]) -> str:
    elements = "\n".join(f"- {item.name} ({'/'.join(item.path)}) - {item.hint}" for item in catalog)
    return "\n".join(
        (
            "You are MIA's semantic proposal assistant. Python, not you, decides confidence "
            "and validates official template metadata.",
            "",
            "You may propose only these target names:",
            elements,
            "",
            "Never invent a source value. Call propose_mappings once with every explicit "
            "field. Give a short rationale. Only call generate_dpp after an explicit request.",
        )
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_mappings",
            "description": "Propose source fields for official IDTA target names.",
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
                                "reasoning": {"type": "string"},
                            },
                            "required": [
                                "sourceField",
                                "sourceValue",
                                "targetElement",
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
            "description": "Generate from mappings already reviewed in the interface.",
            "parameters": {
                "type": "object",
                "properties": {"confirm": {"type": "boolean"}},
                "required": ["confirm"],
            },
        },
    },
]


async def live_turn(
    request: ChatRequest,
    api_key: str,
    repository: OfficialTemplateRepository | None = None,
) -> ChatResponse:
    """Ask OpenRouter for proposals, then enforce targets and confidence in Python."""

    repository = repository or OfficialTemplateRepository()
    catalog = nameplate_catalog(repository)
    catalog_by_name = {item.name: item for item in catalog}
    graph_hint = ""
    if request.graph:
        mappings = "\n".join(
            f"- {entry.source_field} maps to {entry.target_element} (human reviewed)"
            for entry in request.graph
        )
        graph_hint = (
            "\n\nPrior review history may help choose a target, but it does not verify a "
            f"current value:\n{mappings}"
        )
    payload = {
        "model": MODEL,
        "max_tokens": 2000,
        "tools": TOOLS,
        "tool_choice": "auto",
        "messages": [
            {"role": "system", "content": _system_prompt(catalog) + graph_hint},
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
    history = _history(request)

    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        if function.get("name") == "propose_mappings":
            proposed: list[ProposedFieldMapping] = []
            for index, item in enumerate(arguments.get("mappings") or []):
                target_name = str(item.get("targetElement") or "")
                catalog_item = catalog_by_name.get(target_name)
                if catalog_item is None:
                    continue
                source_field = str(item.get("sourceField") or "unknown")
                source_value = str(item.get("sourceValue") or "").strip()
                if not source_value:
                    continue
                confirmations = history.get((source_field.casefold(), target_name), 0)
                assessment = assess_mapping_confidence(
                    source_label=(
                        MatchQuality.STRONG if source_field != "unknown" else MatchQuality.NONE
                    ),
                    value_format=ValueFormatQuality.PLAUSIBLE,
                    semantic_match=MatchQuality.STRONG,
                    destination_candidates=1,
                    history_confirmations=confirmations,
                )
                digest = re.sub(r"[^a-z0-9]", "", source_field.casefold())[:12] or "source"
                evidence_id = f"ev-live-{digest}-{index}"
                proposed.append(
                    ProposedFieldMapping(
                        evidence_id=evidence_id,
                        source_field=source_field,
                        source_value=source_value,
                        target_element=target_name,
                        semantic_id=catalog_item.semantic_id,
                        target=catalog_item.target,
                        confidence=assessment.score,
                        confidence_assessment=assessment,
                        reasoning=str(item.get("reasoning") or "Semantic proposal from the model."),
                        from_graph=confirmations > 0,
                        status=_status(assessment.score),
                    )
                )
            proposal = MappingProposal(
                product_name=str(arguments.get("productName") or "Product"),
                mappings=tuple(proposed),
            )
        elif function.get("name") == "generate_dpp":
            generate = True

    if not reply:
        if proposal:
            reply = "Proposals are ready. Python calculated every confidence explanation."
        elif generate:
            reply = "Building from the mappings currently accepted in the table."
        else:
            reply = "Tell me about the product and I'll propose official IDTA targets."
    return ChatResponse(
        reply=reply,
        proposal=proposal,
        generate=generate,
        mode="live",
        nameplate_elements=catalog,
    )
