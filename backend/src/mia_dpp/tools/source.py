"""Agent-facing product source ingestion capability."""

from mia_dpp.api.schemas import WebsiteIngestRequest, WebsiteIngestResponse
from mia_dpp.sources.website import WebsiteIngestionService


class SourceTool:
    def __init__(self, ingestion: WebsiteIngestionService) -> None:
        self._ingestion = ingestion

    async def ingest(self, request: WebsiteIngestRequest) -> WebsiteIngestResponse:
        return await self._ingestion.ingest(request)
