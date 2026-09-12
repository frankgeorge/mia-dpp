# mypy: disable-error-code="attr-defined"
"""Agent node that invokes the web evidence extraction tool."""

from mia_dpp.agent.state import AgentState


class WebNodes:
    async def _extract_web(self, state: AgentState) -> AgentState:
        result = await self._web_tool.extract(state["website_url"])
        return {"web_extraction": result.model_dump(mode="json")}
