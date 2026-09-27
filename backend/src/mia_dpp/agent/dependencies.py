"""Runtime dependencies injected into MIA agent calls."""

from dataclasses import dataclass
from typing import Any

from mia_dpp.aas.templates import OfficialTemplateRepository
from mia_dpp.agent.models import AgentTraceEvent, MiaState
from mia_dpp.store import Store


@dataclass
class MiaDependencies:
    """Capabilities injected into every agent call."""

    state: MiaState
    templates: OfficialTemplateRepository
    store: Store

    def add_event(self, event_type: str, summary: str, **details: Any) -> AgentTraceEvent:
        """Append and immediately persist one safe activity event."""

        return self.store.add_event(self.state.thread_id, event_type, summary, **details)
