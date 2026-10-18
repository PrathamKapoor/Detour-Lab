/**
 * Verdict and status presentation.
 *
 * The backend has four distinct rule states and five distinct evidence problems.
 * They are **not** interchangeable, so each gets its own label, icon glyph and
 * tone. Colour is applied through a data attribute and always accompanies the
 * text label and the glyph, so the UI remains readable without colour vision.
 */

import type { VerdictState } from '@contracts/types'

export type Tone = 'pass' | 'fail' | 'unknown' | 'neutral' | 'info' | 'temp'

export interface StatusMeta {
  label: string
  glyph: string
  tone: Tone
  /** Longer text used in legends and tooltips. */
  description: string
}

export const VERDICT_META: Record<VerdictState, StatusMeta> = {
  PASS: {
    label: 'Pass in modeled checks',
    glyph: '✓',
    tone: 'pass',
    description:
      'Every applicable modeled check was satisfied by the evidence available at the evaluation instant. Not a certification.',
  },
  FAIL: {
    label: 'Fail',
    glyph: '✕',
    tone: 'fail',
    description: 'A known measured value violates an applicable modeled constraint.',
  },
  UNKNOWN: {
    label: 'Unknown',
    glyph: '?',
    tone: 'unknown',
    description:
      'No known failure, but a required attribute is unresolved. Never reported as passing and never used as a confirmed route.',
  },
  NOT_APPLICABLE: {
    label: 'Not applicable',
    glyph: '–',
    tone: 'neutral',
    description: 'The rule was proved inapplicable to this element. Never used to clear missing evidence.',
  },
}

export function verdictMeta(state: VerdictState): StatusMeta {
  return VERDICT_META[state] ?? VERDICT_META.UNKNOWN
}

export interface EvidenceProblemMeta extends StatusMeta {
  /** What the user should actually do about it. */
  action: string
}

const EVIDENCE_PROBLEMS: Record<string, EvidenceProblemMeta> = {
  NO_EVIDENCE: {
    label: 'No evidence',
    glyph: '∅',
    tone: 'unknown',
    description: 'No observation exists for this attribute. Missing evidence is never treated as a pass.',
    action: 'Measure or enter the attribute, then re-run the analysis.',
  },
  CONFLICTING_EVIDENCE: {
    label: 'Conflicting evidence',
    glyph: '⇄',
    tone: 'unknown',
    description: 'Two or more observations disagree. All claims are retained until a reviewer decides.',
    action: 'Review both records and record an explicit, sourced decision.',
  },
  UNSUPPORTED_UNIT: {
    label: 'Unsupported unit',
    glyph: '⊘',
    tone: 'unknown',
    description: 'A record uses a unit the engine cannot convert exactly. No guess was made.',
    action: 'Re-enter the measurement with a supported unit.',
  },
  INVALID_NUMERIC_VALUE: {
    label: 'Invalid value',
    glyph: '⊘',
    tone: 'unknown',
    description: 'A record carries a value that cannot be a valid measurement.',
    action: 'Correct the recorded value.',
  },
  EVIDENCE_EXPIRED: {
    label: 'Stale evidence',
    glyph: '⏳',
    tone: 'unknown',
    description:
      'The observation is older than the freshness policy declared for this attribute by the rulepack.',
    action: 'Re-observe the attribute, or extend the policy through a reviewed rulepack.',
  },
  EVIDENCE_NOT_VERIFIED: {
    label: 'Not verified',
    glyph: '◌',
    tone: 'unknown',
    description: 'A rule requires verified evidence and this observation is unverified.',
    action: 'Have a reviewer verify the observation.',
  },
  EVIDENCE_INVALIDATED: {
    label: 'Invalidated',
    glyph: '⊗',
    tone: 'unknown',
    description: 'The record was explicitly invalidated and is not eligible for resolution.',
    action: 'Record a replacement observation.',
  },
}

const UNKNOWN_PROBLEM: EvidenceProblemMeta = {
  label: 'Unresolved',
  glyph: '?',
  tone: 'unknown',
  description: 'The evidence state could not be resolved by the engine.',
  action: 'Inspect the raw rule and evidence trace.',
}

export function evidenceProblemMeta(reasonCode: string | null | undefined): EvidenceProblemMeta {
  if (!reasonCode) return UNKNOWN_PROBLEM
  return EVIDENCE_PROBLEMS[reasonCode] ?? { ...UNKNOWN_PROBLEM, label: reasonCode.replace(/_/g, ' ').toLowerCase() }
}

export const REACHABILITY_META = {
  confirmed: {
    label: 'Model-confirmed',
    glyph: '●',
    tone: 'pass' as Tone,
    description:
      'Every edge on this route satisfied every applicable modeled check with adequate evidence.',
  },
  possible: {
    label: 'Possible only',
    glyph: '◐',
    tone: 'unknown' as Tone,
    description:
      'This route exists only if one or more unresolved (UNKNOWN) edges turn out to be usable. It is not confirmed.',
  },
  none: {
    label: 'No route',
    glyph: '○',
    tone: 'fail' as Tone,
    description: 'No route exists in the confirmed or the possible graph for this pair.',
  },
} as const

export type Reachability = keyof typeof REACHABILITY_META

export function reachabilityOf(confirmed: boolean, possible: boolean): Reachability {
  if (confirmed) return 'confirmed'
  if (possible) return 'possible'
  return 'none'
}

export const EDGE_ROLE_META = {
  confirmedRoute: { label: 'Confirmed route', glyph: '━', tone: 'pass' as Tone },
  possibleRoute: { label: 'Possible-only route', glyph: '┄', tone: 'unknown' as Tone },
  closed: { label: 'Closed for construction', glyph: '╳', tone: 'fail' as Tone },
  temporary: { label: 'Temporary connection', glyph: '◇', tone: 'temp' as Tone },
  selected: { label: 'Selected', glyph: '▣', tone: 'info' as Tone },
  default: { label: 'Footway', glyph: '─', tone: 'neutral' as Tone },
} as const