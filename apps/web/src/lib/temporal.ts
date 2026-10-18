/**
 * Temporal accessibility intelligence (Gate 4).
 *
 * Everything in this module is **presentation logic over results the backend has
 * already produced**. It compares two `AnalysisResult` payloads, classifies the
 * difference and explains it in words. It never evaluates a rule, never
 * predicts a route and never turns an unevaluated phase into a verdict.
 *
 * The rules that must hold here:
 *  - `NOT_ANALYSED` is not `PASS`, `FAIL` or `UNKNOWN`;
 *  - a possible-only route is never reported as confirmed;
 *  - an unknown never becomes a pass;
 *  - physical distance is only reported when the backend proved a route, and
 *    never aggregated across phases that are not comparable.
 */

import type { NormalisedAnalysisResult } from '@/api/normalize'
import type { PhaseTimelineEntry } from '@/api/types'

export type ReachabilityState = 'confirmed' | 'possible' | 'none'

export type TransitionKind =
  | 'unchanged-confirmed'
  | 'confirmed-to-possible'
  | 'confirmed-to-none'
  | 'possible-to-confirmed'
  | 'possible-to-none'
  | 'none-to-confirmed'
  | 'none-to-possible'
  | 'unchanged-possible'
  | 'unchanged-none'
  | 'not-evaluated'

export interface OdKey {
  origin_id: string
  destination_id: string
}

export function odKey(od: OdKey): string {
  return `${od.origin_id}|${od.destination_id}`
}

/** Reachability of one pair, taken verbatim from the backend result. */
export function reachabilityOf(result: NormalisedAnalysisResult, key: string): ReachabilityState {
  const pair = result.od_results.find((od) => odKey(od) === key)
  if (!pair) return 'none'
  if (pair.confirmed_reachable) return 'confirmed'
  if (pair.possibly_reachable) return 'possible'
  return 'none'
}

const TRANSITION_LABELS: Record<TransitionKind, string> = {
  'unchanged-confirmed': 'Still confirmed',
  'confirmed-to-possible': 'Lost its confirmed connection; possible-only now',
  'confirmed-to-none': 'No route at all',
  'possible-to-confirmed': 'Confirmed connection gained',
  'possible-to-none': 'Possible route lost entirely',
  'none-to-confirmed': 'Connected',
  'none-to-possible': 'Still not connected; possible-only',
  'unchanged-possible': 'Still possible-only',
  'unchanged-none': 'Still no route',
  'not-evaluated': 'Not evaluated',
}

export function transitionLabel(kind: TransitionKind): string {
  return TRANSITION_LABELS[kind]
}

/** True for transitions that make an engineer's answer materially different. */
export function isMaterialTransition(kind: TransitionKind): boolean {
  return (
    kind === 'confirmed-to-possible' ||
    kind === 'confirmed-to-none' ||
    kind === 'possible-to-confirmed' ||
    kind === 'none-to-confirmed'
  )
}

/**
 * Classify one pair between two phase results.
 *
 * `before`/`after` are nullable: a missing result means the phase was not
 * evaluated, which is reported as such and never as "no route".
 */
export function classifyTransition(
  before: NormalisedAnalysisResult | null,
  after: NormalisedAnalysisResult | null,
  key: string,
): TransitionKind {
  if (!before && !after) return 'not-evaluated'
  if (!before) {
    const to = reachabilityOf(after as NormalisedAnalysisResult, key)
    return to === 'confirmed' ? 'none-to-confirmed' : to === 'possible' ? 'none-to-possible' : 'unchanged-none'
  }
  if (!after) return 'not-evaluated'
  const from = reachabilityOf(before, key)
  const to = reachabilityOf(after, key)
  if (from === to) {
    return from === 'confirmed'
      ? 'unchanged-confirmed'
      : from === 'possible'
        ? 'unchanged-possible'
        : 'unchanged-none'
  }
  const key3 = `${from}-to-${to}` as TransitionKind
  return key3
}

export interface PhaseImpact {
  fromPhaseId: string
  toPhaseId: string
  fromOrder: number
  toOrder: number
  key: string
  originId: string
  destinationId: string
  kind: TransitionKind
  label: string
  material: boolean
  /** Phase-graph hashes, so the two states stay traceable to stored identities. */
  fromGraphHash: string | null
  toGraphHash: string | null
  /** Edges closed or opened between the two phases, as a *relevant change* set. */
  changedEdgeIds: string[]
  /** Only present when the backend actually proved a route in both phases. */
  distanceBefore: number | null
  distanceAfter: number | null
  findingsBefore: string[]
  findingsAfter: string[]
}

export interface TransitionInput {
  entry: PhaseTimelineEntry
  result: NormalisedAnalysisResult | null
}

/**
 * Impacts between successive phases in authoritative order.
 *
 * `changedEdgeIds` is reported as *relevant change*, never as proof of a unique
 * root cause: a route may depend on several edges at once, so the application
 * states what changed alongside what happened without claiming sole causation.
 */
export function computeImpacts(
  phases: readonly TransitionInput[],
  graphFor: (phaseId: string) => { closed: readonly string[]; temporary: readonly string[] } | null,
): PhaseImpact[] {
  const ordered = [...phases].sort((a, b) => a.entry.order - b.entry.order)
  const impacts: PhaseImpact[] = []
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1]!
    const current = ordered[index]!
    if (previous.result === null && current.result === null) continue
    const pairs = unionPairKeys(previous.result, current.result)
    const previousGraph = graphFor(previous.entry.phase_id)
    const currentGraph = graphFor(current.entry.phase_id)
    const changed = changedEdgeIds(previousGraph, currentGraph)

    for (const key of pairs) {
      const kind = classifyTransition(previous.result, current.result, key)
      const [originId = '', destinationId = ''] = key.split('|')
      const beforePair = previous.result?.od_results.find((od) => odKey(od) === key)
      const afterPair = current.result?.od_results.find((od) => odKey(od) === key)
      impacts.push({
        fromPhaseId: previous.entry.phase_id,
        toPhaseId: current.entry.phase_id,
        fromOrder: previous.entry.order,
        toOrder: current.entry.order,
        key,
        originId,
        destinationId,
        kind,
        label: transitionLabel(kind),
        material: isMaterialTransition(kind),
        fromGraphHash: previous.entry.phase_graph_hash,
        toGraphHash: current.entry.phase_graph_hash,
        changedEdgeIds: changed,
        distanceBefore:
          beforePair && beforePair.confirmed_reachable ? (beforePair.confirmed_distance_m ?? null) : null,
        distanceAfter:
          afterPair && afterPair.confirmed_reachable ? (afterPair.confirmed_distance_m ?? null) : null,
        findingsBefore: blockingFindingIds(beforePair),
        findingsAfter: blockingFindingIds(afterPair),
      })
    }
  }
  return impacts
}

function blockingFindingIds(pair: { blocking_finding_ids: string[] } | undefined): string[] {
  return pair ? [...pair.blocking_finding_ids] : []
}

function unionPairKeys(
  before: NormalisedAnalysisResult | null,
  after: NormalisedAnalysisResult | null,
): string[] {
  const keys = new Set<string>()
  for (const result of [before, after]) {
    for (const od of result?.od_results ?? []) keys.add(odKey(od))
  }
  return [...keys].sort()
}

/**
 * Edges whose active state differs between two phases.
 *
 * Derived from the authoritative closure and temporary-edge sets, never from
 * geometry or screen position.
 */
export function changedEdgeIds(
  before: { closed: readonly string[]; temporary: readonly string[] } | null,
  after: { closed: readonly string[]; temporary: readonly string[] } | null,
): string[] {
  if (!before || !after) return []
  const state = (entry: { closed: readonly string[]; temporary: readonly string[] }) => {
    const map = new Map<string, string>()
    for (const id of entry.closed) map.set(id, 'closed')
    for (const id of entry.temporary) map.set(id, 'temporary')
    return map
  }
  const a = state(before)
  const b = state(after)
  const changed = new Set<string>()
  for (const [id, value] of a) {
    if (b.get(id) !== value) changed.add(id)
  }
  for (const [id, value] of b) {
    if (a.get(id) !== value) changed.add(id)
  }
  return [...changed].sort()
}

export type ContinuityState =
  | 'continuously-confirmed'
  | 'interrupted'
  | 'uncertain'
  | 'incomplete'

export interface ContinuityReport {
  key: string
  originId: string
  destinationId: string
  state: ContinuityState
  label: string
  description: string
  /** Phase ids in authoritative order, one entry per evaluated phase. */
  perPhase: { phaseId: string; order: number; reachability: ReachabilityState | 'not-evaluated' }[]
  /** First phase whose state is worse than confirmed, if any. */
  firstProblemPhaseId: string | null
  /** Phases with no usable analysis. They block a "continuously confirmed" claim. */
  unevaluatedPhaseIds: string[]
  blockingPhaseIds: string[]
  unknownPhaseIds: string[]
}

const CONTINUITY_META: Record<ContinuityState, { label: string; description: string }> = {
  'continuously-confirmed': {
    label: 'Continuously confirmed',
    description:
      'A confirmed route exists in every evaluated phase. This is a statement about the modeled checks and the available evidence at the evaluation instant, not about legal compliance.',
  },
  interrupted: {
    label: 'Interrupted',
    description: 'At least one evaluated phase has no route at all for this pair.',
  },
  uncertain: {
    label: 'Uncertain continuity',
    description:
      'No phase has lost the route outright, but at least one phase depends on unresolved conditions, so the sequence cannot be called continuously confirmed.',
  },
  incomplete: {
    label: 'Incomplete evaluation',
    description:
      'At least one phase has no usable analysis. An unevaluated phase is never counted as a pass or a failure.',
  },
}

/**
 * Cross-phase continuity for one pair.
 *
 * Invariants enforced here:
 *  - a single possible-only phase prevents `continuously-confirmed`;
 *  - a single `none` phase produces `interrupted`;
 *  - any unevaluated phase prevents `continuously-confirmed`;
 *  - unevaluated phases are reported separately rather than being treated as
 *    either safe or unsafe.
 */
export function computeContinuity(
  key: string,
  phases: readonly TransitionInput[],
): ContinuityReport {
  const ordered = [...phases].sort((a, b) => a.entry.order - b.entry.order)
  const [originId = '', destinationId = ''] = key.split('|')
  const perPhase: ContinuityReport['perPhase'] = []
  const unevaluated: string[] = []
  const blocking: string[] = []
  const unknown: string[] = []
  let firstProblem: string | null = null

  for (const phase of ordered) {
    if (!phase.result) {
      perPhase.push({ phaseId: phase.entry.phase_id, order: phase.entry.order, reachability: 'not-evaluated' })
      unevaluated.push(phase.entry.phase_id)
      // An unevaluated phase is the first place a reviewer must act, so it counts
      // as the first problem. The continuity *state* stays `incomplete`: it is
      // never treated as a failure, only as a gap in what has been verified.
      if (firstProblem === null) firstProblem = phase.entry.phase_id
      continue
    }
    const reachability = reachabilityOf(phase.result, key)
    perPhase.push({ phaseId: phase.entry.phase_id, order: phase.entry.order, reachability })
    if (reachability === 'none') {
      blocking.push(phase.entry.phase_id)
      if (firstProblem === null) firstProblem = phase.entry.phase_id
    } else if (reachability === 'possible') {
      unknown.push(phase.entry.phase_id)
      if (firstProblem === null) firstProblem = phase.entry.phase_id
    }
  }

  const state: ContinuityState =
    unevaluated.length > 0 ? 'incomplete' : blocking.length > 0 ? 'interrupted' : unknown.length > 0 ? 'uncertain' : 'continuously-confirmed'

  return {
    key,
    originId,
    destinationId,
    state,
    label: CONTINUITY_META[state].label,
    description: CONTINUITY_META[state].description,
    perPhase,
    firstProblemPhaseId: firstProblem,
    unevaluatedPhaseIds: unevaluated,
    blockingPhaseIds: blocking,
    unknownPhaseIds: unknown,
  }
}

/**
 * The earliest phase in authoritative order where a pair stops being confirmed.
 *
 * Uses `Phase.order`, never the position in a list or the phase id.
 */
export function firstProblematicPhase(
  key: string,
  phases: readonly TransitionInput[],
): { phaseId: string | null; report: ContinuityReport } {
  const report = computeContinuity(key, phases)
  return { phaseId: report.firstProblemPhaseId, report }
}

/**
 * Explain the first problem in words from actual data.
 *
 * The text describes what changed between the last good phase and the first
 * problematic one; it does not assert a unique physical cause.
 */
export function explainFirstProblem(
  key: string,
  phases: readonly TransitionInput[],
  graphFor: (phaseId: string) => { closed: readonly string[]; temporary: readonly string[] } | null,
): string | null {
  const ordered = [...phases].sort((a, b) => a.entry.order - b.entry.order)
  const { phaseId, report } = firstProblematicPhase(key, ordered)
  if (phaseId === null) return null

  const index = ordered.findIndex((phase) => phase.entry.phase_id === phaseId)
  const problem = ordered[index]
  const previous = index > 0 ? ordered[index - 1] : undefined
  if (!problem) return null

  const reachability = report.perPhase.find((entry) => entry.phaseId === phaseId)?.reachability
  const beforeState = previous?.result ? reachabilityOf(previous.result, key) : null
  const transition = classifyTransition(previous?.result ?? null, problem.result, key)
  const changed = changedEdgeIds(
    previous ? graphFor(previous.entry.phase_id) : null,
    graphFor(problem.entry.phase_id),
  )
  const reason =
    reachability === 'not-evaluated'
      ? 'it has no usable analysis'
      : reachability === 'none'
        ? 'no route exists in either the confirmed or the possible graph'
        : 'the remaining route depends on unresolved evidence'

  const changedText =
    changed.length > 0
      ? ` Between those phases the active network changed on ${changed.length} edge(s): ${changed.join(', ')}.`
      : ''

  // The first phase has no predecessor: say so plainly instead of inventing one.
  const lead =
    previous === undefined
      ? `${key.replace('|', ' → ')} is already ${describe(reachability)} in the earliest declared phase, ${problem.entry.label || problem.entry.phase_id}, because ${reason}.`
      : `${key.replace('|', ' → ')} is ${describe(beforeState)} in ${previous.entry.label || previous.entry.phase_id} and becomes ${describe(reachability)} in ${problem.entry.label || problem.entry.phase_id} because ${reason}. ${transitionLabel(transition)}.`

  return `${lead}${changedText}`.trim()
}

function describe(state: ReachabilityState | 'not-evaluated' | null | undefined): string {
  if (state === 'confirmed') return 'model-confirmed'
  if (state === 'possible') return 'possible-only'
  if (state === 'none') return 'unreachable'
  return 'not evaluated'
}