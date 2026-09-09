"""HTTP-level checks for the Python replacement backend."""

import asyncio

import httpx
from mia_dpp.api import app


def request(path: str, payload: dict[str, object]) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path, json=payload)

    return asyncio.run(send())


def test_chat_endpoint_uses_demo_mode_without_a_key(monkeypatch: object) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)  # type: ignore[attr-defined]
    response = request(
        "/api/chat",
        {
            "messages": [
                {"role": "user", "content": "Festo sensor, model SDE5, serial SN-42."}
            ],
            "graph": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert response.json()["proposal"]["productName"] == "SDE5"


def test_dpp_endpoint_returns_the_existing_wire_format() -> None:
    response = request(
        "/api/dpp",
        {
            "productName": "Festo SDE5",
            "mappings": [
                {
                    "id": "mapping-1",
                    "sourceField": "NAME1",
                    "sourceValue": "Festo",
                    "targetElement": "ManufacturerName",
                    "semanticId": "0173-1#02-AAO677#002",
                    "confidence": 0.97,
                    "reasoning": "Recognised manufacturer.",
                    "status": "approved",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["productName"] == "Festo SDE5"
    assert body["submodel"]["submodelElements"][0]["value"] == "Festo"
