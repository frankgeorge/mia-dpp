"""Contract tests for the OpenRouter boundary without external requests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import pytest

import mia_dpp.integrations.openrouter as openrouter_module
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.integrations.openrouter import OpenRouterClient
from mia_dpp.llm.chat import ChatLLM, ChatMessage
from mia_dpp.llm.semantic import SemanticLLM
from mia_dpp.tools.mapping.models import WebsiteIngestRequest
from mia_dpp.tools.mapping.resolver import ProductResolver, WebsiteWorkflow
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "web" / "website-product.html"
PRODUCT_URL = "https://manufacturer.example/products/pg-16"


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeOpenRouterClient:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> FakeOpenRouterClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> FakeResponse:
        self.calls.append(json)
        tool_name = json["tools"][0]["function"]["name"]
        if tool_name == "respond_to_user":
            arguments: dict[str, Any] = {
                "intent": "chat",
                "reply": "Please provide a direct product URL.",
                "url": None,
            }
        else:
            context = openrouter_module.json.loads(json["messages"][1]["content"])
            selected_evidence = next(
                item for item in context["evidence"] if item["label"] == "Connectivity"
            )
            selected_requirement = next(
                item
                for item in context["requirements"]
                if item["name"] == "ManufacturerProductFamily"
            )
            arguments = {
                "mappings": [
                    {
                        "evidenceId": selected_evidence["id"],
                        "requirementId": selected_requirement["id"],
                        "reasoning": "A constrained test proposal.",
                    },
                    {
                        "evidenceId": "invented-evidence",
                        "requirementId": selected_requirement["id"],
                        "reasoning": "This invented ID must be removed.",
                    },
                ]
            }
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": tool_name,
                                        "arguments": openrouter_module.json.dumps(arguments),
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )


class FixtureLoader:
    async def load(self, url: str) -> RenderedPage:
        return RenderedPage(url=url, html=FIXTURE.read_text(encoding="utf-8"))


async def public_resolver(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def roles() -> tuple[ChatLLM, SemanticLLM]:
    client = OpenRouterClient("test-key")
    return (
        ChatLLM(client, model="conversation-model"),
        SemanticLLM(client, model="semantic-model"),
    )


def test_conversation_requires_a_typed_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeOpenRouterClient.calls.clear()
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", FakeOpenRouterClient)

    decision = asyncio.run(
        roles()[0].decide((ChatMessage(role="user", content="How can MIA help me?"),))
    )

    assert decision.intent == "chat"
    assert "product URL" in decision.reply
    assert FakeOpenRouterClient.calls[0]["model"] == "conversation-model"
    assert FakeOpenRouterClient.calls[0]["tool_choice"]["function"]["name"] == "respond_to_user"


def test_semantic_model_can_return_only_supplied_domain_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeOpenRouterClient.calls.clear()
    monkeypatch.setattr(openrouter_module.httpx, "AsyncClient", FakeOpenRouterClient)
    repository = OfficialTemplateRepository()
    website = asyncio.run(
        WebsiteWorkflow(
            WebExtractionTool(
                loader=FixtureLoader(),
                url_policy=ProductUrlPolicy(public_resolver),
            ),
            ProductResolver(repository),
        ).ingest(WebsiteIngestRequest(url=PRODUCT_URL))
    )

    decisions = asyncio.run(
        roles()[1].propose(
            website.knowledge_package,
            website.coverage_report,
        )
    )

    assert len(decisions) == 1
    assert decisions[0].evidence_id in {item.id for item in website.evidence}
    assert decisions[0].requirement_id in {
        item.id for item in website.coverage_report.inventory.requirements
    }
    assert FakeOpenRouterClient.calls[0]["model"] == "semantic-model"
