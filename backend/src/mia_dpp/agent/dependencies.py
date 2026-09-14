"""Runtime dependencies injected into every PydanticAI tool call."""

from dataclasses import dataclass
from typing import Any

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.agent.models import AgentTraceEvent, MiaState
from mia_dpp.tools.mapping.knowledge import MappingKnowledgeStore
from mia_dpp.tools.mapping.resolver import ProductResolver
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.search import SearchProvider
from mia_dpp.tools.web.tool import WebExtractionTool
from mia_dpp.workspace.models import ArtifactKind
from mia_dpp.workspace.store import WorkspaceStore


@dataclass
class MiaDependencies:
    """Capabilities injected into every PydanticAI tool call.

    Tools use this object to read or update the current ``MiaState`` and to
    invoke MIA services assembled by ``Mia``. The model never constructs
    these trusted dependencies itself.
    """

    state: MiaState
    search: SearchProvider
    web_tool: WebExtractionTool
    mapping_tool: ProductResolver
    mapping_review: MappingReviewService
    mapping_knowledge: MappingKnowledgeStore
    dpp_pipeline: DeterministicDppPipeline
    workspace: WorkspaceStore

    def add_event(self, event_type: str, summary: str, **details: Any) -> AgentTraceEvent:
        """Append and immediately persist one safe activity event.

        Immediate persistence lets the UI observe tool progress while the
        autonomous PydanticAI run is still in flight.
        """

        event = self.state.add_event(event_type, summary, **details)
        self.workspace.write_json(
            self.state.thread_id,
            ArtifactKind.TRACE,
            "event.json",
            event.model_dump(mode="json"),
            created_by="agent",
            product_id=event.product_id,
        )
        return event
