import type { FieldMapping, DppPackage } from "./types";

/**
 * A working subset of the IDTA Digital Nameplate submodel (IDTA 02006).
 * Scoped deliberately: one submodel, done properly, rather than shallow
 * coverage of many.
 */
export const NAMEPLATE_ELEMENTS: {
  name: string;
  semanticId: string;
  hint: string;
  required: boolean;
}[] = [
  {
    name: "ManufacturerName",
    semanticId: "0173-1#02-AAO677#002",
    hint: "Legal name of the company that made the product",
    required: true,
  },
  {
    name: "ManufacturerProductDesignation",
    semanticId: "0173-1#02-AAW338#001",
    hint: "Product name or model designation",
    required: true,
  },
  {
    name: "ManufacturerProductFamily",
    semanticId: "0173-1#02-AAU731#001",
    hint: "Product family or series the item belongs to",
    required: false,
  },
  {
    name: "SerialNumber",
    semanticId: "0173-1#02-AAM556#002",
    hint: "Unique serial number of the individual item",
    required: true,
  },
  {
    name: "YearOfConstruction",
    semanticId: "0173-1#02-AAP906#001",
    hint: "Year the product was built",
    required: true,
  },
  {
    name: "CountryOfOrigin",
    semanticId: "0173-1#02-AAO259#004",
    hint: "Country where the product was manufactured",
    required: false,
  },
  {
    name: "ManufacturingSite",
    semanticId: "0173-1#02-AAW336#001",
    hint: "Plant or site where the product was manufactured",
    required: false,
  },
  {
    name: "OrderCode",
    semanticId: "0173-1#02-AAO227#002",
    hint: "Article, order or material number used to order the product",
    required: false,
  },
  {
    name: "DegreeOfProtection",
    semanticId: "0173-1#02-AAM634#003",
    hint: "IP rating or ingress protection class",
    required: false,
  },
  {
    name: "MeasuringRange",
    semanticId: "0173-1#02-AAN401#003",
    hint: "Operating or measuring range, with unit",
    required: false,
  },
  {
    name: "MaterialNumber",
    semanticId: "0173-1#02-AAO676#003",
    hint: "Internal material master number",
    required: false,
  },
  {
    name: "CEMarking",
    semanticId: "0173-1#02-AAO729#001",
    hint: "CE conformity marking or declared conformity",
    required: false,
  },
];

export const REQUIRED_ELEMENTS = NAMEPLATE_ELEMENTS.filter((e) => e.required).map(
  (e) => e.name
);

export function semanticIdFor(elementName: string): string {
  return (
    NAMEPLATE_ELEMENTS.find(
      (e) => e.name.toLowerCase() === elementName.toLowerCase()
    )?.semanticId ?? "0173-1#02-XXXXXX#001"
  );
}

/**
 * Builds an AAS-shaped Digital Nameplate submodel from approved mappings.
 * Deterministic on purpose: the model proposes mappings, but the package
 * itself is assembled by code so the output is always schema-valid.
 */
export function buildDpp(
  productName: string,
  mappings: FieldMapping[]
): DppPackage {
  const approved = mappings.filter((m) => m.status === "approved" || m.status === "auto");
  const passportId = `urn:dpp:${slug(productName)}:${Date.now().toString(36)}`;

  return {
    productName,
    passportId,
    generatedAt: new Date().toISOString(),
    submodel: {
      idShort: "Nameplate",
      id: passportId,
      kind: "Instance",
      semanticId: {
        type: "ExternalReference",
        keys: [
          {
            type: "GlobalReference",
            value: "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
          },
        ],
      },
      modelType: "Submodel",
      submodelElements: approved.map((m) => ({
        idShort: m.targetElement,
        modelType: "Property",
        valueType: "xs:string",
        value: m.sourceValue,
        semanticId: {
          type: "ExternalReference",
          keys: [{ type: "GlobalReference", value: m.semanticId }],
        },
        qualifiers: [
          {
            type: "MappingConfidence",
            valueType: "xs:double",
            value: m.confidence.toFixed(2),
          },
          {
            type: "SourceField",
            valueType: "xs:string",
            value: m.sourceField,
          },
        ],
      })),
    },
  };
}

export function missingRequired(mappings: FieldMapping[]): string[] {
  const present = new Set(
    mappings
      .filter((m) => m.status === "approved" || m.status === "auto")
      .map((m) => m.targetElement)
  );
  return REQUIRED_ELEMENTS.filter((r) => !present.has(r));
}

function slug(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40) || "product";
}

/* ------------------------------------------------------------------ */
/* Demo-mode agent                                                     */
/* Runs when no ANTHROPIC_API_KEY is set, so the demo never dead-ends.  */
/* ------------------------------------------------------------------ */

const PATTERNS: {
  re: RegExp;
  source: string;
  target: string;
  confidence: number;
  reasoning: string;
}[] = [
  {
    re: /\b(?:serial(?:\s*(?:no|number|nr))?|sn|seriennummer)\b[:\s#]*([A-Za-z0-9][A-Za-z0-9\-\/]{2,})/i,
    source: "SERNR",
    target: "SerialNumber",
    confidence: 0.96,
    reasoning: "Explicit serial-number label with an alphanumeric identifier.",
  },
  {
    re: /\b(IP\s?\d{2})\b/i,
    source: "SCHUTZART",
    target: "DegreeOfProtection",
    confidence: 0.94,
    reasoning: "Matches the IPxx ingress-protection notation.",
  },
  {
    re: /\b(\d+(?:[.,]\d+)?\s*(?:-|to|bis|–)\s*\d+(?:[.,]\d+)?\s*(?:bar|mbar|°C|psi|kPa|MPa|V|A))\b/i,
    source: "MESSBEREICH",
    target: "MeasuringRange",
    confidence: 0.88,
    reasoning: "Numeric span followed by a physical unit reads as a range.",
  },
  {
    re: /\b(?:model|modell|type|typ|designation)\b[:\s]*([A-Za-z0-9][A-Za-z0-9\-\.]{1,})/i,
    source: "MATNR_TXT",
    target: "ManufacturerProductDesignation",
    confidence: 0.91,
    reasoning: "Labelled model/type designation.",
  },
  {
    re: /\b(?:made in|manufactured in|hergestellt in)\s+([A-Za-zÄÖÜäöüß\s]{3,25})/i,
    source: "LAND1",
    target: "CountryOfOrigin",
    confidence: 0.9,
    reasoning: "Country stated with an origin phrase.",
  },
  {
    re: /\b(?:plant|werk|site|factory)\b[:\s]*([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-\s]{2,24})/i,
    source: "WERKS",
    target: "ManufacturingSite",
    confidence: 0.86,
    reasoning: "SAP plant code WERKS conventionally carries the manufacturing site.",
  },
  {
    re: /\b(?:material(?:\s*(?:no|nr|number))?|matnr|article(?:\s*(?:no|nr|number))?|art\.?\s?nr|order\s*code)\b[:\s#.]*([A-Za-z0-9]+(?:[\-\.][A-Za-z0-9]+)*)/i,
    source: "MATNR",
    target: "OrderCode",
    confidence: 0.79,
    reasoning:
      "Material number is often reused as the order code, but the two can diverge.",
  },
  {
    re: /\b(?:year|baujahr|built|year of construction)\b[:\s]*((?:19|20)\d{2})/i,
    source: "BAUJAHR",
    target: "YearOfConstruction",
    confidence: 0.93,
    reasoning: "Four-digit year with a construction-year label.",
  },
  {
    re: /\b(CE)\b[\s-]*(?:mark|marking|konform)?/i,
    source: "CE_KZ",
    target: "CEMarking",
    confidence: 0.72,
    reasoning: "CE mentioned, but the declaration reference is not stated.",
  },
];

const KNOWN_MANUFACTURERS = ["AFRISO", "SCHUNK", "FIBRO", "Bosch", "Siemens", "Festo"];

export function demoPropose(text: string): {
  productName: string;
  mappings: Omit<FieldMapping, "id" | "status">[];
} {
  const found: Omit<FieldMapping, "id" | "status">[] = [];
  const seen = new Set<string>();

  const push = (m: Omit<FieldMapping, "id" | "status">) => {
    if (seen.has(m.targetElement)) return;
    seen.add(m.targetElement);
    found.push(m);
  };

  const mfr = KNOWN_MANUFACTURERS.find((m) =>
    new RegExp(`\\b${m}\\b`, "i").test(text)
  );
  if (mfr) {
    push({
      sourceField: "NAME1",
      sourceValue: mfr,
      targetElement: "ManufacturerName",
      semanticId: semanticIdFor("ManufacturerName"),
      confidence: 0.97,
      reasoning: "Recognised manufacturer name stated directly in the request.",
    });
  }

  for (const p of PATTERNS) {
    const m = text.match(p.re);
    if (m) {
      push({
        sourceField: p.source,
        sourceValue: (m[1] ?? m[0]).trim(),
        targetElement: p.target,
        semanticId: semanticIdFor(p.target),
        confidence: p.confidence,
        reasoning: p.reasoning,
      });
    }
  }

  // Bare four-digit year fallback when no explicit label was used.
  if (!seen.has("YearOfConstruction")) {
    const y = text.match(/\b(19[89]\d|20[0-4]\d)\b/);
    if (y) {
      push({
        sourceField: "BAUJAHR",
        sourceValue: y[1],
        targetElement: "YearOfConstruction",
        semanticId: semanticIdFor("YearOfConstruction"),
        confidence: 0.64,
        reasoning:
          "Unlabelled four-digit year. Could also be a revision or catalogue year, so this needs a human check.",
      });
    }
  }

  const nameGuess =
    found.find((f) => f.targetElement === "ManufacturerProductDesignation")
      ?.sourceValue ??
    text.split(/[.,\n]/)[0].replace(/^(create|make|build)\s+a?\s*dpp\s*(for)?\s*/i, "").trim() ??
    "Product";

  return { productName: nameGuess.slice(0, 60) || "Product", mappings: found };
}
