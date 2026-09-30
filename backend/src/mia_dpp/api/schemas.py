"""HTTP request and response contracts exposed by MIA."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from mia_dpp.domain.base import WireModel
from mia_dpp.domain.evidence import EvidenceRecord
from mia_dpp.domain.mappings import FieldMapping


class DppBuildRequest(WireModel):
    product_name: str
    mappings: tuple[FieldMapping, ...]
    evidence: tuple[EvidenceRecord, ...] = ()
    thread_id: str | None = None


class GenerateRequest(WireModel):
    """Simple DPP generation from extracted key-value pairs.

    Fields is a dict of IDTA 02006 id_short names to their values.
    submodel_fields is a per-submodel dict for multi-submodel passports.
    """

    product_name: str = Field(min_length=1, max_length=512)
    fields: dict[str, str] = Field(default_factory=dict)
    submodel_fields: dict[str, dict[str, str]] | None = None
    thread_id: str | None = Field(default=None, min_length=8, max_length=128)


class GenerateResponse(WireModel):
    """Result of generating a DPP from simple extracted fields."""

    thread_id: str
    passport_id: str
    artifact_sha256: str
    deployable: bool
    validation_valid: bool
    dpp_json: dict


class HealthResponse(WireModel):
    status: Literal["ok", "not_ready"]
    version: str
    standards_ready: bool
    standards_commit: str


class DeployRequest(WireModel):
    basyx_url: str = "https://v3.admin-shell.io"
    passport_base_url: str = ""
    force: bool = False  # Skip AAS validation and deploy anyway


class DeployResponse(WireModel):
    status: Literal["deployed"]
    repository_url: str
    shell_ids: list[str]
    submodel_ids: list[str]
    passport_url: str
    qr_code_png_b64: str
    aas_json: dict | None = None
