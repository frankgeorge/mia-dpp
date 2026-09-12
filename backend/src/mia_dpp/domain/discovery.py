"""Stable company and product discovery concepts."""

from mia_dpp.domain.base import WireModel


class CompanyCandidate(WireModel):
    id: str
    name: str
    official_url: str
    domain: str
    description: str = ""
    source_uri: str


class ProductCandidate(WireModel):
    id: str
    name: str
    official_url: str
    description: str = ""
    family: str | None = None
    model: str | None = None
    thumbnail_url: str | None = None
    source_uri: str
