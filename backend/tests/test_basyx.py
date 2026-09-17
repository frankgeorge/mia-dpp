"""Tests for the BaSyx deployment gate without requiring a live server."""

import asyncio
import json

import httpx
import pytest

from mia_dpp.aas.build import build_dpp
from mia_dpp.aas.models import AasArtifact
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.errors import DeploymentError
from mia_dpp.integrations.basyx import BasyxAasRepository
from test_aas_pipeline import PRODUCT, accepted_mappings


def test_deploys_submodel_before_shell_after_validation() -> None:
    product_name, mappings = accepted_mappings(PRODUCT)
    package = build_dpp(product_name, mappings, repository=OfficialTemplateRepository())
    artifact = AasArtifact(
        environment=package.environment,
        submodel=package.submodel,
        sha256=package.artifact_sha256,
        compiler_name="test",
        compiler_version="1",
    )
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201)

    async def deploy() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await BasyxAasRepository(
                client,
                base_url="http://basyx.example",
            ).deploy(artifact, package.validation_report)

    result = asyncio.run(deploy())

    assert [path for path, _ in requests] == ["/submodels", "/shells"]
    assert result.artifact_sha256 == artifact.sha256
    assert result.submodel_ids == (package.submodel["id"],)


def test_rejects_invalid_or_stale_validation_before_network() -> None:
    product_name, mappings = accepted_mappings(
        "SCHUNK clamping module, order code JGZ-100-1, 2022."
    )
    package = build_dpp(product_name, mappings)
    artifact = AasArtifact(
        environment=package.environment,
        submodel=package.submodel,
        sha256=package.artifact_sha256,
        compiler_name="test",
        compiler_version="1",
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(500))

    async def deploy() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            repository = BasyxAasRepository(client, base_url="http://basyx.example")
            await repository.deploy(artifact, package.validation_report)

    with pytest.raises(DeploymentError, match="failed validation"):
        asyncio.run(deploy())
