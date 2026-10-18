/**
 * Response normalisation.
 *
 * The generated contracts mark defaulted list fields optional (correctly - Pydantic
 * declares `default_factory`), but the live API always sends them. Rather than
 * sprinkling `?? []` through every component, results are normalised once at the
 * client boundary, which also makes the client defensive against a malformed or
 * partial payload: anything unexpected raises a clear error instead of producing
 * `undefined.length` deep inside a component.
 */

import type {
  PhaseEdge,
  PhaseGraphResponse,
  PhaseTimelineEntry,
  ScenarioTimeline,
} from './types'
import type {
  AnalysisResult,
  EdgeEvaluation,
  Finding,
  ODPairResult,
  ResolvedAttribute,
  RuleVerdict,
} from '@contracts/types'

export interface NormalisedEdgeEvaluation extends Omit<EdgeEvaluation, 'reason_codes' | 'verdict_ids' | 'findings' | 'unknown_only'> {
  reason_codes: string[]
  verdict_ids: string[]
  findings: FindingNormalised[]
  unknown_only: boolean
}

export interface FindingNormalised extends Omit<Finding, 'evidence_ids' | 'attributes' | 'rule_id' | 'remedy_hint'> {
  evidence_ids: string[]
  attributes: ResolvedAttribute[]
  rule_id: string | null
  remedy_hint: string
}

export interface RuleVerdictNormalised extends Omit<RuleVerdict, 'inputs' | 'rule_id'> {
  inputs: ResolvedAttribute[]
  rule_id: string
}

export interface ODPairNormalised
  extends Omit<
    ODPairResult,
    | 'confirmed_path_edge_ids'
    | 'possible_path_edge_ids'
    | 'blocking_finding_ids'
    | 'relevant_finding_ids'
    | 'reason_codes'
    | 'confirmed_distance_m'
    | 'possible_distance_m'
  > {
  confirmed_path_edge_ids: string[]
  possible_path_edge_ids: string[]
  blocking_finding_ids: string[]
  relevant_finding_ids: string[]
  reason_codes: string[]
  confirmed_distance_m: number | null
  possible_distance_m: number | null
}

export interface NormalisedAnalysisResult extends Omit<AnalysisResult, 'edge_evaluations' | 'verdicts' | 'od_results' | 'warnings' | 'counts'> {
  edge_evaluations: NormalisedEdgeEvaluation[]
  verdicts: RuleVerdictNormalised[]
  od_results: ODPairNormalised[]
  warnings: string[]
  counts: Record<string, number>
}

/**
 * Phase reads (Gate 4).
 *
 * The same rule as the analysis result applies: a phase payload that is not
 * recognisable raises a visible error rather than becoming an empty timeline or
 * a phase graph with no closures - "no data" and "no closures" are different
 * claims and must never be confused.
 */
function requiredString(source: Record<string, unknown>, key: string, where: string): string {
  const value = source[key]
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${where} is missing required field "${key}"`)
  }
  return value
}

function requiredNumber(source: Record<string, unknown>, key: string, where: string): number {
  const value = source[key]
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${where} is missing required field "${key}"`)
  }
  return value
}

export function normaliseTimeline(raw: unknown): ScenarioTimeline {
  if (!raw || typeof raw !== 'object') throw new Error('Timeline payload was not an object')
  const body = raw as Record<string, unknown>
  requiredString(body, 'scenario_id', 'Timeline')
  const phases = array<Record<string, unknown>>(body.phases)
  for (const phase of phases) {
    requiredString(phase, 'phase_id', 'Timeline phase')
    requiredNumber(phase, 'order', `Timeline phase ${String(phase.phase_id)}`)
    requiredString(phase, 'phase_graph_hash', `Timeline phase ${String(phase.phase_id)}`)
    if (!phase.analysis || typeof phase.analysis !== 'object') {
      throw new Error(`Timeline phase ${String(phase.phase_id)} is missing its analysis state`)
    }
  }
  return {
    ...(body as unknown as ScenarioTimeline),
    phases: phases.map((phase) => ({
      ...(phase as unknown as PhaseTimelineEntry),
      closed_edge_ids: array<string>(phase.closed_edge_ids),
      temporary_edge_ids: array<string>(phase.temporary_edge_ids),
      warnings: array<string>(phase.warnings),
    })),
  }
}

export function normalisePhaseGraph(raw: unknown): PhaseGraphResponse {
  if (!raw || typeof raw !== 'object') throw new Error('Phase graph payload was not an object')
  const body = raw as Record<string, unknown>
  requiredString(body, 'phase_id', 'Phase graph')
  requiredString(body, 'phase_graph_hash', 'Phase graph')
  requiredNumber(body, 'scenario_revision', 'Phase graph')
  const edges = array<Record<string, unknown>>(body.edges)
  for (const edge of edges) {
    requiredString(edge, 'id', 'Phase graph edge')
    // Geometry must be coordinate pairs; a malformed one would silently distort
    // the rendering, so it is rejected here rather than drawn.
    const geometry = edge.geometry
    if (!Array.isArray(geometry) || geometry.length < 2) {
      throw new Error(`Phase graph edge ${String(edge.id)} has no usable geometry`)
    }
  }
  return {
    ...(body as unknown as PhaseGraphResponse),
    closed_edge_ids: array<string>(body.closed_edge_ids),
    active_temporary_edge_ids: array<string>(body.active_temporary_edge_ids),
    warnings: array<string>(body.warnings),
    nodes: array(body.nodes),
    edges: edges.map((edge) => ({
      ...(edge as unknown as PhaseEdge),
      closed: Boolean(edge.closed),
      temporary: Boolean(edge.temporary),
      inactive: Boolean(edge.inactive),
    })),
    crossings: array(body.crossings),
  }
}

/** Shared by analysis results and phase payloads. */
function array<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function normaliseAnalysisResult(raw: unknown): NormalisedAnalysisResult {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Analysis result payload was not an object')
  }
  const result = raw as Record<string, unknown>
  for (const required of ['scenario_id', 'phase_id', 'profile_id', 'rulepack_id']) {
    if (typeof result[required] !== 'string') {
      throw new Error(`Analysis result is missing required field "${required}"`)
    }
  }

  return {
    ...(result as unknown as NormalisedAnalysisResult),
    counts: (result.counts ?? {}) as Record<string, number>,
    warnings: array<string>(result.warnings),
    edge_evaluations: array<Record<string, unknown>>(result.edge_evaluations).map((evaluation) => ({
      ...(evaluation as unknown as NormalisedEdgeEvaluation),
      unknown_only: Boolean(evaluation.unknown_only),
      reason_codes: array<string>(evaluation.reason_codes),
      verdict_ids: array<string>(evaluation.verdict_ids),
      findings: array<Record<string, unknown>>(evaluation.findings).map((finding) => ({
        ...(finding as unknown as FindingNormalised),
        evidence_ids: array<string>(finding.evidence_ids),
        attributes: array<ResolvedAttribute>(finding.attributes),
        rule_id: (finding.rule_id ?? null) as string | null,
        remedy_hint: (finding.remedy_hint ?? '') as string,
      })),
    })),
    verdicts: array<Record<string, unknown>>(result.verdicts).map((verdict) => ({
      ...(verdict as unknown as RuleVerdictNormalised),
      rule_id: (verdict.rule_id ?? '') as string,
      inputs: array<ResolvedAttribute>(verdict.inputs).map((input) => ({
        ...input,
        evidence_ids: array<string>(input.evidence_ids),
        conversions: array(input.conversions),
        conflicting_values: array<string>(input.conflicting_values),
      })),
    })),
    od_results: array<Record<string, unknown>>(result.od_results).map((od) => ({
      ...(od as unknown as ODPairNormalised),
      confirmed_path_edge_ids: array<string>(od.confirmed_path_edge_ids),
      possible_path_edge_ids: array<string>(od.possible_path_edge_ids),
      blocking_finding_ids: array<string>(od.blocking_finding_ids),
      relevant_finding_ids: array<string>(od.relevant_finding_ids),
      reason_codes: array<string>(od.reason_codes),
      confirmed_distance_m: nullableNumber(od.confirmed_distance_m),
      possible_distance_m: nullableNumber(od.possible_distance_m),
    })),
  }
}