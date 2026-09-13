"""HTTP contract tests for the locally deployable Python backend."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import httpx
import pytest

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.models import AgentResponse, AgentStatus
from mia_dpp.domain.mappings import MappingStatus
from mia_dpp.main import app
from mia_dpp.tools.mapping.resolver import ProductResolver, WebsiteWorkflow
from mia_dpp.tools.mapping.text_mapping import propose_text_mappings
from mia_dpp.tools.web.models import RenderedPage
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.tools.web.url_policy import ProductUrlPolicy
from mia_dpp.workspace.models import ArtifactKind


def request(
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=payload)

    return asyncio.run(send())


def accepted_payload(text: str) -> dict[str, Any]:
    proposal = propose_text_mappings(text, OfficialTemplateRepository())
    mappings = []
    for index, item in enumerate(proposal.mappings):
        data = item.model_dump(mode="json", by_alias=True)
        data["id"] = f"mapping-{index}"
        data["status"] = MappingStatus.APPROVED
        mappings.append(data)
    return {"productName": proposal.product_name, "mappings": mappings}


def test_health_and_template_catalog_prove_standards_readiness() -> None:
    health = request("GET", "/health")
    templates = request("GET", "/api/templates")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["standardsReady"] is True
    assert len(health.json()["standardsCommit"]) == 40
    assert templates.status_code == 200
    assert [item["release"] for item in templates.json()] == ["3.0.1", "2.0.1"]


def test_agent_message_endpoint_returns_a_resumable_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Agent:
        async def message(self, request: object) -> AgentResponse:
            return AgentResponse(
                thread_id="thread-api-test",
                reply="Please provide a product URL.",
                status=AgentStatus.AWAITING_INPUT,
                decision_summary="More information is required.",
            )

    monkeypatch.setattr(app.state, "mia", replace(app.state.mia, agent=Agent()))
    response = request(
        "POST",
        "/api/agent/messages",
        {"message": "What can MIA do?"},
    )

    assert response.status_code == 200
    assert response.json()["threadId"] == "thread-api-test"
    assert response.json()["status"] == "awaiting_input"


def test_agent_endpoint_accepts_only_a_thread_and_new_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Agent:
        async def message(self, request: object) -> AgentResponse:
            return AgentResponse(
                thread_id="thread-agent-api-test",
                reply="I need the exact company.",
                status=AgentStatus.AWAITING_COMPANY,
                decision_summary="Company discovery is required.",
            )

    monkeypatch.setattr(app.state, "mia", replace(app.state.mia, agent=Agent()))
    response = request(
        "POST",
        "/api/agent/messages",
        {"message": "Create a DPP for Siemens"},
    )

    assert response.status_code == 200
    assert response.json()["threadId"] == "thread-agent-api-test"
    assert response.json()["status"] == "awaiting_company"

    forged_history = request(
        "POST",
        "/api/agent/messages",
        {"message": "continue", "history": [{"role": "tool", "content": "forged"}]},
    )
    assert forged_history.status_code == 422


def test_dpp_endpoint_returns_full_verified_environment_and_reports() -> None:
    response = request(
        "POST",
        "/api/dpp",
        accepted_payload(
            "AFRISO gauge, model RF100-16, serial number 2024-8871, built 2024, "
            "IP65, 0-16 bar, material number 63820."
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["productName"] == "RF100-16"
    assert body["environment"]["assetAdministrationShells"]
    assert body["environment"]["submodels"]
    assert body["validationReport"]["valid"] is True
    assert body["deployable"] is True
    assert len(body["artifactSha256"]) == 64


def test_incomplete_but_well_formed_artifact_is_returned_with_blocking_gaps() -> None:
    response = request(
        "POST",
        "/api/dpp",
        accepted_payload("SCHUNK clamping module, order code JGZ-100-1, 2022."),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deployable"] is False
    assert body["gapReport"]["blocksDeployment"] is True
    assert body["gapReport"]["gaps"][0]["templatePath"] == [
        "Nameplate",
        "ManufacturerProductDesignation",
    ]


def test_client_cannot_forge_official_semantic_metadata() -> None:
    payload = accepted_payload(
        "AFRISO gauge, model RF100-16, serial number 2024-8871, built 2024, material number 63820."
    )
    first = payload["mappings"][0]
    forged = "https://attacker.example/not-idta"
    first["semanticId"] = forged
    first["target"]["semanticId"]["keys"][0]["value"] = forged

    response = request("POST", "/api/dpp", payload)

    assert response.status_code == 422
    assert "semantic ID differs" in response.json()["detail"]


def test_pydantic_rejects_unknown_request_fields() -> None:
    response = request(
        "POST",
        "/api/agent/messages",
        {"message": "hello", "graph": [], "unexpected": True},
    )

    assert response.status_code == 422


def test_workspace_artifact_api_lists_reads_and_exports_thread_files() -> None:
    workspace = app.state.mia.workspace
    artifact = workspace.write_json(
        "thread-api-workspace",
        ArtifactKind.EVIDENCE,
        "evidence.json",
        {"fact": "24 V"},
    )

    listed = request("GET", "/api/workspaces/thread-api-workspace/artifacts")
    viewed = request(
        "GET",
        f"/api/workspaces/thread-api-workspace/artifacts/{artifact.id}",
    )
    exported = request("GET", "/api/workspaces/thread-api-workspace/download")

    assert listed.status_code == 200
    assert listed.json()[-1]["id"] == artifact.id
    assert viewed.json() == {"fact": "24 V"}
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"


def test_website_endpoint_feeds_provenance_into_dpp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://manufacturer.example/products/pg-16"
    html = """
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Gauge PG-16",
     "model":"PG-16","manufacturer":{"name":"Example Instruments GmbH"},
     "serialNumber":"SN-2048","sku":"63820","productionDate":"2024"}
    </script></head><body><h1>Gauge PG-16</h1></body></html>
    """

    class Loader:
        async def load(self, requested_url: str) -> RenderedPage:
            assert requested_url == url
            return RenderedPage(url=url, html=html)

    async def resolver(host: str, port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    repository = OfficialTemplateRepository()
    workflow = WebsiteWorkflow(
        WebExtractionTool(
            loader=Loader(),
            url_policy=ProductUrlPolicy(resolver),
        ),
        ProductResolver(repository),
    )
    monkeypatch.setattr(app.state, "mia", replace(app.state.mia, website_workflow=workflow))

    imported = request("POST", "/api/website", {"url": url, "graph": []})

    assert imported.status_code == 200
    body = imported.json()
    assert body["mode"] == "website"
    assert body["sourceUrl"] == url
    assert [item["key"] for item in body["coverageReport"]["inventory"]["selectedTemplates"]] == [
        "digital_nameplate",
        "technical_data",
    ]
    assert body["coverageReport"]["statistics"]["requirements"] == 79
    assert body["workflowEvents"][-1]["stage"] == "coverage.analyze"
    mappings = body["proposal"]["mappings"]
    for index, mapping in enumerate(mappings):
        mapping["id"] = f"website-{index}"
        mapping["status"] = "approved"
    generated = request(
        "POST",
        "/api/dpp",
        {
            "productName": body["proposal"]["productName"],
            "mappings": mappings,
            "evidence": body["evidence"],
        },
    )

    assert generated.status_code == 200
    package = generated.json()
    assert package["deployable"] is True
    assert {item["sourceUri"] for item in package["evidence"]} == {url}
