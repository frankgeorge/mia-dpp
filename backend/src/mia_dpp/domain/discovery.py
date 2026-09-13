"""Stable company and product discovery concepts."""

from mia_dpp.domain.base import WireModel


class CompanyCandidate(WireModel):
    id: str
    name: str
    official_url: str
    domain: str
    description: str = ""
    source_uri: str
    identity_verified: bool = False


class ProductCandidate(WireModel):
    id: str
    name: str
    official_url: str
    description: str = ""
    family: str | None = None
    model: str | None = None
    thumbnail_url: str | None = None
    source_uri: str


class ProductSourceCandidate(WireModel):
    """A public page the agent may inspect for one already identified product."""

    id: str
    product_id: str
    title: str
    url: str
    description: str = ""
    authoritative_domain: bool
    source_uri: str
