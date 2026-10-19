/**
 * API response shapes.
 *
 * `packages/contracts/types.ts` is generated from the Pydantic **domain** models and
 * is imported directly (never duplicated). It does not cover the HTTP envelope
 * shapes, so those are declared here - this is the documented exception:
 *
 *  - the generator maps domain models, not route responses;
 *  - route envelopes (graph payload, evaluate result, manifest) are thin wrappers
 *    around those models and are asserted against the live OpenAPI document by
 *    `tests/api-client.test.ts` using the repository's own generated `openapi.json`.
 *
 * One further precision: Pydantic emits edge geometry as `[[x, y], ...]` tuples,
 * which the conservative generator maps to `Record<string, unknown>[][]`. The
 * renderer therefore uses the explicit `EdgeGeometry` alias below instead of the
 * generated placeholder, because silently treating those pairs as untyped records
 * would defeat the point of using generated contracts at all.
 */

import type { NormalisedAnalysisResult } from './normalize'

export type { NormalisedAnalysisResult }
import type {
  AnalysisResult,
  CandidateEvaluation,
  CoordinateBasis,
  DataSource,
  Edge,
  EdgeEvaluation,
  EvidenceRecord,
  ExcludedIntervention,
  Intervention,
  MobilityProfile,
  Node,
  ODPairResult,
  OriginDestination,
  Phase,
  Rule,
  RulePack,
  Scenario,
  SearchConfig,
  SolverStatus,
  TemporaryEdge,
} from '@contracts/types'

/**
 * Re-exported generated contracts.
 *
 * Components import domain models from the single generated module rather than
 * re-declaring them, so there is exactly one source of truth for the shapes the
 * API validates against.
 */
export type {
  AnalysisResult,
  BaselineOD,
  BaselineProfile,
  BudgetCheck,
  CandidateAssumption,
  CandidateCostLine,
  CandidateCostSummary,
  CandidateEvaluation,
  CandidateProposal,
  CandidateVerification,
  CoordinateBasis,
  CostProvenance,
  DataSource,
  DomainSummary,
  EdgeType,
  EdgeEvaluation,
  ElementStateChange,
  EngineeringObservation,
  EvidenceConflictReport,
  EvidenceCriticality,
  EvidenceIssue,
  EvidenceIssuePair,
  EvidenceQueue,
  EvidenceQueueScope,
  EvidenceRecord,
  ExecutionError,
  ExcludedIntervention,
  ExperimentLimits,
  ExperimentOutcome,
  ExperimentSource,
  ExperimentSummary,
  FaultDefinition,
  FaultKind,
  FaultObservation,
  Intervention,
  InterventionCost,
  InterventionEffect,
  InterventionPhaseChange,
  InterventionPrecondition,
  MobilityProfile,
  Node,
  ObservationComparison,
  ODPairResult,
  ODTransition,
  OriginDestination,
  PairTransition,
  Phase,
  PhaseProfileOutcome,
  ProvenanceClass,
  QueueState,
  RankingPolicy,
  ReasonCode,
  ReportAlternativePlan,
  ReportCandidate,
  ReportEvidenceIssue,
  ReportEvidenceRow,
  ReportExperiment,
  ReportFinding,
  ReportIdentity,
  ReportLimitations,
  ReportModification,
  ReportNetwork,
  ReportODRow,
  ReportScope,
  ReportSection12,
  ResolvedAttribute,
  ReviewReport,
  RobustnessSummary,
  Rule,
  RulePack,
  RuleVerdict,
  Scenario,
  SearchBudget,
  SearchConfig,
  SearchOutcome,
  SearchStatus,
  SectionAvailability,
  SolverStatus,
  TemporaryEdge,
  VerificationStatus,
  VerdictState,
} from '@contracts/types'

/**
 * Route envelopes the contract generator does not cover.
 *
 * These are thin wrappers around the generated domain models plus query/filter
 * echoes. They are asserted against the live `openapi.json` in
 * `tests/api-client.test.ts`, so a drift between these shapes and the routes is
 * a failing test rather than a runtime surprise.
 */

/**
 * Names used *inside* this module. The re-export block above only publishes
 * types to consumers; referencing one here still needs an import.
 */
import type {
  ElementStateChange,
  EngineeringObservation,
  EvidenceConflictReport,
  EvidenceIssue,
  EvidenceIssuePair,
  EvidenceQueue,
  EvidenceQueueScope,
  ExecutionError,
  ExperimentLimits,
  ExperimentOutcome,
  FaultDefinition,
  FaultKind,
  ObservationComparison,
  PairTransition,
  ReportIdentity,
  ReviewReport,
  RobustnessSummary,
  SectionAvailability,
} from '@contracts/types'

/** One entry of `GET /scenarios/{id}/failure-lab/catalog`. */
export interface FailureLabCatalog {
  scenario_id: string
  scenario_revision: number
  scenario_content_hash: string
  declared_phase_ids: string[]
  selected_phase_ids: string[]
  rulepack: { id: string; version: string; content_hash: string; legal_applicability: string }
  fault_kinds: { kind: Gate6Fault['kind']; description: string; mutation_note: string }[]
  suites: {
    suite_id: string
    title: string
    description: string
    target_element_ids: string[]
    applicable_phase_ids: string[]
    applicable: boolean
    unavailable_reason: string
  }[]
  limits: Gate6Limits
  unsupported_scenarios: { name: string; reason: string }[]
  honesty_note: string
}

/** `POST /scenarios/{id}/failure-lab/experiments` response envelope. */
export interface FailureLabRunEnvelope {
  experiments: Gate6Experiment[]
  experiment_count: number
  robustness: Gate6Robustness | null
  limits: Gate6Limits
  unsupported_scenarios: { name: string; reason: string }[]
}

/** One fault definition sent to the backend. */
export interface FaultRequestPayload {
  kind: FaultKind
  label?: string
  target_ids?: string[]
  phase_ids?: string[]
  observation?: {
    field: string
    value?: number | string | boolean | null
    unit?: string | null
    method?: string
    source?: string
    verification_status?: 'unverified' | 'verified' | 'disputed'
    quality?: 'high' | 'medium' | 'low'
    provenance_class?: 'assumed' | 'synthetic' | 'synthetic_fixture'
    note?: string
  }
  evaluation_instant?: string | null
  note?: string
}

/** Stored experiment metadata shown in history lists. */
export interface StoredExperimentSummary {
  experiment_id: string
  scenario_id: string
  scenario_revision: number
  phase_ids: string[]
  profile_ids: string[]
  fault_kinds: FaultKind[]
  fault_labels: string[]
  status: string
  observations: EngineeringObservation[]
  input_hash: string
  semantic_hash: string
  created_at: string
  suite_id: string | null
  error_code: string | null
}

/** `POST /failure-lab/experiments/{id}/replay`. */
export interface ExperimentReplay {
  experiment_id: string
  reproduced: boolean
  detail: string
  stored_semantic_hash: string
  stored_input_hash: string
  replayed_semantic_hash: string
  replayed_experiment_id: string
  status: string
}

/** Element-level before/after for one experiment. */
export interface ExperimentGraphDiff {
  experiment_id: string
  status: string
  source: Gate6Experiment['source']
  isolated: {
    scenario_hash: string
    graph_hash: string
    graph_version_id: string
    evaluation_instant: string
  }
  phase_graph_identities: {
    phase_id: string
    profile_id: string
    baseline_phase_graph_hash: string | null
    faulted_phase_graph_hash: string | null
    changed: boolean
  }[]
  element_changes: Gate6ElementChange[]
  evidence_change_log: Record<string, unknown>[]
  applicability: { faults: Record<string, unknown>[] }
}

/** Stored review packet metadata. */
export interface StoredReportSummary {
  report_id: string
  scenario_revision: number
  describes_current_revision: boolean
  schema_version: string
  generator_version: string
  semantic_hash: string
  pdf_sha256: string
  pdf_bytes: number
  pdf_page_count: number
  selected_run_ids: string[]
  selected_search_ids: string[]
  selected_experiment_ids: string[]
  created_at: string
}

/** `POST /scenarios/{id}/reports` response. */
export interface GeneratedReportEnvelope {
  report: {
    report_id: string
    semantic_hash: string
    schema_version: string
    generator_version: string
    page_count: number
    pdf_bytes: number
    pdf_sha256: string
    identity: ReportIdentity
    reproducibility: ReviewReport['reproducibility']
    section_availability: Record<string, SectionAvailability>
    disclaimer: string
    runtime: Record<string, unknown>
  }
  payload: Complete<ReviewReport>
}

/** `GET /reports/{id}`. */
export interface ReportEnvelope {
  report_id: string
  scenario_id: string
  scenario_revision: number
  current_scenario_revision: number
  describes_current_revision: boolean
  schema_version: string
  generator_version: string
  semantic_hash: string
  pdf_sha256: string
  pdf_bytes: number
  pdf_page_count: number
  selected_run_ids: string[]
  selected_search_ids: string[]
  selected_experiment_ids: string[]
  created_at: string
  payload: Complete<ReviewReport>
}

/** `[[x, y], [x, y], ...]` in the graph's own coordinate basis. */
export type EdgeGeometry = [number, number][]

/**
 * Treats every property of a generated contract as present, recursively.
 *
 * The generator marks a field optional whenever its Pydantic counterpart has a
 * default. That is faithful to the schema but misleading here: the backend
 * serialises with `model_dump()`, which always emits every field, at every level.
 * Applying this to the Gate 6 models removes hundreds of `?? []` guards at the
 * call sites without weakening type safety, because a genuinely absent field is
 * still typed as its declared type rather than as `any`.
 */
export type Complete<T> = T extends readonly (infer U)[]
  ? Complete<U>[]
  : T extends object
    ? { [K in keyof T]-?: Complete<T[K]> }
    : T

/** Gate 6 domain models, with defaults guaranteed present. */
export type Gate6Issue = Complete<EvidenceIssue>
export type Gate6IssuePair = Complete<EvidenceIssuePair>
export type Gate6ConflictReport = Complete<EvidenceConflictReport>
export type Gate6Observation = Complete<ObservationComparison>
export type Gate6Queue = Complete<EvidenceQueue>
export type Gate6QueueScope = Complete<EvidenceQueueScope>
export type Gate6Fault = Complete<FaultDefinition>
export type Gate6Experiment = Complete<ExperimentOutcome>
export type Gate6Transition = Complete<PairTransition>
export type Gate6ElementChange = Complete<ElementStateChange>
export type Gate6Error = Complete<ExecutionError>
export type Gate6Limits = Complete<ExperimentLimits>
export type Gate6Robustness = Complete<RobustnessSummary>
export type Gate6Report = Complete<ReviewReport>

/** The flat error envelope every backend failure uses. */
export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
  request_id: string
}

export interface Project {
  id: string
  name: string
  study_area_description: string
  basis: CoordinateBasis
  jurisdiction: string
  owner: string
  dataset_source: DataSource
  notice?: string
}

export interface ProjectGraph {
  project_id: string
  graph_version_id: string
  content_hash: string
  basis: CoordinateBasis
  source: DataSource
  nodes: Node[]
  edges: GraphEdge[]
  evidence: EvidenceRecord[]
  unlinked_crossings: UnlinkedCrossing[]
}

export type GraphEdge = Omit<Edge, 'geometry'> & { geometry: EdgeGeometry }

export interface UnlinkedCrossing {
  edge_ids: [string, string]
  point: [number, number]
  connected_via_shared_node: boolean
  shared_node_ids?: string[]
}

export interface RunSummary {
  id: string
  scenario_id: string
  scenario_revision: number
  phase_id: string
  profile_id: string
  engine_version: string
  evaluation_instant: string
  input_hash: string
  semantic_hash: string
  created_at: string
}

export interface StoredRunSummary extends RunSummary {
  duration_ms?: number
}

export interface EvaluateResponse {
  run: RunSummary
  result: NormalisedAnalysisResult
}

export interface RunResponse {
  run: StoredRunSummary
  result: NormalisedAnalysisResult
}

export interface HealthResponse {
  status: string
  engine_version: string
  rulepack_id: string
  rulepack_hash: string
  legal_applicability: string
  database_schema_version: number
  row_counts: Record<string, number>
  max_blocker_probes: number
  profiles: string[]
}

export interface RuleSetResponse {
  rulepacks: (Omit<RulePack, 'rules'> & { rules: Rule[] })[]
  profiles: MobilityProfile[]
}

export interface ScenarioRunList {
  scenario_id: string
  runs: StoredRunSummary[]
}

export interface ScenarioSummary {
  id: string
  name: string
  revision: number
  content_hash: string
  parent_scenario_id: string | null
  base_graph_version_id: string
  rulepack_id: string
  phase_count: number
  edit_count: number
  note: string
}

export interface ScenarioListResponse {
  project_id: string
  scenarios: ScenarioSummary[]
}

export interface ScenarioRevisionEntry {
  revision: number
  content_hash: string
  created_at: string
}

export type ScenarioList = {
  id: string
  name: string
  parent_scenario_id: string | null
  base_graph_version_id: string
  rulepack_id: string
  rulepack_hash: string
  revision: number
  phases: Phase[]
  origins_destinations: OriginDestination[]
  temporary_edges: TemporaryEdge[]
  edits: ScenarioEdit[]
  intervention_ids: string[]
  note: string
  content_hash: string
}

export type ScenarioEdit = NonNullable<Scenario['edits']>[number]

/**
 * Phase reads (Gate 4).
 *
 * The timeline and the phase graph are served by the backend precisely so the
 * browser never reconstructs closures or temporary connections itself.
 */
export interface PhaseAnalysisState {
  analysed: boolean
  /** `analysed` or `NOT_ANALYSED`. NOT_ANALYSED is *not* a verdict. */
  state: 'analysed' | 'NOT_ANALYSED'
  run_id: string | null
  profile_id: string | null
  semantic_hash: string | null
  scenario_revision: number | null
  /** True when only older-revision runs exist for this phase. */
  stale: boolean
  historical_run_count?: number
}

export interface PhaseTimelineEntry {
  phase_id: string
  order: number
  label: string
  notes: string
  boundary_convention: string
  closed_edge_ids: string[]
  temporary_edge_ids: string[]
  phase_graph_id: string
  phase_graph_hash: string
  warnings: string[]
  analysis: PhaseAnalysisState
}

export interface ScenarioTimeline {
  scenario_id: string
  scenario_revision: number
  scenario_content_hash: string
  ordering: 'phase_order'
  phases: PhaseTimelineEntry[]
}

export interface PhaseEdge extends GraphEdge {
  closed: boolean
  temporary: boolean
  inactive: boolean
}

export interface PhaseGraphResponse {
  scenario_id: string
  scenario_revision: number
  scenario_content_hash: string
  phase_id: string
  phase_order: number | null
  phase_label: string
  phase_notes: string
  boundary_convention: string
  phase_graph_id: string
  phase_graph_hash: string
  closed_edge_ids: string[]
  active_temporary_edge_ids: string[]
  warnings: string[]
  nodes: Node[]
  edges: PhaseEdge[]
  crossings: UnlinkedCrossing[]
}

export interface ManifestResponse {
  schema_version: string
  engine_version: string
  project: { id: string; notice: string }
  inputs: {
    base_graph_version_id: string
    base_graph_hash: string
    base_graph_basis: CoordinateBasis
    dataset_source: DataSource
    node_count: number
    edge_count: number
    evidence_count: number
    run_input_hash: string
  }
  scenario: {
    id: string
    content_hash: string
    revision: number
    phase_id: string
    phase_graph_id: string
    phase_graph_hash: string
    phases: {
      id: string
      order: number
      label: string
      boundary_convention: string
      closed_edge_ids: string[]
      temporary_edge_ids: string[]
    }[]
  }
  ruleset: {
    id: string
    version: string
    content_hash: string
    legal_applicability: string
    disclaimer: string
    rules: { id: string; version: string; scope: string; kind: string }[]
  }
  profile: MobilityProfile & { is_demo_profile: boolean }
  results: {
    counts: Record<string, number>
    edge_evaluations: EdgeEvaluation[]
    verdicts: AnalysisResult['verdicts']
    origin_destination_matrix: ODPairResult[]
    unknowns: {
      element_id: string
      rule_id: string
      reason_code: string
      explanation: string
      evidence_ids: string[]
    }[]
    known_failures: {
      element_id: string
      rule_id: string
      reason_code: string
      explanation: string
      evidence_ids: string[]
    }[]
    warnings: string[]
  }
  limitations: string[]
  attributions: { name: string; license: string; attribution: string; url: string | null }[]
  disclaimer: string
  runtime: {
    run_id: string
    created_at: string
    duration_ms: number
    evaluation_instant: string
    engine_version: string
  }
  semantic_hash: string
  canonical_json_bytes: number
}

/**
 * Fix This Plan reads (Gate 5).
 *
 * Every candidate, verdict and delta in these payloads was computed by the
 * backend engine against the source plan; the browser renders them and never
 * derives its own verdict, route or cost.
 */
export interface InterventionCatalogItem extends Intervention {
  applicable: boolean
  eligibility_reasons: string[]
}

export interface InterventionCatalog {
  library: { id: string; version: string; notice: string; source: string }
  scenario_id: string
  scenario_revision: number
  phase_id: string
  declared_phases: string[]
  evaluated_as_of: string
  interventions: InterventionCatalogItem[]
  eligible_intervention_ids: string[]
  excluded: ExcludedIntervention[]
  precondition_rejected: Record<string, unknown>[]
}

export interface OptimizationSearchRequest {
  phase_id: string
  profile_ids?: string[]
  evaluation_instant?: string
  config?: SearchConfig
}

export interface OptimizationSearchSummary {
  search_id: string
  scenario_id: string
  scenario_revision: number
  phase_id: string
  evaluation_instant: string
  engine_version: string
  semantic_hash: string
  input_hash: string
  created_at: string
  solver_status: SolverStatus | null
  exhaustive: boolean | null
  best_proposal_id: string | null
  candidate_count: number
}

export interface OptimizationSearchList {
  scenario_id: string
  searches: OptimizationSearchSummary[]
}

export interface PromotionRequest {
  search_id: string
  proposal_id: string
  new_scenario_id: string
  new_scenario_name: string
  expected_source_revision: number
}

export interface PromotionProfileMatch {
  profile_id: string
  preview_semantic_hash: string
  persisted_semantic_hash: string
  match: boolean
}

export interface PromotionResult {
  engine_version: string
  search_id: string
  proposal_id: string
  classification: CandidateEvaluation['classification']
  source: { scenario_id: string; revision: number; content_hash: string; unchanged: boolean }
  branch: {
    scenario_id: string
    name: string
    revision: number
    parent_scenario_id: string | null
    content_hash: string
    intervention_ids: string[]
  }
  verification: {
    content_hash_match: boolean
    per_profile: PromotionProfileMatch[]
    all_match: boolean
  }
  od_summary: {
    restored_all_profiles: string[]
    restored_any_profile: string[]
    regressed_pairs: string[]
  }
  disclaimers: string[]
}

