"""Normalize source facts into stable, provenance-rich evidence records."""

from __future__ import annotations

import re
from collections.abc import Sequence

from mia_dpp.models import CandidateFact, EvidenceRecord, EvidenceStatus, RawSourceArtifact

EXTRACTOR_NAME = "mia-website-fact-extractor"
EXTRACTOR_VERSION = "1"


class EvidenceNormalizer:
    """Convert facts without deciding whether or where they map."""

    def normalize(
        self,
        source: RawSourceArtifact,
        facts: Sequence[CandidateFact],
    ) -> tuple[EvidenceRecord, ...]:
        records: list[EvidenceRecord] = []
        for fact in facts:
            if fact.source_artifact_id != source.id:
                raise ValueError(f"candidate fact {fact.id!r} belongs to a different source")
            slug = re.sub(r"[^a-z0-9]+", ".", fact.label.casefold()).strip(".") or "fact"
            records.append(
                EvidenceRecord(
                    id=fact.id.replace("fact-web-", "ev-web-", 1),
                    predicate=f"source.{slug}",
                    source_label=fact.label,
                    canonical_predicate=None,
                    value=fact.value,
                    unit=fact.unit,
                    source_uri=source.source_uri,
                    source_content_sha256=source.content_sha256,
                    source_location=fact.source_location,
                    extraction_method=fact.extraction_method,
                    extractor_name=EXTRACTOR_NAME,
                    extractor_version=EXTRACTOR_VERSION,
                    status=EvidenceStatus.OBSERVED,
                    acquired_at=source.acquired_at,
                )
            )
        return tuple(records)
