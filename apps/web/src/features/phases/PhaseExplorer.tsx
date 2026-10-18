import { useMemo } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { GraphCanvas } from '@/features/network/GraphCanvas'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import type { PhaseTimelineEntry } from '@/api/types'
import { formatHash } from '@/lib/format'
import {
  computeContinuity,
  computeImpacts,
  explainFirstProblem,
  reachabilityOf,
  type ContinuityReport,
  type TransitionInput,
} from '@/lib/temporal'

/**
 * Construction Phase Explorer (Gate 4, G4-01/G4-02/G4-04).
 *
 * Ordering, closures, temporary connections and the phase graph all come from
 * the backend. The phase sequence is an *ordered list*, never a calendar: no
 * dates, durations or scheduling exist anywhere in this component.
 */
export function PhaseExplorer() {
  const {
    timelineLoading,
    timelineError,
    reloadTimeline,
    orderedPhases,
    selectedPhaseId,
    selectPhase,
    phaseGraph,
    phaseGraphLoading,
    phaseGraphError,
    phaseResults,
    evaluateAllPhases,
    evaluatePhase,
    evaluatingPhases,
    batchError,
    profileId,
    graphFor,
    selectEdge,
    setView,
  } = useWorkspace()

  const index = orderedPhases.findIndex((phase) => phase.phase_id === selectedPhaseId)
  const selected = index >= 0 ? orderedPhases[index]! : null

  const transitionInputs = useMemo<TransitionInput[]>(
    () =>
      orderedPhases.map((entry) => ({
        entry,
        result: phaseResults[entry.phase_id] ?? null,
      })),
    [orderedPhases, phaseResults],
  )

  const impacts = useMemo(() => computeImpacts(transitionInputs, graphFor), [transitionInputs, graphFor])

  const continuity = useMemo<ContinuityReport[]>(() => {
    const keys = new Set<string>()
    for (const input of transitionInputs) {
      for (const od of input.result?.od_results ?? []) keys.add(`${od.origin_id}|${od.destination_id}`)
    }
    return [...keys].sort().map((key) => computeContinuity(key, transitionInputs))
  }, [transitionInputs])

  if (timelineLoading) return <Spinner label="Loading construction timeline" />
  if (timelineError) {
    return (
      <ErrorPanel
        title="Cannot load the construction timeline"
        code={timelineError.code}
        message={timelineError.userMessage}
        action={<Button onClick={reloadTimeline}>Retry</Button>}
      />
    )
  }
  if (orderedPhases.length === 0) {
    return (
      <EmptyState
        title="This scenario declares no phases"
        description="A construction scenario must declare at least one phase before it can be evaluated."
      />
    )
  }

  const go = (offset: number) => {
    const next = orderedPhases[index + offset]
    if (next) selectPhase(next.phase_id)
  }

  return (
    <div className="phases">
      <Panel
        title="Construction phases"
        subtitle={`${orderedPhases.length} phase(s) in authoritative order · profile ${profileId}`}
        actions={
          <>
            <Button
              onClick={() => go(-1)}
              disabled={index <= 0}
              aria-label="Previous phase"
              data-testid="phase-prev"
            >
              ← Previous
            </Button>
            <Button
              onClick={() => go(1)}
              disabled={index >= orderedPhases.length - 1}
              aria-label="Next phase"
              data-testid="phase-next"
            >
              Next →
            </Button>
            <Button
              variant="primary"
              onClick={() => void evaluateAllPhases()}
              busy={Object.values(evaluatingPhases).some((state) => state === 'running')}
              data-testid="evaluate-all-phases"
            >
              Evaluate all phases
            </Button>
          </>
        }
      >
        <ol className="phase-rail" data-testid="phase-rail" aria-label="Construction phases in order">
          {orderedPhases.map((phase) => (
            <li key={phase.phase_id}>
              <PhaseMarker
                phase={phase}
                selected={phase.phase_id === selectedPhaseId}
                analysed={Boolean(phaseResults[phase.phase_id])}
                state={evaluatingPhases[phase.phase_id] ?? null}
                onSelect={() => selectPhase(phase.phase_id)}
              />
            </li>
          ))}
        </ol>

        {batchError ? (
          <ErrorPanel
            title="Some phases could not be evaluated"
            code={batchError.code}
            message={batchError.userMessage}
            action={<Button onClick={() => void evaluateAllPhases()}>Retry the whole sequence</Button>}
          />
        ) : null}
      </Panel>

      <div className="phases__grid">
        <Panel
          title={selected ? `${selected.label || selected.phase_id}` : 'Phase'}
          subtitle={
            selected
              ? `order ${selected.order} · ${selected.closed_edge_ids.length} closure(s) · ${selected.temporary_edge_ids.length} temporary connection(s)`
              : undefined
          }
          actions={
            selected ? (
              <Button
                onClick={() => void evaluatePhase(selected.phase_id)}
                busy={evaluatingPhases[selected.phase_id] === 'running'}
                data-testid="evaluate-phase"
              >
                Evaluate this phase
              </Button>
            ) : null
          }
        >
          {selected ? <PhaseDetails phase={selected} hasResult={Boolean(phaseResults[selected.phase_id])} /> : null}
        </Panel>

        <Panel title="Phase graph" subtitle="Served by the backend; closures are never inferred locally">
          {phaseGraphLoading ? <Spinner label="Loading phase graph" /> : null}
          {phaseGraphError ? (
            <ErrorPanel
              title="Cannot load the phase graph"
              code={phaseGraphError.code}
              message={phaseGraphError.userMessage}
              action={<Button onClick={() => setView('network')}>Open the network studio</Button>}
            />
          ) : null}
          {phaseGraph && !phaseGraphLoading ? (
            <>
              <KeyValueList
                items={[
                  { term: 'Phase graph id', value: <span className="mono">{phaseGraph.phase_graph_id}</span> },
                  { term: 'Phase hash', value: <span className="mono">{formatHash(phaseGraph.phase_graph_hash, 20)}</span> },
                  { term: 'Scenario revision', value: String(phaseGraph.scenario_revision) },
                  { term: 'Closed edges', value: phaseGraph.closed_edge_ids.join(', ') || 'none' },
                  { term: 'Active temporary', value: phaseGraph.active_temporary_edge_ids.join(', ') || 'none' },
                ]}
              />
              <GraphCanvas
                nodes={phaseGraph.nodes}
                edges={phaseGraph.edges}
                crossings={phaseGraph.crossings}
                overlays={{
                  confirmedRouteEdgeIds: [],
                  possibleRouteEdgeIds: [],
                  closedEdgeIds: phaseGraph.closed_edge_ids,
                  temporaryEdgeIds: phaseGraph.edges.filter((edge) => edge.temporary).map((edge) => edge.id),
                }}
                onSelectEdge={selectEdge}
                height={360}
                ariaLabel={`Pedestrian network during ${phaseGraph.phase_label || phaseGraph.phase_id}`}
              />
              <p className="inspector__note">
                A closed edge is still drawn so its position stays legible, but it is excluded from
                routing: visibility never implies traversability.
              </p>
            </>
          ) : null}
        </Panel>
      </div>

      <Panel
        title="Accessibility continuity across the sequence"
        subtitle="Cross-phase summary; it does not replace the per-phase four-valued rule results"
        flush
      >
        <ContinuityMatrix continuity={continuity} phases={orderedPhases} />
      </Panel>

      <Panel
        title="Temporal findings"
        subtitle="What changed between successive phases, and the evidence behind it"
        flush
      >
        <TemporalFindings impacts={impacts} continuity={continuity} transitionInputs={transitionInputs} graphFor={graphFor} />
      </Panel>
    </div>
  )
}

function PhaseMarker({
  phase,
  selected,
  analysed,
  state,
  onSelect,
}: {
  phase: PhaseTimelineEntry
  selected: boolean
  analysed: boolean
  state: 'running' | 'done' | 'failed' | null
  onSelect: () => void
}) {
  const glyph = state === 'running' ? '…' : analysed ? '◆' : '○'
  const status = state === 'failed' ? 'Evaluation failed' : analysed ? 'Analysed' : 'NOT ANALYSED'
  return (
    <button
      type="button"
      className={`phase-marker ${selected ? 'phase-marker--selected' : ''}`}
      aria-current={selected ? 'step' : undefined}
      aria-pressed={selected}
      onClick={onSelect}
      data-testid={`phase-marker-${phase.phase_id}`}
      title={`${phase.label || phase.phase_id} — ${status}`}
    >
      <span className="phase-marker__order" aria-hidden="true">
        {glyph}
      </span>
      <span className="phase-marker__label">{phase.label || phase.phase_id}</span>
      <span className="phase-marker__meta">
        <span className="mono">order {phase.order}</span>
        <span className="mono">{phase.phase_id}</span>
        <span className="mono">
          {phase.closed_edge_ids.length} closed · {phase.temporary_edge_ids.length} temporary
        </span>
      </span>
      <span className="visually-hidden">{status}</span>
    </button>
  )
}

function PhaseDetails({ phase, hasResult }: { phase: PhaseTimelineEntry; hasResult: boolean }) {
  return (
    <>
      <KeyValueList
        items={[
          { term: 'Phase id', value: <span className="mono">{phase.phase_id}</span> },
          { term: 'Authoritative order', value: <span className="mono">{phase.order}</span> },
          { term: 'Boundary convention', value: phase.boundary_convention },
          { term: 'Notes', value: phase.notes || '—', wide: true },
          {
            term: 'Closures in this phase',
            value: phase.closed_edge_ids.length ? (
              <span className="mono">{phase.closed_edge_ids.join(', ')}</span>
            ) : (
              'none'
            ),
            wide: true,
          },
          {
            term: 'Temporary connections',
            value: phase.temporary_edge_ids.length ? (
              <span className="mono">{phase.temporary_edge_ids.join(', ')}</span>
            ) : (
              'none'
            ),
            wide: true,
          },
        ]}
      />
      {hasResult ? (
        <StatusBadge
          meta={{
            label: 'Analysed for this revision',
            glyph: '◆',
            tone: 'info',
            description: 'A stored run exists for this phase, profile and scenario revision.',
          }}
        />
      ) : (
        <StatusBadge
          meta={{
            label: 'NOT ANALYSED',
            glyph: '○',
            tone: 'neutral',
            description:
              'No analysis has been run for this phase at the current revision. This is not a pass, a failure or an unknown result.',
          }}
        />
      )}
    </>
  )
}

const REACHABILITY_TEXT: Record<string, string> = {
  confirmed: 'Model-confirmed',
  possible: 'Possible only',
  none: 'No route',
  'not-evaluated': 'Not analysed',
}

function ContinuityMatrix({
  continuity,
  phases,
}: {
  continuity: readonly ContinuityReport[]
  phases: readonly PhaseTimelineEntry[]
}) {
  if (continuity.length === 0) {
    return (
      <div className="panel__body">
        <p className="inspector__note">
          No analysis has been run for this scenario yet. Evaluate the sequence to build the
          continuity matrix.
        </p>
      </div>
    )
  }
  return (
    <table className="data-table continuity" data-testid="continuity-matrix">
      <caption>
        One row per origin–destination pair, one column per phase in authoritative order. Every cell
        states its status in words; colour alone never carries the meaning.
      </caption>
      <thead>
        <tr>
          <th scope="col">Origin → destination</th>
          {phases.map((phase) => (
            <th key={phase.phase_id} scope="col">
              <span className="mono">{phase.phase_id}</span>
              <span className="continuity__order">order {phase.order}</span>
            </th>
          ))}
          <th scope="col">Continuity</th>
          <th scope="col">First problem</th>
        </tr>
      </thead>
      <tbody>
        {continuity.map((report) => (
          <tr key={report.key} data-testid={`continuity-${report.key}`}>
            <th scope="row" className="data-table__mono">
              {report.originId} → {report.destinationId}
            </th>
            {report.perPhase.map((entry) => (
              <td key={entry.phaseId} className={`cell cell--${entry.reachability}`}>
                {REACHABILITY_TEXT[entry.reachability]}
              </td>
            ))}
            <td>
              <StatusBadge
                meta={{
                  label: report.label,
                  glyph:
                    report.state === 'continuously-confirmed'
                      ? '●'
                      : report.state === 'interrupted'
                        ? '✕'
                        : report.state === 'uncertain'
                          ? '◐'
                          : '○',
                  tone:
                    report.state === 'continuously-confirmed'
                      ? 'pass'
                      : report.state === 'interrupted'
                        ? 'fail'
                        : report.state === 'uncertain'
                          ? 'unknown'
                          : 'neutral',
                  description: report.description,
                }}
                size="sm"
              />
            </td>
            <td className="data-table__mono">
              {report.firstProblemPhaseId ?? '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TemporalFindings({
  impacts,
  continuity,
  transitionInputs,
  graphFor,
}: {
  impacts: ReturnType<typeof computeImpacts>
  continuity: readonly ContinuityReport[]
  transitionInputs: readonly TransitionInput[]
  graphFor: (phaseId: string) => { closed: readonly string[]; temporary: readonly string[] } | null
}) {
  const material = impacts.filter((impact) => impact.material)
  const explanations = continuity
    .map((report) => explainFirstProblem(report.key, transitionInputs, graphFor))
    .filter((text): text is string => text !== null)

  if (material.length === 0 && explanations.length === 0) {
    return (
      <div className="panel__body">
        <p className="inspector__note">
          No material change between consecutive phases has been observed. Evaluate more than one
          phase to compare them.
        </p>
      </div>
    )
  }

  return (
    <>
      {explanations.length > 0 ? (
        <ul className="finding-explanations" data-testid="first-problem-explanations">
          {explanations.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : null}
      <table className="data-table" data-testid="impact-table">
        <caption>
          Material transitions between successive phases. A changed edge is a <em>relevant change</em>{' '}
          alongside the transition, not proof of a unique root cause.
        </caption>
        <thead>
          <tr>
            <th scope="col">Pair</th>
            <th scope="col">From → To</th>
            <th scope="col">Transition</th>
            <th scope="col">Relevant change</th>
            <th scope="col">Distance</th>
          </tr>
        </thead>
        <tbody>
          {material.map((impact) => (
            <tr key={`${impact.key}-${impact.fromPhaseId}-${impact.toPhaseId}`} data-testid={`impact-${impact.key}-${impact.toPhaseId}`}>
              <td className="data-table__mono">{impact.key.replace('|', ' → ')}</td>
              <td className="data-table__mono">
                {impact.fromPhaseId} → {impact.toPhaseId}
              </td>
              <td>{impact.label}</td>
              <td className="data-table__mono">
                {impact.changedEdgeIds.length ? impact.changedEdgeIds.join(', ') : 'none recorded'}
              </td>
              <td className="numeric">
                {impact.distanceBefore !== null && impact.distanceAfter !== null
                  ? `${impact.distanceBefore.toFixed(1)} m → ${impact.distanceAfter.toFixed(1)} m`
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="panel__foot-note">
        {material.length} material transition(s) observed. Reachability is a statement about the
        modeled checks under the available evidence, not a prediction about the physical world.
      </p>
    </>
  )
}

/** Reachable-state helper reused by the comparison view. */
export function pairReachability(
  result: ReturnType<typeof useWorkspace>['phaseResults'][string] | null,
  key: string,
): string {
  if (!result) return 'not-evaluated'
  return REACHABILITY_TEXT[reachabilityOf(result, key)] ?? 'not-evaluated'
}