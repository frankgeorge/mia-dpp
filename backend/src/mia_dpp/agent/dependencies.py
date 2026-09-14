"""Runtime dependencies injected into every PydanticAI tool call."""

from dataclasses import dataclass
from typing import Any

from mia_dpp.aas.build import DeterministicDppPipeline
from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.models import AgentTraceEvent, MiaState
from mia_dpp.store import Store
from mia_dpp.tools.mapping.review import MappingReviewService
from mia_dpp.tools.search import SearchProvider
from mia_dpp.tools.web.tool import WebExtractionTool


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
    templates: OfficialTemplateRepository
    mapping_review: MappingReviewService
    dpp_pipeline: DeterministicDppPipeline
    store: Store

    def add_event(self, event_type: str, summary: str, **details: Any) -> AgentTraceEvent:
        """Append and immediately persist one safe activity event.

        Immediate persistence lets the UI observe tool progress while the
        autonomous PydanticAI run is still in flight.
        """

        return self.store.add_event(self.state.thread_id, event_type, summary, **details)
