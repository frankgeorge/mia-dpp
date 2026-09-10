export type MappingStatus = "auto" | "review" | "approved" | "rejected";
export type Severity = "info" | "warning" | "error";
export type ValidationCategory = "metamodel" | "template" | "policy";
export type EvidenceStatus =
  | "observed"
  | "inferred"
  | "verified"
  | "conflicting"
  | "rejected";

export interface SourceLocation {
  page: number | null;
  selector: string | null;
  jsonPointer: string | null;
  excerpt: string | null;
  table: string | null;
  cell: string | null;
}

export interface EvidenceRecord {
  id: string;
  predicate: string;
  value: unknown;
  unit: string | null;
  sourceUri: string;
  sourceContentSha256: string;
  sourceLocation: SourceLocation;
  extractionMethod: string;
  extractorName: string;
  extractorVersion: string;
  status: EvidenceStatus;
  acquiredAt: string;
}

export interface ReferenceKey {
  type: string;
  value: string;
}

export interface SemanticReference {
  type: string;
  keys: ReferenceKey[];
}

export interface ConfidenceFactor {
  code: string;
  label: string;
  awarded: number;
  maximum: number;
  explanation: string;
  uncertainty: string | null;
}

export interface ConfidenceAssessment {
  score: number;
  factors: ConfidenceFactor[];
  remainingUncertainty: string[];
}

export interface TemplateRelease {
  key: string;
  family: string;
  release: string;
  repositoryCommit: string;
  sourcePath: string;
  sourceSha256: string;
  metamodelVersion: string;
}

export interface TargetProfile {
  id: string;
  name: string;
  template: TemplateRelease;
  aasMetamodelVersion: "3.0";
  language: string;
}

export interface MappingTarget {
  templateKey: string;
  templateRelease: string;
  templatePath: string[];
  instancePath: string[];
  idShort: string;
  semanticId: SemanticReference;
  modelType: string;
  valueType: string | null;
  wildcard: boolean;
}

export interface FieldMapping {
  id: string;
  evidenceId: string;
  /** Field name as it appears in the manufacturer's own system. */
  sourceField: string;
  sourceValue: string;
  /** Compatibility label; target contains the authoritative template metadata. */
  targetElement: string;
  semanticId: string;
  target: MappingTarget;
  /** Reproducible score from confidenceAssessment, not a probability. */
  confidence: number;
  confidenceAssessment: ConfidenceAssessment;
  reasoning: string;
  status: MappingStatus;
  /** True when earlier human review helped resolve the target. */
  fromGraph?: boolean;
}

export type ProposedFieldMapping = Omit<FieldMapping, "id">;

export interface NameplateElement {
  name: string;
  path: string[];
  semanticId: string;
  hint: string;
  required: boolean;
  modelType: string;
  valueType: string | null;
  target: MappingTarget;
}

export interface GraphEntry {
  sourceField: string;
  targetElement: string;
  semanticId: string;
  verifiedAt: string;
  corrections: number;
}

export interface Gap {
  templatePath: string[];
  message: string;
  severity: Severity;
}

export interface GapReport {
  templateKey: string;
  gaps: Gap[];
  blocksDeployment: boolean;
}

export interface ValidationFinding {
  category: ValidationCategory;
  code: string;
  message: string;
  severity: Severity;
  instancePath: string[];
  templatePath: string[];
  expected: string | null;
  actual: string | null;
}

export interface ValidationReport {
  valid: boolean;
  templateKey: string;
  templateRelease: string;
  artifactSha256: string;
  validatorVersions: Record<string, string>;
  findings: ValidationFinding[];
}

export interface DppPackage {
  productName: string;
  generatedAt: string;
  submodel: Record<string, unknown>;
  environment: Record<string, unknown>;
  passportId: string;
  artifactSha256: string;
  targetProfile: TargetProfile;
  gapReport: GapReport;
  validationReport: ValidationReport;
  deployable: boolean;
  evidence: EvidenceRecord[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  reply: string;
  proposal: {
    productName: string;
    mappings: ProposedFieldMapping[];
  } | null;
  generate: boolean;
  mode: string;
  nameplateElements: NameplateElement[];
}

export interface WebsiteIngestResponse {
  reply: string;
  sourceUrl: string;
  proposal: {
    productName: string;
    mappings: ProposedFieldMapping[];
  };
  evidence: EvidenceRecord[];
  mode: "website";
  nameplateElements: NameplateElement[];
}
