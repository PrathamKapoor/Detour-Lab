import { describe, expect, it } from 'vitest'
import { normaliseAnalysisResult } from '@/api/normalize'
import type { PhaseTimelineEntry } from '@/api/types'
import {
  changedEdgeIds,
  classifyTransition,
  computeContinuity,
  computeImpacts,
  explainFirstProblem,
  firstProblematicPhase,
  isMaterialTransition,
  reachabilityOf,
  type TransitionInput,
} from '@/lib/temporal'

function phase(
  phaseId: string,
  order: number,
  overrides: Partial<PhaseTimelineEntry> = {},
): PhaseTimelineEntry {
  return {
    phase_id: phaseId,
    order,
    label: `Phase ${order}`,
    notes: '',
    boundary_convention: 'logical_ordinal',
    closed_edge_ids: [],
    temporary_edge_ids: [],
    phase_graph_id: `g~phase:${phaseId}`,
    phase_graph_hash: `sha256:${phaseId}`,
    warnings: [],
    analysis: {
      analysed: false,
      state: 'NOT_ANALYSED',
      run_id: null,
      profile_id: null,
      semantic_hash: null,
      scenario_revision: null,
      stale: false,
    },
    ...overrides,
  }
}

type Pair = [string, boolean, boolean]

/** Builds a realistic result payload; reachability comes from the pairs given. */
function result(pairs: Pair[]): ReturnType<typeof normaliseAnalysisResult> {
  return normaliseAnalysisResult({
    scenario_id: 'scn',
    phase_id: 'p',
    profile_id: 'DEMO_PROFILE_MANUAL_WHEELCHAIR',
    rulepack_id: 'DEMO_RULEPACK_NOT_LEGAL',
    edge_evaluations: [],
    verdicts: [],
    counts: {},
    od_results: pairs.map(([key, confirmed, possible]) => {
      const [origin_id, destination_id] = key.split('|')
      return {
        origin_id,
        destination_id,
        confirmed_reachable: confirmed,
        possibly_reachable: possible,
        confirmed_distance_m: confirmed ? 58 : null,
        blocking_finding_ids: [],
      }
    }),
  })
}

const graphFor = (map: Record<string, { closed: string[]; temporary: string[] }>) => (phaseId: string) =>
  map[phaseId] ?? null

describe('reachability of a stored result', () => {
  it('reports exactly what the backend proved', () => {
    const stored = result([
      ['OD-W|OD-GATE', true, true],
      ['OD-E|OD-LIB', false, true],
      ['OD-E|OD-GATE', false, false],
    ])
    expect(reachabilityOf(stored, 'OD-W|OD-GATE')).toBe('confirmed')
    expect(reachabilityOf(stored, 'OD-E|OD-LIB')).toBe('possible')
    expect(reachabilityOf(stored, 'OD-E|OD-GATE')).toBe('none')
  })

  it('does not invent a result for a pair the backend never returned', () => {
    const stored = result([['OD-W|OD-GATE', true, true]])
    expect(reachabilityOf(stored, 'OD-Z|OD-UNKNOWN')).toBe('none')
  })
})

describe('transition classification', () => {
  const cases: [string, [boolean, boolean], [boolean, boolean], string][] = [
    ['confirmed -> confirmed', [true, true], [true, true], 'unchanged-confirmed'],
    ['confirmed -> possible-only', [true, true], [false, true], 'confirmed-to-possible'],
    ['confirmed -> no route', [true, true], [false, false], 'confirmed-to-none'],
    ['possible-only -> confirmed', [false, true], [true, true], 'possible-to-confirmed'],
    ['possible-only -> no route', [false, true], [false, false], 'possible-to-none'],
    ['no route -> confirmed', [false, false], [true, true], 'none-to-confirmed'],
    ['no route -> possible-only', [false, false], [false, true], 'none-to-possible'],
    ['possible-only unchanged', [false, true], [false, true], 'unchanged-possible'],
    ['no route unchanged', [false, false], [false, false], 'unchanged-none'],
  ]

  it.each(cases)('%s', (_name, before, after, expected) => {
    const from = result([['OD-W|OD-LIB', before[0], before[1]]])
    const to = result([['OD-W|OD-LIB', after[0], after[1]]])
    expect(classifyTransition(from, to, 'OD-W|OD-LIB')).toBe(expected)
  })

  it('never classifies a missing analysis as a disconnection', () => {
    const stored = result([['OD-W|OD-LIB', true, true]])
    expect(classifyTransition(null, null, 'OD-W|OD-LIB')).toBe('not-evaluated')
    expect(classifyTransition(stored, null, 'OD-W|OD-LIB')).toBe('not-evaluated')
    expect(classifyTransition(null, stored, 'OD-W|OD-LIB')).toBe('none-to-confirmed')
  })

  it('marks only reachability-changing transitions as material', () => {
    expect(isMaterialTransition('confirmed-to-possible')).toBe(true)
    expect(isMaterialTransition('confirmed-to-none')).toBe(true)
    expect(isMaterialTransition('possible-to-confirmed')).toBe(true)
    expect(isMaterialTransition('unchanged-confirmed')).toBe(false)
    expect(isMaterialTransition('unchanged-possible')).toBe(false)
    expect(isMaterialTransition('not-evaluated')).toBe(false)
  })
})

describe('phase impacts', () => {
  it('compares successive phases in authoritative order, not array order', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-2', 2), result: result([['OD-W|OD-LIB', false, false]]) },
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
    ]
    const impacts = computeImpacts(inputs, graphFor({}))
    expect(impacts).toHaveLength(1)
    expect(impacts[0]).toMatchObject({
      fromPhaseId: 'phase-1',
      toPhaseId: 'phase-2',
      kind: 'confirmed-to-none',
      material: true,
    })
  })

  it('reports changed edges from the authoritative sets, never from geometry', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
      {
        entry: phase('phase-2', 2, { closed_edge_ids: ['E_ES1'] }),
        result: result([['OD-W|OD-LIB', false, false]]),
      },
    ]
    const graphs = graphFor({
      'phase-1': { closed: ['E_ME'], temporary: [] },
      'phase-2': { closed: ['E_ME', 'E_ES1'], temporary: ['TMP-X'] },
    })
    const impacts = computeImpacts(inputs, graphs)
    expect(impacts[0]?.changedEdgeIds).toEqual(['E_ES1', 'TMP-X'])
  })

  it('reports distance only when a route was actually proven on both sides', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
      { entry: phase('phase-2', 2), result: result([['OD-W|OD-LIB', false, true]]) },
    ]
    const impacts = computeImpacts(inputs, graphFor({}))
    expect(impacts[0]?.distanceBefore).toBe(58)
    // The later phase has no confirmed route: no distance may be invented.
    expect(impacts[0]?.distanceAfter).toBeNull()
  })

  it('skips pairs entirely when neither phase was evaluated', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: null },
      { entry: phase('phase-2', 2), result: null },
    ]
    expect(computeImpacts(inputs, graphFor({}))).toEqual([])
  })

  it('carries the phase-graph hashes so both states stay traceable', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
      {
        entry: phase('phase-2', 2, { phase_graph_hash: 'sha256:second' }),
        result: result([['OD-W|OD-LIB', false, false]]),
      },
    ]
    const impacts = computeImpacts(inputs, graphFor({}))
    expect(impacts[0]?.fromGraphHash).toBe('sha256:phase-1')
    expect(impacts[0]?.toGraphHash).toBe('sha256:second')
  })
})

describe('changed edges', () => {
  it('detects closures that open again', () => {
    expect(
      changedEdgeIds({ closed: ['E_A'], temporary: [] }, { closed: [], temporary: [] }),
    ).toEqual(['E_A'])
  })

  it('detects a temporary connection appearing', () => {
    expect(
      changedEdgeIds({ closed: [], temporary: [] }, { closed: [], temporary: ['TMP-X'] }),
    ).toEqual(['TMP-X'])
  })

  it('returns nothing when a phase graph is unknown', () => {
    expect(changedEdgeIds(null, { closed: [], temporary: [] })).toEqual([])
  })

  it('returns nothing when both phases are identical', () => {
    expect(
      changedEdgeIds({ closed: ['E_A'], temporary: [] }, { closed: ['E_A'], temporary: [] }),
    ).toEqual([])
  })
})

describe('cross-phase continuity', () => {
  const threePhases = (results: (ReturnType<typeof normaliseAnalysisResult> | null)[]): TransitionInput[] =>
    results.map((stored, index) => ({
      entry: phase(`phase-${index + 1}`, index + 1),
      result: stored,
    }))

  it('is continuously confirmed only when every phase is confirmed', () => {
    const report = computeContinuity(
      'OD-W|OD-LIB',
      threePhases([
        result([['OD-W|OD-LIB', true, true]]),
        result([['OD-W|OD-LIB', true, true]]),
        result([['OD-W|OD-LIB', true, true]]),
      ]),
    )
    expect(report.state).toBe('continuously-confirmed')
    expect(report.firstProblemPhaseId).toBeNull()
  })

  it('a single no-route phase makes the sequence interrupted', () => {
    const report = computeContinuity(
      'OD-W|OD-LIB',
      threePhases([
        result([['OD-W|OD-LIB', true, true]]),
        result([['OD-W|OD-LIB', false, false]]),
        result([['OD-W|OD-LIB', true, true]]),
      ]),
    )
    expect(report.state).toBe('interrupted')
    expect(report.blockingPhaseIds).toEqual(['phase-2'])
  })

  it('a single possible-only phase prevents a continuously-confirmed claim', () => {
    const report = computeContinuity(
      'OD-W|OD-LIB',
      threePhases([
        result([['OD-W|OD-LIB', true, true]]),
        result([['OD-W|OD-LIB', false, true]]),
        result([['OD-W|OD-LIB', true, true]]),
      ]),
    )
    expect(report.state).toBe('uncertain')
    expect(report.state).not.toBe('continuously-confirmed')
    expect(report.unknownPhaseIds).toEqual(['phase-2'])
  })

  it('an unevaluated phase is incomplete, never a pass and never a failure', () => {
    const report = computeContinuity(
      'OD-W|OD-LIB',
      threePhases([result([['OD-W|OD-LIB', true, true]]), null, result([['OD-W|OD-LIB', true, true]])]),
    )
    expect(report.state).toBe('incomplete')
    expect(report.unevaluatedPhaseIds).toEqual(['phase-2'])
    expect(report.blockingPhaseIds).toEqual([])
    expect(report.perPhase[1]?.reachability).toBe('not-evaluated')
  })

  it('identifies the first problem using Phase.order, not list position', () => {
    const report = computeContinuity('OD-W|OD-LIB', [
      { entry: phase('phase-late', 9), result: result([['OD-W|OD-LIB', false, false]]) },
      { entry: phase('phase-early', 1), result: result([['OD-W|OD-LIB', true, true]]) },
    ])
    expect(report.perPhase.map((entry) => entry.phaseId)).toEqual(['phase-early', 'phase-late'])
    expect(report.firstProblemPhaseId).toBe('phase-late')
  })

  it('handles non-contiguous orders without confusion', () => {
    const report = computeContinuity('OD-W|OD-LIB', [
      { entry: phase('phase-b', 20), result: result([['OD-W|OD-LIB', false, false]]) },
      { entry: phase('phase-a', 10), result: result([['OD-W|OD-LIB', true, true]]) },
    ])
    expect(report.perPhase.map((entry) => entry.order)).toEqual([10, 20])
    expect(report.firstProblemPhaseId).toBe('phase-b')
  })

  it('firstProblematicPhase returns null when nothing is wrong', () => {
    const { phaseId } = firstProblematicPhase(
      'OD-W|OD-LIB',
      threePhases([result([['OD-W|OD-LIB', true, true]])]),
    )
    expect(phaseId).toBeNull()
  })
})

describe('first-problem explanation', () => {
  it('explains a confirmed-to-possible-only transition from real data', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1, { label: 'Phase 1 - resurfacing' }), result: result([['OD-E|OD-LIB', true, true]]) },
      {
        entry: phase('phase-2', 2, { label: 'Phase 2 - east link', closed_edge_ids: ['E_ES1'] }),
        result: result([['OD-E|OD-LIB', false, true]]),
      },
    ]
    const text = explainFirstProblem(
      'OD-E|OD-LIB',
      inputs,
      graphFor({
        'phase-1': { closed: ['E_ME'], temporary: [] },
        'phase-2': { closed: ['E_ME', 'E_ES1'], temporary: [] },
      }),
    )
    expect(text).toContain('OD-E → OD-LIB')
    expect(text).toContain('Phase 1 - resurfacing')
    expect(text).toContain('Phase 2 - east link')
    expect(text).toContain('unresolved evidence')
    expect(text).toContain('E_ES1')
  })

  it('reports no explanation when every phase is confirmed', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
      { entry: phase('phase-2', 2), result: result([['OD-W|OD-LIB', true, true]]) },
    ]
    expect(explainFirstProblem('OD-W|OD-LIB', inputs, graphFor({}))).toBeNull()
  })

  it('says so plainly when the first problem is a missing analysis', () => {
    const inputs: TransitionInput[] = [
      { entry: phase('phase-1', 1), result: result([['OD-W|OD-LIB', true, true]]) },
      { entry: phase('phase-2', 2), result: null },
    ]
    const text = explainFirstProblem('OD-W|OD-LIB', inputs, graphFor({}))
    expect(text).toContain('no usable analysis')
  })
})