"""HTTP adapter for deploying only validated artifacts to Eclipse BaSyx."""

from __future__ import annotations

import base64
from typing import Any, cast

import httpx

from mia_dpp.canonical import sha256_json
from mia_dpp.domain.contracts import AasArtifact, DeploymentResult, ValidationReport
from mia_dpp.errors import DeploymentError


class BasyxAasRepository:
    """Keep BaSyx transport details outside MIA's compiler and domain models."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def deploy(
        self,
        artifact: AasArtifact,
        validation: ValidationReport,
    ) -> DeploymentResult:
        """Create submodels before shells after verifying the deployment gate."""

        if not validation.valid:
            raise DeploymentError("an artifact with failed validation cannot be deployed")
        if validation.artifact_sha256 != artifact.sha256:
            raise DeploymentError("validation report does not apply to this artifact digest")
        if sha256_json(artifact.environment) != artifact.sha256:
            raise DeploymentError("artifact content differs from its recorded digest")
        submodels = self._objects(artifact, "submodels")
        shells = self._objects(artifact, "assetAdministrationShells")
        try:
            for submodel in submodels:
                await self._post("submodels", submodel)
            for shell in shells:
                await self._post("shells", shell)
        except httpx.HTTPError as error:
            raise DeploymentError(f"BaSyx deployment failed: {error}") from error
        return DeploymentResult(
            artifact_sha256=artifact.sha256,
            repository_url=self._base_url,
            shell_ids=tuple(self._identifier(item) for item in shells),
            submodel_ids=tuple(self._identifier(item) for item in submodels),
        )

    async def _post(self, collection: str, value: dict[str, Any]) -> None:
        response = await self._client.post(f"{self._base_url}/{collection}", json=value)
        response.raise_for_status()

    @staticmethod
    def _objects(artifact: AasArtifact, key: str) -> list[dict[str, Any]]:
        values = artifact.environment.get(key, [])
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            raise DeploymentError(f"AAS environment field {key!r} must be a list of objects")
        return cast(list[dict[str, Any]], values)

    @staticmethod
    def _identifier(value: dict[str, Any]) -> str:
        identifier = value.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise DeploymentError("AAS repository object has no identifier")
        return identifier

    @staticmethod
    def encode_identifier(identifier: str) -> str:
        """Encode an AAS identifier as required by BaSyx repository routes."""

        return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")
