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