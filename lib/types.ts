export type MappingStatus = "auto" | "review" | "approved" | "rejected";

export interface FieldMapping {
  id: string;
  sourceField: string;
  sourceValue: string;
  targetElement: string;
  semanticId: string;
  confidence: number;
  reasoning: string;
  status: MappingStatus;
  fromGraph?: boolean;
  
  // FEATURE 4: Der Original-Beweissatz (Data Provenance)
  sourceQuote?: string; 
}

export type ProposedFieldMapping = Omit<FieldMapping, "id">;

export interface NameplateElement {
  name: string;
  semanticId: string;
  hint: string;
  required: boolean;
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