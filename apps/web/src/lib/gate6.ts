/**
 * Presentation metadata for Gate 6 surfaces.
 *
 * Every label here is *display wording only*. The machine-readable
 * `resolution_status`, `observation` and `criticality` values always travel
 * alongside it, so a translated or re-worded label can never change what the
 * system says happened.
 *
 * No entry here carries a number that was not computed by the backend.
 */

import type { EngineeringObservation, EvidenceCriticality, FaultKind } from '@/api/types'

export type Tone = 'pass' | 'fail' | 'unknown' | 'neutral' | 'info' | 'temp'

export interface StatusMeta {
  label: string
  /** A second, non-colour signal: shown alongside the label, never instead. */
  glyph: string
  tone: Tone
  description: string
}

/** The five evidence-resolution conditions the resolver can return. */
export const EVIDENCE_STATUS_META: Record<string, StatusMeta> = {
  NO_EVIDENCE: {
    label: 'No observation recorded',
    glyph: '○',
    tone: 'unknown',
    description:
      'No eligible observation exists for this attribute. The modelled check cannot return a known ' +
      'result. This is missing information, not evidence that the element is unsuitable.',
  },
  CONFLICTING_EVIDENCE: {
    label: 'Observations disagree',
    glyph: '≠',
    tone: 'fail',
    description:
      'Two or more eligible observations disagree after canonical unit conversion. Every claim is ' +
      'retained and none is selected, averaged, or preferred because it would pass.',
  },
  UNSUPPORTED_UNIT: {
    label: 'Unsupported unit',
    glyph: '⚠',
    tone: 'fail',
    description:
      'At least one observation cannot be read in the unit the rulepack declares. The attribute is ' +
      'unknown - never zero and never passing.',
  },
  EVIDENCE_EXPIRED: {
    label: 'Stale under freshness policy',
    glyph: '⏱',
    tone: 'unknown',
    description:
      'The observation is older than the freshness policy the rulepack declares for this attribute, ' +
      'or its age cannot be established.',
  },
  EVIDENCE_NOT_VERIFIED: {
    label: 'Observation not verified',
    glyph: '◇',
    tone: 'unknown',
    description:
      'The rulepack requires verified evidence and the eligible observation is not verified. ' +
      'Entering the value again does not verify it.',
  },
}

export const EVIDENCE_STATUS_FALLBACK: StatusMeta = {
  label: 'Unresolved attribute',
  glyph: '○',
  tone: 'unknown',
  description: 'The resolver could not return a determined value. See its explanation.',
}

export function evidenceStatusMeta(reasonCode: string | null | undefined): StatusMeta {
  return (reasonCode && EVIDENCE_STATUS_META[reasonCode]) || EVIDENCE_STATUS_FALLBACK
}

/**
 * Decision-relevance categories.
 *
 * The wording deliberately avoids "risk", "confidence" and "importance" score
 * language: the category describes what the modelled decision is waiting on, not
 * how likely a field visit is to succeed.
 */
export const CRITICALITY_META: Record<string, StatusMeta> = {
  decision_blocking: {
    label: 'Decision-blocking',
    glyph: '■',
    tone: 'fail',
    description:
      'The current analysis demonstrated this element as a blocker for an origin-destination pair ' +
      'that is not model-confirmed reachable.',
  },
  decision_relevant: {
    label: 'Decision-relevant',
    glyph: '▲',
    tone: 'unknown',
    description:
      'The attribute sits on a confirmed route, on a possible-only route, or affects more than one ' +
      'selected mobility profile.',
  },
  supporting: {
    label: 'Supporting',
    glyph: '▪',
    tone: 'neutral',
    description:
      'Unresolved for a rule in scope, but not currently linked to a selected origin-destination ' +
      'outcome.',
  },
}

export function criticalityMeta(criticality: EvidenceCriticality | string): StatusMeta {
  return CRITICALITY_META[criticality] ?? EVIDENCE_STATUS_FALLBACK
}

/** What the authoritative engine reported about a pair under a fault. */
export const OBSERVATION_META: Record<string, StatusMeta> = {
  confirmed_connectivity_preserved: {
    label: 'Confirmed connectivity preserved',
    glyph: '✓',
    tone: 'pass',
    description: 'A model-confirmed route exists after the injected condition, exactly as before.',
  },
  confirmed_connectivity_gained: {
    label: 'Confirmed connectivity gained',
    glyph: '⇧',
    tone: 'info',
    description:
      'The pair gained a model-confirmed route under the injected condition. Reported explicitly so ' +
      'it is not mistaken for "nothing changed".',
  },
  confirmed_connectivity_lost: {
    label: 'Confirmed connectivity lost',
    glyph: '✕',
    tone: 'fail',
    description:
      'The pair had a model-confirmed route before the injected condition and has none after it. This ' +
      'is a modelled disconnection, not an observation about the physical network.',
  },
  confirmed_route_became_possible_only: {
    label: 'Confirmed route became possible-only',
    glyph: '◐',
    tone: 'unknown',
    description:
      'The pair lost its model-confirmed route but a hypothetical route still exists. This is NOT ' +
      'confirmed accessibility.',
  },
  possible_only_route_became_disconnected: {
    label: 'Possible-only route disconnected',
    glyph: '⊘',
    tone: 'fail',
    description:
      'The pair previously had a hypothetical route that assumed unknown edges were usable and now ' +
      'has none.',
  },
  new_known_rule_violation: {
    label: 'New known rule violation',
    glyph: '!',
    tone: 'fail',
    description:
      'The injected condition introduced a rule violation the rulepack can decide. A known modelled ' +
      'failure, distinct from any unresolved condition.',
  },
  new_unresolved_evidence_condition: {
    label: 'New unresolved evidence condition',
    glyph: '?',
    tone: 'unknown',
    description:
      'The injected condition introduced an attribute the rulepack cannot resolve. Unknown is not a ' +
      'pass and not a fail.',
  },
  no_relevant_modelled_change: {
    label: 'No relevant modelled change',
    glyph: '=',
    tone: 'neutral',
    description: "The injected condition did not change this pair's connectivity or any verdict for it.",
  },
  analysis_unavailable: {
    label: 'Analysis unavailable',
    glyph: '∅',
    tone: 'neutral',
    description:
      'The engine returned no result. That is a software outcome, not evidence that the network ' +
      'failed.',
  },
}

export function observationMeta(observation: EngineeringObservation | string): StatusMeta {
  return OBSERVATION_META[observation] ?? EVIDENCE_STATUS_FALLBACK
}

/** Whether an execution outcome is a statement about the software or the plan. */
export const EXECUTION_STATUS_META: Record<string, StatusMeta> = {
  completed: {
    label: 'Completed',
    glyph: '✓',
    tone: 'pass',
    description: 'Every selected phase and profile produced a baseline and a faulted analysis.',
  },
  partially_completed: {
    label: 'Partially completed',
    glyph: '◐',
    tone: 'unknown',
    description:
      'Some analyses completed and some did not. The unavailable ones are reported as unavailable ' +
      'and are excluded from every robustness count.',
  },
  invalid_experiment: {
    label: 'Invalid experiment',
    glyph: '⊘',
    tone: 'fail',
    description:
      'The fault could not be represented safely, so nothing was executed. This condition was NOT tested.',
  },
  execution_failed: {
    label: 'Execution failed',
    glyph: '✕',
    tone: 'fail',
    description:
      'The software could not complete the experiment. This is evidence about the system, never about the plan.',
  },
  cancelled: { label: 'Cancelled', glyph: '—', tone: 'neutral', description: 'The experiment did not finish.' },
}

export function executionStatusMeta(status: string): StatusMeta {
  return EXECUTION_STATUS_META[status] ?? EVIDENCE_STATUS_FALLBACK
}

/** Short label for a fault kind, used in tables and history rows. */
export const FAULT_KIND_LABEL: Record<FaultKind, string> = {
  edge_closure: 'Edge closure',
  temporary_connection_loss: 'Temporary connection loss',
  evidence_removal: 'Missing observation',
  conflicting_observation: 'Conflicting observation',
  evidence_expiration: 'Stale observation',
  unsupported_unit_observation: 'Unsupported unit',
  path_obstruction: 'Modelled obstruction',
}

/** A short, plain-language reachability description used in every comparison. */
export function reachabilityOf(confirmed: boolean, possible: boolean): string {
  if (confirmed) return 'confirmed'
  if (possible) return 'possible-only'
  return 'no route'
}

/** Render a distance that may legitimately not exist. Never substitutes zero. */
export function formatDistance(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'not established'
  return `${Number(value).toFixed(1)} m`
}

/** Render a possibly-unknown cost. Never substitutes zero. */
export function formatOptionalCost(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined) return 'Not estimated'
  return `${Number(value).toFixed(0)} ${currency ?? ''}`.trim()
}