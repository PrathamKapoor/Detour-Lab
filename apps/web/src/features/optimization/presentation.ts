/**
 * Fix This Plan presentation helpers (Gate 5).
 *
 * Pure formatting only. The browser never derives a verdict, route, delta or
 * cost: every value these helpers format was computed and persisted by the
 * backend engine, and "unknown" always renders as an explicit label - never as
 * a fabricated number or a bare dash.
 */

import type {
  BudgetCheck,
  CandidateCostSummary,
  CandidateEvaluation,
  SolverStatus,
} from '@/api/types'
import type { StatusMeta, Tone } from '@/lib/status'

export type Classification = CandidateEvaluation['classification']

export const CLASSIFICATION_META: Record<Classification, StatusMeta> = {
  certified: {
    label: 'Model-certified',
    glyph: '✓',
    tone: 'pass',
    description:
      'No regression, no new hard model-FAIL, and at least one model-confirmed restoration or a comparable confirmed-route shortening in this scenario revision. The restoration may hold for a subset of the selected profiles; the ranking prefers improvements that hold for every profile. Not legal or engineering approval.',
  },
  requires_verification: {
    label: 'Needs verification',
    glyph: '?',
    tone: 'unknown',
    description:
      'No regression and no new hard model-FAIL, but the benefit exists only with unresolved evidence, or the candidate introduces elements whose model verdicts are UNKNOWN. Unknown is never treated as a pass.',
  },
  no_improvement: {
    label: 'No modelled improvement',
    glyph: '–',
    tone: 'neutral',
    description:
      'Evaluated against the real engine and measurably changed nothing the objective rewards. Not a failure.',
  },
  rejected: {
    label: 'Rejected',
    glyph: '✕',
    tone: 'fail',
    description:
      'Violates a hard constraint: a regression, a new hard model-FAIL, a budget that cannot be met, or an invalid effect.',
  },
}

export function classificationMeta(classification: string): StatusMeta {
  return CLASSIFICATION_META[classification as Classification] ?? CLASSIFICATION_META.rejected
}

const SOLVER_STATUS_LABEL: Record<SolverStatus, string> = {
  OPTIMAL_IN_ENUMERATED_DOMAIN:
    'Optimal in the enumerated domain (the declared search space was exhausted)',
  FEASIBLE_NOT_PROVEN_OPTIMAL:
    'Feasible candidate found - optimality not proven (search stopped at a declared limit)',
  NO_FEASIBLE_IN_ENUMERATED_DOMAIN: 'No feasible candidate in the enumerated domain',
  INVALID_INPUT: 'Invalid input',
  INCOMPLETE_OR_UNKNOWN: 'Incomplete or unknown',
}

export function solverStatusLabel(status: string | null | undefined): string {
  if (!status) return 'Unknown'
  return SOLVER_STATUS_LABEL[status as SolverStatus] ?? status
}

export function solverStatusTone(status: string | null | undefined): Tone {
  switch (status) {
    case 'OPTIMAL_IN_ENUMERATED_DOMAIN':
      return 'pass'
    case 'FEASIBLE_NOT_PROVEN_OPTIMAL':
      return 'info'
    case 'NO_FEASIBLE_IN_ENUMERATED_DOMAIN':
      return 'fail'
    default:
      return 'unknown'
  }
}

const NOT_ESTIMATED = 'Not estimated'

/** Unknown cost is "Not estimated", never 0 and never an invented price. */
export function formatCost(
  value: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return NOT_ESTIMATED
  const formatted = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(value)
  return currency ? `${formatted} ${currency}` : formatted
}

export function formatCostSummary(
  cost: Pick<CandidateCostSummary, 'nominal' | 'maximum' | 'currency' | 'unknown' | 'mixed_currency'>,
): string {
  if (cost.unknown || (cost.nominal === null && cost.maximum === null)) return NOT_ESTIMATED
  if (cost.mixed_currency) return `${formatCost(cost.nominal, cost.currency)} (mixed currencies)`
  return formatCost(cost.nominal, cost.currency)
}

export function formatSignedMetres(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Not comparable'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${value.toFixed(1)} m`
}

const BUDGET_STATUS_META: Record<BudgetCheck['status'], { label: string; tone: Tone; description: string }> = {
  not_requested: {
    label: 'No budget set',
    tone: 'neutral',
    description: 'No monetary budget filter was requested for this search.',
  },
  within: {
    label: 'Within budget',
    tone: 'pass',
    description: 'The declared upper-bound cost is at or below the budget on the stated basis.',
  },
  exceeds: {
    label: 'Exceeds budget',
    tone: 'fail',
    description: 'The candidate cannot meet the declared budget on the stated basis.',
  },
  cannot_certify_unknown_cost: {
    label: 'Cannot be certified against the budget',
    tone: 'unknown',
    description:
      'The candidate carries cost items without a declared price, so meeting the budget cannot be certified. It is never assumed to fit.',
  },
}

export function budgetMeta(status: BudgetCheck['status']) {
  return BUDGET_STATUS_META[status] ?? BUDGET_STATUS_META.not_requested
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '0'
  return String(value)
}
