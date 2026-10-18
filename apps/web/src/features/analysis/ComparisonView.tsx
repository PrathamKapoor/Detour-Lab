import { useMemo } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, Panel } from '@/components/Button'
import { StatusBadge } from '@/components/StatusBadge'
import { formatMetres } from '@/lib/format'
import { REACHABILITY_META, reachabilityOf } from '@/lib/status'

/**
 * Screen 5 — before / after comparison.
 *
 * Both sides are real stored runs from the backend. Nothing here recomputes a
 * verdict: the comparison only reads the two `AnalysisResult` payloads and
 * reports the difference between them.
 */
export function ComparisonView() {
  const { baseline, current, setView, graph } = useWorkspace()

  const rows = useMemo(() => {
    if (!baseline || !current) return []
    const baseByKey = new Map(baseline.result.od_results.map((od) => [`${od.origin_id}|${od.destination_id}`, od]))
    return current.result.od_results.map((od) => {
      const key = `${od.origin_id}|${od.destination_id}`
      const before = baseByKey.get(key)
      const beforeKind = before ? reachabilityOf(before.confirmed_reachable, before.possibly_reachable) : 'none'
      const afterKind = reachabilityOf(od.confirmed_reachable, od.possibly_reachable)
      return { key, before, after: od, beforeKind, afterKind }
    })
  }, [baseline, current])

  if (!baseline || !current) {
    return (
      <Panel title="Before / after comparison">
        <EmptyState
          title={!current ? 'Run an analysis first' : 'No baseline captured'}
          description={
            !current
              ? 'Run an analysis, then use “Use as baseline”, make an edit, and run again.'
              : 'The analysis currently displayed has not been marked as a baseline yet.'
          }
          icon="⇄"
          action={
            <Button variant="primary" onClick={() => setView('analysis')}>
              Go to analysis
            </Button>
          }
        />
      </Panel>
    )
  }

  const lostPairs = rows.filter((row) => row.before?.confirmed_reachable && !row.after.confirmed_reachable)
  const gainedPairs = rows.filter((row) => !row.before?.confirmed_reachable && row.after.confirmed_reachable)

  return (
    <div className="compare">
      <Panel
        title="Comparison context"
        subtitle="Both sides come from stored backend runs"
        actions={
          <Button onClick={() => setView('analysis')}>Back to analysis</Button>
        }
      >
        <div className="compare__context">
          <div>
            <h3 className="inspector__heading">Baseline</h3>
            <p className="mono">{baseline.run.id}</p>
            <p className="inspector__note">
              revision {baseline.run.scenario_revision} · {baseline.result.phase_id} ·{' '}
              {baseline.result.profile_id} · hash {baseline.run.semantic_hash.slice(7, 19)}
            </p>
          </div>
          <div>
            <h3 className="inspector__heading">Modified</h3>
            <p className="mono">{current.run.id}</p>
            <p className="inspector__note">
              revision {current.run.scenario_revision} · {current.result.phase_id} ·{' '}
              {current.result.profile_id} · hash {current.run.semantic_hash.slice(7, 19)}
            </p>
          </div>
          {baseline.result.profile_id !== current.result.profile_id ||
          baseline.result.phase_id !== current.result.phase_id ? (
            <p className="error-panel" role="status">
              These runs use different profiles or phases. Connectivity differences may reflect that
              change rather than the construction edit.
            </p>
          ) : null}
        </div>
      </Panel>

      <Panel title="Connectivity change" subtitle="Reachability transitions per origin–destination pair" flush>
        <table className="data-table" data-testid="comparison-table">
          <caption>
            Compare confirmed reachability between the two runs. Distances are shown only when both
            sides proved a route.
          </caption>
          <thead>
            <tr>
              <th scope="col">Pair</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
              <th scope="col">Change</th>
              <th scope="col">Distance before → after</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const changed = row.beforeKind !== row.afterKind
              const direction =
                row.beforeKind === 'confirmed' && row.afterKind !== 'confirmed'
                  ? 'lost'
                  : row.beforeKind !== 'confirmed' && row.afterKind === 'confirmed'
                    ? 'gained'
                    : 'unchanged'
              return (
                <tr key={row.key} className={changed ? 'is-changed' : undefined} data-testid={`cmp-${row.key}`}>
                  <td className="data-table__mono">{row.key.replace('|', ' → ')}</td>
                  <td>
                    <StatusBadge meta={REACHABILITY_META[row.beforeKind]} size="sm" />
                  </td>
                  <td>
                    <StatusBadge meta={REACHABILITY_META[row.afterKind]} size="sm" />
                  </td>
                  <td className={`delta-${direction}`}>{direction}</td>
                  <td className="numeric">
                    {row.before?.confirmed_reachable && row.after.confirmed_reachable
                      ? `${formatMetres(row.before.confirmed_distance_m)} → ${formatMetres(row.after.confirmed_distance_m)}`
                      : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="panel__foot-note">
          {lostPairs.length} pair(s) lost a confirmed connection; {gainedPairs.length} gained one.
          A “lost confirmed” pair may still be <em>possible</em>: that is a modelling statement about
          the evidence, not a prediction about the world.
        </p>
      </Panel>

      <Panel title="Edge state changes" subtitle="Same graph, different modeled state" flush>
        <table className="data-table" data-testid="edge-diff-table">
          <caption>Edges whose modeled state differs between the two runs</caption>
          <thead>
            <tr>
              <th scope="col">Edge</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
            </tr>
          </thead>
          <tbody>
            {buildEdgeDiff(baseline, current).map((row) => (
              <tr key={row.edgeId}>
                <td className="data-table__mono">{row.edgeId}</td>
                <td>
                  <StatusBadge meta={REACHABILITY_META[row.before]} size="sm" />
                </td>
                <td>
                  <StatusBadge meta={REACHABILITY_META[row.after]} size="sm" />
                </td>
              </tr>
            ))}
            {buildEdgeDiff(baseline, current).length === 0 ? (
              <tr>
                <td colSpan={3} className="inspector__note">
                  No modeled edge state changed between these runs.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Panel>

      {graph ? (
        <Panel title="Graph identity" subtitle="Both runs are computed against the same base network">
          <p className="mono">{graph.graph_version_id}</p>
          <p className="inspector__note">
            Base graph hash {graph.content_hash.slice(7, 27)}. Identical base hashes mean a difference in
            results comes from the scenario, phase or profile — not from the network being edited.
          </p>
        </Panel>
      ) : null}
    </div>
  )
}

type EdgeClass = 'confirmed' | 'possible' | 'none'

function buildEdgeDiff(
  baseline: NonNullable<ReturnType<typeof useWorkspace>['baseline']>,
  current: NonNullable<ReturnType<typeof useWorkspace>['current']>,
): { edgeId: string; before: EdgeClass; after: EdgeClass }[] {
  const classify = (evaluation: { confirmed_eligible: boolean; possibly_eligible: boolean }): EdgeClass =>
    evaluation.confirmed_eligible ? 'confirmed' : evaluation.possibly_eligible ? 'possible' : 'none'
  const before = new Map<string, EdgeClass>(
    baseline.result.edge_evaluations.map((evaluation) => [evaluation.edge_id, classify(evaluation)]),
  )
  return current.result.edge_evaluations
    .filter((evaluation) => before.get(evaluation.edge_id) !== classify(evaluation))
    .map((evaluation) => ({
      edgeId: evaluation.edge_id,
      before: before.get(evaluation.edge_id) ?? ('none' as EdgeClass),
      after: classify(evaluation),
    }))
}