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
  CoordinateBasis,
  DataSource,
  Edge,
  EdgeEvaluation,
  EvidenceRecord,
  MobilityProfile,
  Node,
  ODPairResult,
  OriginDestination,
  Phase,
  Rule,
  RulePack,
  Scenario,
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
  CoordinateBasis,
  DataSource,
  EdgeType,
  EdgeEvaluation,
  EvidenceRecord,
  MobilityProfile,
  Node,
  ODPairResult,
  OriginDestination,
  Phase,
  ProvenanceClass,
  ReasonCode,
  ResolvedAttribute,
  Rule,
  RulePack,
  RuleVerdict,
  Scenario,
  TemporaryEdge,
  VerificationStatus,
  VerdictState,
} from '@contracts/types'

/** `[[x, y], [x, y], ...]` in the graph's own coordinate basis. */
export type EdgeGeometry = [number, number][]

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

