export type MappingStatus = "auto" | "review" | "approved" | "rejected";
export type MappingOrigin = "deterministic" | "semantic_agent" | "human";
export type Severity = "info" | "warning" | "error";
export type ValidationCategory = "metamodel" | "template" | "policy";
export type RequirementKind = "value" | "structural";
export type CoverageStatus =
  | "satisfied"
  | "candidate"
  | "ambiguous"
  | "missing";
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
  /** Label exactly as presented by the source, before semantic mapping. */
  sourceLabel: string | null;
  /** Optional understood meaning; null means MIA has not assigned one. */
  canonicalPredicate: string | null;
  value: unknown;
  unit: string | null;
  sourceType: "website" | "human";
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
  mappingOrigin: MappingOrigin;
  humanReviewed: boolean;
  llmReview?: {
    conclusion: string;
    rationale: string;
    evidenceIds: string[];
    alternativeTargetIds: string[];
    uncertainties: string[];
  } | null;
  humanComment?: string | null;
  /** True when earlier human review helped resolve the target. */
  fromGraph?: boolean;
}

export type ProposedFieldMapping = Omit<FieldMapping, "id">;

export interface ProductKnowledgePackage {
  productId: string;
  productName: string;
  sourceArtifactIds: string[];
  evidence: EvidenceRecord[];
}

export interface Requirement {
  id: string;
  templateKey: string;
  templateRelease: string;
  templatePath: string[];
  idShort: string | null;
  semanticId: SemanticReference | null;
  supplementalSemanticIds: SemanticReference[];
  modelType: string;
  valueType: string | null;
  cardinality: "One" | "ZeroToOne" | "OneToMany" | "ZeroToMany" | null;
  kind: RequirementKind;
  required: boolean;
  conditional: boolean;
  unit: string | null;
  allowedValues: string[];
  description: string | null;
  wildcard: boolean;
}

export interface RequirementInventory {
  selectedTemplates: TemplateRelease[];
  requirements: Requirement[];
}

export interface RequirementCoverage {
  requirementId: string;
  status: CoverageStatus;
  supportingEvidenceIds: string[];
  candidateEvidenceIds: string[];
  matchMethod: string;
  explanation: string;
}

export interface CoverageStatistics {
  selectedTemplates: number;
  requirements: number;
  requiredRequirements: number;
  requiredSatisfied: number;
  requiredCandidate: number;
  requiredAmbiguous: number;
  requiredMissing: number;
  optionalRequirements: number;
  optionalSatisfied: number;
  optionalCandidate: number;
  optionalAmbiguous: number;
  optionalMissing: number;
  evidenceRecords: number;
  evidenceUsed: number;
  unmatchedEvidence: number;
}

export interface CoverageReport {
  inventory: RequirementInventory;
  coverage: RequirementCoverage[];
  analyzedEvidenceIds: string[];
  unmatchedEvidenceIds: string[];
  statistics: CoverageStatistics;
}

export interface CompletionSummary {
  source: {
    totalDiscovered: number;
    automaticallyResolved: number;
    acceptedAfterReview: number;
    pendingReview: number;
    unresolved: number;
    rejectedProposals: number;
  };
  fixedTemplates: Array<{
    templateKey: string;
    templateName: string;
    mandatoryTotal: number;
    mandatoryFilled: number;
    mandatoryMissing: number;
    optionalTotal: number;
    optionalFilled: number;
    optionalMissing: number;
  }>;
  technicalData: {
    discovered: number;
    resolved: number;
    unresolved: number;
  };
}

export interface MappingResult {
  mapped: ProposedFieldMapping[];
  ambiguous: ProposedFieldMapping[];
  unmatchedEvidenceIds: string[];
}

export interface WorkflowEvent {
  id: string;
  stage: string;
  status: "done" | "failed";
  startedAt: string;
  completedAt: string;
  inputCount: number;
  outputCount: number;
  summary: string;
  metadata: Record<string, unknown>;
}

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

export interface SemanticReviewItem {
  id: string;
  requirementId: string;
  mapping: ProposedFieldMapping;
}

export interface AgentReviewDecision {
  reviewId: string;
  decision: "approve" | "correct" | "reject";
  correctedRequirementId?: string | null;
  correctedValue?: string | null;
  comment?: string | null;
}

export type AgentStatus =
  | "running"
  | "awaiting_company"
  | "awaiting_product"
  | "awaiting_review"
  | "awaiting_input"
  | "awaiting_optional_choice"
  | "ready_to_build"
  | "completed"
  | "failed";

export interface CompanyCandidate {
  id: string;
  name: string;
  officialUrl: string;
  domain: string;
  description: string;
  sourceUri: string;
  identityVerified: boolean;
}

export interface ProductCandidate {
  id: string;
  name: string;
  officialUrl: string;
  description: string;
  family: string | null;
  model: string | null;
  thumbnailUrl: string | null;
  sourceUri: string;
}

export interface ProductSourceCandidate {
  id: string;
  productId: string;
  title: string;
  url: string;
  description: string;
  authoritativeDomain: boolean;
  sourceUri: string;
}

export interface AgentTraceEvent {
  id: string;
  threadId: string;
  eventType: string;
  status: "started" | "completed" | "failed";
  timestamp: string;
  summary: string;
  toolName: string | null;
  productId: string | null;
  inputSummary: string | null;
  outputSummary: string | null;
  sourceIds: string[];
  durationMs: number | null;
  metadata: Record<string, string | number | boolean | null>;
}

export interface AgentProductWork {
  productId: string;
  status: "queued" | "in_progress" | "awaiting_review" | "ready_to_build" | "completed" | "failed";
  candidate: ProductCandidate | null;
  sourceCandidates: ProductSourceCandidate[];
  extractions: unknown[];
  resolution: WebsiteIngestResponse | null;
  pendingReviews: SemanticReviewItem[];
  reviewComplete: boolean;
  aasArtifactSha256: string | null;
  artifactIds: string[];
}

export interface HumanRequest {
  kind: "mapping_review" | "requirement_value";
  productId: string;
  summary: string;
  requirementId: string | null;
}

export interface WorkspaceArtifact {
  id: string;
  kind: "search" | "source" | "raw" | "evidence" | "mapping" | "coverage" | "review" | "aas" | "validation" | "trace" | "export";
  name: string;
  relativePath: string;
  createdAt: string;
  createdBy: string;
  contentType: string;
  sha256: string;
  size: number;
  productId: string | null;
  sourceUrl: string | null;
  derivedFrom: string[];
  downloadable: boolean;
}

export interface AgentResponse {
  threadId: string;
  reply: string;
  status: AgentStatus;
  decisionSummary: string;
  companyCandidates: CompanyCandidate[];
  selectedCompany: CompanyCandidate | null;
  productCandidates: ProductCandidate[];
  selectedProductIds: string[];
  currentProduct: AgentProductWork | null;
  traceEvents: AgentTraceEvent[];
  pendingHumanRequest: HumanRequest | null;
  artifactCount: number;
  mode: "agent";
}

export interface WebsiteIngestResponse {
  reply: string;
  sourceUrl: string;
  proposal: {
    productName: string;
    mappings: ProposedFieldMapping[];
  };
  evidence: EvidenceRecord[];
  knowledgePackage: ProductKnowledgePackage;
  mappingResult: MappingResult;
  coverageReport: CoverageReport;
  completionSummary: CompletionSummary;
  workflowEvents: WorkflowEvent[];
  mode: "website";
  nameplateElements: NameplateElement[];
}
