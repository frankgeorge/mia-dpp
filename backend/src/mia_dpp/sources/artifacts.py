"""Source acquisition models remain independent of extraction and AAS mapping."""

from __future__ import annotations

from mia_dpp.domain.evidence import RawSourceArtifact, SourceType
from mia_dpp.sources.extraction import RenderedPage


def raw_website_artifact(page: RenderedPage) -> RawSourceArtifact:
    """Convert one rendered page into MIA's framework-neutral source boundary."""

    return RawSourceArtifact(
        id=f"source-web-{page.content_sha256[:24]}",
        source_uri=page.url,
        content_sha256=page.content_sha256,
        acquired_at=page.acquired_at,
        media_type="text/html",
        source_type=SourceType.WEBSITE,
        content=page.html,
        metadata={"characterCount": len(page.html)},
    )
