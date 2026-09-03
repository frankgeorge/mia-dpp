export type MappingStatus = "auto" | "review" | "approved" | "rejected";

export interface FieldMapping {
  id: string;
  /** Field name as it appears in the manufacturer's own system. */
  sourceField: string;
  sourceValue: string;
  /** Target element in the IDTA Digital Nameplate submodel. */
  targetElement: string;
  semanticId: string;
  /** 0..1 */
  confidence: number;
  reasoning: string;
  status: MappingStatus;
  /** True when this mapping was retrieved from the Integration Graph. */
  fromGraph?: boolean;
}

export interface GraphEntry {
  sourceField: string;
  targetElement: string;
  semanticId: string;
  verifiedAt: string;
  corrections: number;
}

export interface DppPackage {
  productName: string;
  generatedAt: string;
  submodel: Record<string, unknown>;
  passportId: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
