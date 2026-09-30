"""Web-enabled specialist agents for on-demand carbon footprint and technical data analysis."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from mia_dpp.agent.models import ExtractedField
from mia_dpp.domain.base import WireModel
from mia_dpp.integrations.ddgs import DdgsSearchProvider


@dataclass
class WebAgentDeps:
    """Dependencies injected into web-capable specialist agents."""

    search: DdgsSearchProvider
    http: httpx.AsyncClient


class SpecialistAgentOutput(WireModel):
    """Structured output returned by a specialist calculation/extraction agent."""

    reply: str
    extracted_fields: list[ExtractedField] = []
    methodology: str = ""
    confidence: str = "estimated"
    data_sources: list[str] = []


_TOOL_RULES = """
You have two tools available:
- web_search(query): searches the web and returns titles, URLs, and snippets for the top results
- fetch_url(url): fetches and extracts the full text content from a URL

Guidelines:
- Prefer official manufacturer sources, official standards databases, and peer-reviewed data
- When you cannot find exact data, use credible industry averages and clearly state this
- Cite the URL or source for every data point you use
- If a tool call fails, try an alternative query or URL
"""

_CF_INSTRUCTIONS = """\
You are a carbon footprint calculation specialist for Digital Product Passports (DPP) under IDTA 02023.
Your job: calculate a defensible Product Carbon Footprint (PCF) for an industrial product.

""" + _TOOL_RULES + """

CALCULATION PROCESS:
1. Read the PRODUCT CONTEXT in the user message — use existing fields for product name, manufacturer, materials
2. If a product URL is provided, fetch it to extract materials, weight, and specs
3. Search for manufacturer sustainability data (carbon footprint reports, green energy use, certifications)
4. Search for emission factors for key materials (main housing material, electronics, metals)
   - Example search: "ABS plastic production emission factor kg CO2e per kg"
   - Example search: "steel sheet manufacturing carbon footprint"
5. Apply: PCF = sum(weight_i × emission_factor_i) + manufacturing_energy + transport
6. If manufacturer uses 100% renewable energy, set manufacturing energy contribution to near zero
7. Return results as kg CO2eq per unit (cradle-to-gate, scope A1-A3)

OUTPUT FIELDS — use these exact IDTA 02023 field names in extracted_fields:
- PCFCO2eq: numeric PCF value as string (e.g. "4.08")
- ReferenceValueForCalculation: "piece" or "unit"
- QuantityOfMeasureForCalculation: "1"
- PCFLiveCyclePhase: "A1-A3" (cradle-to-gate) unless you have full lifecycle data
- PCFCalculationMethod: "GHG Protocol Product Standard" or "ISO 14067:2018"
- PublicationDate: today's date in YYYY-MM-DD
- ExpirationDate: one year from today in YYYY-MM-DD
- PCFGoodsAddressHandover: manufacturer address if found
- ExplanatoryStatement: brief description of methodology and data sources

In your reply:
- Summarise the calculation: what materials, which emission factors, what total
- State which values come from official sources vs industry averages
- Give confidence: "high" (official PCF data found), "medium" (verified material estimates), "low" (rough estimates only)
- Be transparent about uncertainty — a well-reasoned estimate with clear methodology is more valuable than a precise-looking guess
"""

_TD_INSTRUCTIONS = """\
You are a technical data extraction specialist for Digital Product Passports (DPP) under IDTA 02003.
Your job: extract complete, structured technical specifications for an industrial product.

""" + _TOOL_RULES + """

EXTRACTION PROCESS:
1. Read the PRODUCT CONTEXT in the user message for product name, manufacturer, order code, URL
2. If a product URL is provided, fetch it to extract specs from the product page
3. Search for the product datasheet: try "[product_name] [manufacturer] datasheet filetype:pdf" or "[order_code] technical specifications"
4. If a datasheet PDF URL is found, fetch it to extract specs
5. Extract ALL technical properties: electrical ratings, mechanical specs, environmental ratings, certifications, approvals
6. Record each property's value AND unit separately

OUTPUT FIELDS — use these IDTA 02003-compatible field names in extracted_fields:
- GeneralInformation: comprehensive product description combining capabilities and use case (REQUIRED)
- ManufacturerArticleNumber: article/part number
- ManufacturerOrderCode: order code
- FurtherInformation: additional URLs, notes, or references

For technical properties, use descriptive field names:
- SupplyVoltage (e.g. "230"), SupplyVoltageUnit (e.g. "V AC")
- ProtectionClass (e.g. "IP44"), ProtectionClassStandard (e.g. "IEC 60529")
- AmbientTemperatureMin (e.g. "-10"), AmbientTemperatureMax (e.g. "55"), TemperatureUnit (e.g. "°C")
- PowerConsumption (e.g. "3.5"), PowerUnit (e.g. "W")
- CableLength (e.g. "5"), LengthUnit (e.g. "m")
- Approvals (comma-separated, e.g. "CE, VDE, RoHS")
- ComplianceStandards (comma-separated)
- Weight (e.g. "0.8"), WeightUnit (e.g. "kg")
- Dimensions (e.g. "110 x 85 x 55"), DimensionsUnit (e.g. "mm")
- And any other specs found

Set confidence based on source quality:
- "high" = data confirmed from official manufacturer datasheet
- "medium" = from product page or official search result
- "low" = inferred or from third-party source

In your reply:
- List all specs found and their source (product page / datasheet / search)
- Note what you could not find
"""


def build_carbon_footprint_agent(model: Any) -> Agent[WebAgentDeps, SpecialistAgentOutput]:
    """Create the Carbon Footprint Calculator specialist agent."""

    agent: Agent[WebAgentDeps, SpecialistAgentOutput] = Agent(
        model,
        name="mia-carbon-footprint",
        output_type=SpecialistAgentOutput,
        instructions=_CF_INSTRUCTIONS,
        retries=2,
        model_settings=ModelSettings(temperature=0, max_tokens=8192),
    )

    @agent.tool
    async def web_search(ctx: RunContext[WebAgentDeps], query: str) -> str:  # noqa: ARG001
        """Search the web and return top results with titles, URLs and snippets."""
        try:
            hits = await ctx.deps.search.search(query, limit=6)
        except Exception as exc:
            return f"Search failed: {exc}"
        if not hits:
            return "No results found."
        return "\n\n".join(
            f"[{i + 1}] {h.title}\nURL: {h.url}\n{h.snippet}"
            for i, h in enumerate(hits)
        )

    @agent.tool
    async def fetch_url(ctx: RunContext[WebAgentDeps], url: str) -> str:  # noqa: ARG001
        """Fetch the text content of a URL (web page or PDF)."""
        try:
            resp = await ctx.deps.http.get(url, follow_redirects=True, timeout=20.0)
            resp.raise_for_status()
        except Exception as exc:
            return f"Failed to fetch {url}: {exc}"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:10_000]

    return agent


def build_technical_data_agent(model: Any) -> Agent[WebAgentDeps, SpecialistAgentOutput]:
    """Create the Technical Data Expert specialist agent."""

    agent: Agent[WebAgentDeps, SpecialistAgentOutput] = Agent(
        model,
        name="mia-technical-data",
        output_type=SpecialistAgentOutput,
        instructions=_TD_INSTRUCTIONS,
        retries=2,
        model_settings=ModelSettings(temperature=0, max_tokens=8192),
    )

    @agent.tool
    async def web_search(ctx: RunContext[WebAgentDeps], query: str) -> str:  # noqa: ARG001
        """Search the web and return top results with titles, URLs and snippets."""
        try:
            hits = await ctx.deps.search.search(query, limit=6)
        except Exception as exc:
            return f"Search failed: {exc}"
        if not hits:
            return "No results found."
        return "\n\n".join(
            f"[{i + 1}] {h.title}\nURL: {h.url}\n{h.snippet}"
            for i, h in enumerate(hits)
        )

    @agent.tool
    async def fetch_url(ctx: RunContext[WebAgentDeps], url: str) -> str:  # noqa: ARG001
        """Fetch the text content of a URL (web page or PDF)."""
        try:
            resp = await ctx.deps.http.get(url, follow_redirects=True, timeout=20.0)
            resp.raise_for_status()
        except Exception as exc:
            return f"Failed to fetch {url}: {exc}"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:10_000]

    return agent
