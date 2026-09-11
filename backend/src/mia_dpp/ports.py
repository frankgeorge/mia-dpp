"""MIA-owned interfaces isolating optional upstream implementations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mia_dpp.aas.models import AasArtifact, DeploymentResult, ValidationReport
from mia_dpp.domain.evidence import (
    DocumentReference,
    EvidenceRecord,
    ProductKnowledgePackage,
    SiteAdapterSpec,
)
from mia_dpp.domain.mappings import MappingSpecification
from mia_dpp.domain.targets import SubmodelTemplate, TemplateRelease


class WebsiteExtractor(Protocol):
    async def extract_url(
        self,
        url: str,
        spec: SiteAdapterSpec,
    ) -> Sequence[EvidenceRecord]: ...


class DocumentExtractor(Protocol):
    def extract(self, document: DocumentReference) -> Sequence[EvidenceRecord]: ...


class TemplateRepository(Protocol):
    def get(self, key: str) -> TemplateRelease: ...

    def load(self, key: str) -> SubmodelTemplate: ...


class AasCompiler(Protocol):
    def compile(
        self,
        package: ProductKnowledgePackage,
        specification: MappingSpecification,
        template: SubmodelTemplate,
    ) -> AasArtifact: ...


class AasRepository(Protocol):
    async def deploy(
        self,
        artifact: AasArtifact,
        validation: ValidationReport,
    ) -> DeploymentResult: ...
