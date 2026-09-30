"""Web-enabled specialist agents for on-demand carbon footprint and technical data analysis."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import Field
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
    tool_trace: list[dict[str, str]] = field(default_factory=list)


class SpecialistAgentOutput(WireModel):
    """Structured output returned by a specialist calculation/extraction agent."""

    reply: str
    extracted_fields: list[ExtractedField] = []
    methodology: str = ""
    confidence: str = "estimated"
    data_sources: list[str] = []
    calculation_inputs: dict[str, str] = Field(default_factory=dict)


_TOOL_RULES = """
TOOLS AVAILABLE:
- web_search(query): searches the web and returns titles, URLs, and snippets
- fetch_url(url): fetches the full text content from a URL

Use tools sparingly — prefer embedded data over web searches. Cite every source URL.
"""

_CF_INSTRUCTIONS = """\
You are a Product Carbon Footprint (PCF) calculation engine for Digital Product Passports under IDTA 02023.
You calculate a GHG Protocol Product Standard compliant PCF for scope A1-A3 (cradle-to-gate).
You do NOT search the web. You work ONLY from the product data provided in the user message.

═══════════════════════════════════════════════════════════════════
EMBEDDED EMISSION FACTOR DATABASE
(Sources: ecoinvent 3.9, World Steel Association, PlasticsEurope, IAI, iNEMI)
═══════════════════════════════════════════════════════════════════

MATERIAL FACTORS (kg CO2e per kg of material, cradle-to-gate A1-A3):
  Metals:
  • Steel (average)         1.85  — World Steel Association
  • Stainless steel 304     6.15  — ecoinvent 3.9
  • Aluminum (primary)     11.89  — International Aluminium Institute
  • Aluminum (recycled)     0.60  — IAI
  • Copper (primary)        3.28  — ecoinvent 3.9
  • Brass (Cu-Zn)           3.12  — ecoinvent 3.9
  • Cast iron               1.51  — ecoinvent 3.9
  • Zinc                    3.56  — ecoinvent 3.9

  Plastics & polymers:
  • ABS                     3.10  — PlasticsEurope Eco-profiles
  • PP (polypropylene)      1.95  — PlasticsEurope
  • PE (polyethylene, HD)   1.86  — PlasticsEurope
  • PVC                     2.41  — PlasticsEurope
  • PA6 (nylon)             7.57  — PlasticsEurope
  • PC (polycarbonate)      5.13  — PlasticsEurope
  • PTFE                    9.10  — ecoinvent 3.9
  • Epoxy resin             6.00  — ecoinvent 3.9

  Other:
  • Glass                   0.86  — ecoinvent 3.9
  • EPDM rubber             3.14  — ecoinvent 3.9
  • PCB (bare board)       28.00  — iNEMI Industry Study
  • Electronics (complex)  200.0  — estimated per kg electronic assembly

MANUFACTURING GRID CARBON INTENSITY (kg CO2e per kWh):
  • EU average   0.326    • Germany   0.485    • China     0.681
  • USA          0.433    • France    0.099    • UK        0.233
  • Global avg   0.475

PRODUCT CATEGORY BENCHMARKS (kg CO2e per unit, from published EPDs):
  • Temperature sensor / thermostat       1–5    typical 2.5
  • Pressure sensor / transmitter         2–8    typical 4.0
  • Flow meter (mechanical)               5–30   typical 12.0
  • Flow meter (electromagnetic)         15–80   typical 35.0
  • Control valve / actuator              5–50   typical 15.0
  • Industrial relay                      0.5–3  typical 1.5
  • Circuit breaker (DIN rail)            1–5    typical 2.5
  • Pump (centrifugal, small)            20–100  typical 45.0
  • Water meter                           2–6    typical 3.5
  • Gas sensor / detector                 1–5    typical 2.5
  • Smart home sensor                     0.3–1.5 typical 0.8
  • Industrial controller / PLC          10–50   typical 25.0
  • Variable frequency drive (small)     20–150  typical 60.0
  • Electric motor (small <1 kW)          5–30   typical 12.0
  • HVAC sensor / controller              1–10   typical 4.0
  • Level sensor / switch                 1–6    typical 2.8
  • Heat meter                            4–15   typical 7.5
  • Energy meter                          1–5    typical 2.5

═══════════════════════════════════════════════════════════════════
CALCULATION RULES — follow in priority order
═══════════════════════════════════════════════════════════════════

TIER 1 — MATERIAL CALCULATION (highest priority):
  Use when: Weight AND primary material are present in PRODUCT CONTEXT
  Formula:  PCF = weight_kg × material_EF × 1.25
            (1.25 covers manufacturing energy, assembly, packaging, ancillaries)
  Confidence: "medium"
  Record in calculation_inputs: weight_kg, primary_material,
    material_ef_kg_co2e_per_kg, manufacturing_factor="1.25",
    calculated_pcf_kg_co2e, data_tier="tier1_material_calculation", ef_source

TIER 2 — CATEGORY BENCHMARK:
  Use when: Product type is identifiable from name/description but no weight/material
  Use the typical value from the category benchmark table above.
  Confidence: "low"
  Record in calculation_inputs: product_category, benchmark_range,
    benchmark_typical, data_tier="tier2_category_benchmark"

TIER 3 — MISSING INPUTS:
  Use when: Cannot determine product type, weight, or material
  Set PCFCO2eq = "0", confidence = "insufficient_data"
  In reply, state exactly which 1-3 inputs are needed.
  In calculation_inputs: data_tier="tier3_insufficient_data",
    missing_inputs (comma-separated list of what's needed)

═══════════════════════════════════════════════════════════════════
OUTPUT — always populate ALL of these IDTA 02023 fields
═══════════════════════════════════════════════════════════════════

Always set (no data needed):
• PCFLiveCyclePhase:               "A1-A3"
• PCFCalculationMethod:            "GHG Protocol Product Standard"
• ReferenceValueForCalculation:    "piece"
• QuantityOfMeasureForCalculation: "1"
• PublicationDate:                 today YYYY-MM-DD
• ExpirationDate:                  one year from today YYYY-MM-DD

From calculation:
• PCFCO2eq:           the value as a string (e.g. "4.08")
• ExplanatoryStatement: 2 sentences: what was used, what tier, cite EF source

In your reply (shown in chat):
- State which tier was used
- Show the full formula with numbers: e.g. "0.35 kg × 3.10 kg CO2e/kg × 1.25 = 1.36 kg CO2e"
- If Tier 3: list exactly what inputs are needed (weight? material?)
"""

_TD_INSTRUCTIONS = """\
You are a technical data extraction specialist for Digital Product Passports (DPP) under IDTA 02003.
Your job: extract complete, structured technical specifications for an industrial product.

""" + _TOOL_RULES + """

EXTRACTION PROCESS:
1. Read PRODUCT CONTEXT — note product name, manufacturer, order code, URL
2. If a product URL is provided, fetch it to extract specs from the product page
3. Search for the product datasheet: try "[product_name] [manufacturer] datasheet filetype:pdf"
4. If a datasheet PDF URL is found, fetch it to extract specs
5. Extract ALL technical properties: electrical ratings, mechanical specs, IP ratings, certifications

OUTPUT FIELDS — IDTA 02003-compatible names in extracted_fields:
• GeneralInformation:      comprehensive product description (REQUIRED)
• ManufacturerArticleNumber, ManufacturerOrderCode
• SupplyVoltage, SupplyVoltageUnit  (e.g. "230", "V AC")
• ProtectionClass, ProtectionClassStandard  (e.g. "IP44", "IEC 60529")
• AmbientTemperatureMin, AmbientTemperatureMax, TemperatureUnit
• PowerConsumption, PowerUnit
• CableLength, LengthUnit
• Approvals   (comma-separated: "CE, VDE, RoHS")
• ComplianceStandards
• Weight, WeightUnit
• Dimensions, DimensionsUnit
• FurtherInformation
• Any other specs found

Confidence levels:
• "high"   = confirmed from official manufacturer datasheet
• "medium" = from product page or official search result
• "low"    = inferred or from third-party source

In your reply:
- List all specs found and their source
- Note what you could not find
"""


def _attach_tools(agent: Agent[WebAgentDeps, SpecialistAgentOutput]) -> None:
    """Register web_search and fetch_url tools on a specialist agent."""

    @agent.tool
    async def web_search(ctx: RunContext[WebAgentDeps], query: str) -> str:
        """Search the web and return top results with titles, URLs and snippets."""
        try:
            hits = await ctx.deps.search.search(query, limit=5)
        except Exception as exc:
            ctx.deps.tool_trace.append({"tool": "web_search", "input": query, "success": "false", "summary": str(exc)})
            return f"Search failed: {exc}"
        result = "\n\n".join(
            f"[{i + 1}] {h.title}\nURL: {h.url}\n{h.snippet}"
            for i, h in enumerate(hits)
        ) if hits else "No results found."
        ctx.deps.tool_trace.append({"tool": "web_search", "input": query, "success": "true", "summary": result[:300]})
        return result

    @agent.tool
    async def fetch_url(ctx: RunContext[WebAgentDeps], url: str) -> str:
        """Fetch the text content of a URL (web page or PDF)."""
        try:
            resp = await ctx.deps.http.get(url, follow_redirects=True, timeout=20.0)
            resp.raise_for_status()
        except Exception as exc:
            ctx.deps.tool_trace.append({"tool": "fetch_url", "input": url, "success": "false", "summary": str(exc)})
            return f"Failed to fetch {url}: {exc}"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)[:10_000]
        ctx.deps.tool_trace.append({"tool": "fetch_url", "input": url, "success": "true", "summary": text[:300]})
        return text


def build_carbon_footprint_agent(model: Any) -> Agent[WebAgentDeps, SpecialistAgentOutput]:
    """Create the Carbon Footprint Calculator — pure calculation, no web search."""

    agent: Agent[WebAgentDeps, SpecialistAgentOutput] = Agent(
        model,
        name="mia-carbon-footprint",
        output_type=SpecialistAgentOutput,
        instructions=_CF_INSTRUCTIONS,
        retries=1,
        model_settings=ModelSettings(temperature=0, max_tokens=2048),
    )
    # No tools attached — CF agent works purely from provided context
    return agent


def build_technical_data_agent(model: Any) -> Agent[WebAgentDeps, SpecialistAgentOutput]:
    """Create the Technical Data Expert specialist agent."""

    agent: Agent[WebAgentDeps, SpecialistAgentOutput] = Agent(
        model,
        name="mia-technical-data",
        output_type=SpecialistAgentOutput,
        instructions=_TD_INSTRUCTIONS,
        retries=2,
        model_settings=ModelSettings(temperature=0, max_tokens=4096),
    )
    _attach_tools(agent)
    return agent
