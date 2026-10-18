import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel } from '@/components/Button'
import { Dialog } from '@/components/Dialog'
import { SelectField, TextField } from '@/components/Field'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { formatHash } from '@/lib/format'
import { computeContinuity, reachabilityOf, type TransitionInput } from '@/lib/temporal'
import './branches.css'

/**
 * Scenario Branch Explorer and Scorecard (Gate 4, G4-09/G4-10/G4-11).
 *
 * Branches are real persisted scenarios: the source is never mutated, and both
 * sides of a comparison are read back from the API rather than from client
 * state. Every number below is counted from stored analysis results; no score
 * is synthesised and no weighting is applied.
 */
export function BranchExplorer() {
  const {
    scenarios,
    scenarioId,
    selectScenario,
    scenario,
    orderedPhases,
    phaseResults,
    profileId,
    evaluateAllPhases,
    evaluatingPhases,
    api,
    projectId,
    reloadScenarios,
  } = useWorkspace()

  const [creating, setCreating] = useState(false)
  const [newId, setNewId] = useState('')
  const [newName, setNewName] = useState('')
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [compareWith, setCompareWith] = useState('')

  const others = scenarios.filter((entry) => entry.id !== scenarioId)
  const parent = scenarios.find((entry) => entry.id === scenario?.parent_scenario_id) ?? null

  const createBranch = async () => {
    const id = newId.trim()
    if (!scenario) return
    if (!id) {
      setError({ code: 'INVALID_INPUT', message: 'A branch needs its own scenario id.' })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.createBranchFrom(
        projectId ?? '',
        scenario.id,
        id,
        newName.trim() || `Branch of ${scenario.id}`,
      )
      reloadScenarios()
      selectScenario(id)
      setCreating(false)
    } catch (caught) {
      setError({
        code: caught instanceof Error ? caught.name : 'UNKNOWN',
        message: caught instanceof Error ? caught.message : 'Could not create the branch.',
      })
    } finally {
      setBusy(false)
    }
  }

  const selectScenarioAndReload = (id: string) => {
    selectScenario(id)
    setCreating(false)
  }

  const scorecard = useMemo(() => buildScorecard(orderedPhases, phaseResults, profileId), [
    orderedPhases,
    phaseResults,
    profileId,
  ])

  return (
    <div className="branches">
      <Panel
        title="Scenario branches"
        subtitle="Each branch is an independent, persisted scenario with its own revision history"
        actions={
          <Button variant="primary" onClick={() => setCreating(true)} data-testid="create-branch">
            Create branch
          </Button>
        }
      >
        {scenarios.length === 0 ? (
          <EmptyState title="No scenarios loaded" />
        ) : (
          <table className="data-table" data-testid="branch-table">
            <caption>Scenarios available for this project. Selecting one loads its own phase timeline.</caption>
            <thead>
              <tr>
                <th scope="col">Scenario</th>
                <th scope="col">Revision</th>
                <th scope="col">Parent</th>
                <th scope="col">Edits</th>
                <th scope="col">Identity</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((entry) => (
                <tr key={entry.id} aria-selected={entry.id === scenarioId} data-testid={`branch-row-${entry.id}`}>
                  <td>
                    <div className="dashboard__name">{entry.name}</div>
                    <div className="dashboard__id mono">{entry.id}</div>
                  </td>
                  <td className="numeric">{entry.revision}</td>
                  <td className="data-table__mono">{entry.parent_scenario_id ?? '—'}</td>
                  <td className="numeric">{entry.edit_count}</td>
                  <td className="data-table__mono">{formatHash(entry.content_hash, 10)}</td>
                  <td>
                    <Button
                      variant={entry.id === scenarioId ? 'primary' : 'secondary'}
                      onClick={() => void selectScenarioAndReload(entry.id)}
                      data-testid={`select-branch-${entry.id}`}
                    >
                      {entry.id === scenarioId ? 'Open' : 'Open branch'}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="phases__grid">
        <Panel title="Phase scorecard" subtitle={`Profile ${profileId} · ${orderedPhases.length} phase(s)`}>
          <KeyValueList
            items={[
              { term: 'Evaluated phases', value: `${scorecard.evaluated} of ${orderedPhases.length}` },
              { term: 'Phases with confirmed reachability', value: String(scorecard.confirmedPhases) },
              { term: 'Interrupted phases', value: String(scorecard.interruptedPhases) },
              { term: 'Phases with possible-only routes', value: String(scorecard.possibleOnlyPhases) },
              { term: 'Unknown conditions', value: String(scorecard.unknowns) },
              { term: 'Known rule violations', value: String(scorecard.failures) },
              { term: 'Affected origin/destination pairs', value: String(scorecard.affectedPairs) },
            ]}
          />
          <p className="inspector__note">
            These are counts of what the engine reported. There is no composite "safety score": fewer
            violations does not make a plan safer, and no regulatory conclusion is implied.
          </p>
          <Button
            variant="primary"
            onClick={() => void evaluateAllPhases()}
            busy={Object.values(evaluatingPhases).some((state) => state === 'running')}
          >
            Evaluate this branch's sequence
          </Button>
        </Panel>

        <Panel title="Compare with another branch" subtitle="Both sides are read back from the API">
          {others.length === 0 ? (
            <EmptyState
              title="No alternative branch yet"
              description="Create a branch to compare an alternative plan against this one."
            />
          ) : (
            <div className="field">
              <SelectField
                label="Compare with"
                value={compareWith}
                onChange={(event) => setCompareWith(event.target.value)}
                data-testid="compare-branch-select"
              >
                <option value="">Select a branch…</option>
                {others.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.name} (r{entry.revision})
                  </option>
                ))}
              </SelectField>
              <p className="inspector__note">
                Opening the other branch loads its own timeline, graph and runs. The scenario you
                leave is preserved on the server, so switching back never loses work.
              </p>
              {compareWith ? (
                <Button onClick={() => void selectScenarioAndReload(compareWith)} data-testid="open-compare-branch">
                  Open {compareWith}
                </Button>
              ) : null}
            </div>
          )}
          {parent ? (
            <p className="inspector__note">
              This scenario branches from <span className="mono">{parent.id}</span> (revision{' '}
              {parent.revision}). Editing it does not change its parent.
            </p>
          ) : null}
        </Panel>
      </div>

      <Panel title="Continuity by pair" subtitle="Uses this branch's own evaluated phases" flush>
        <BranchContinuity orderedPhases={orderedPhases} phaseResults={phaseResults} />
      </Panel>

      <Dialog
        open={creating}
        title="Create a scenario branch"
        description="The new scenario copies this revision's phases and origins. The source is not modified."
        onClose={() => setCreating(false)}
        footer={
          <>
            <Button onClick={() => setCreating(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => void createBranch()} busy={busy} data-testid="confirm-branch">
              Create branch
            </Button>
          </>
        }
      >
        <TextField
          label="Branch id"
          value={newId}
          onChange={setNewId}
          placeholder={`${scenario?.id ?? 'scn'}-alt`}
          hint="Stored server-side as the scenario identity; it must be unique."
          error={error?.message}
        />
        <TextField label="Branch name" value={newName} onChange={setNewName} placeholder="Alternative plan B" />
        {error ? <ErrorPanel code={error.code} message={error.message} /> : null}
      </Dialog>
    </div>
  )
}

export interface Scorecard {
  evaluated: number
  confirmedPhases: number
  interruptedPhases: number
  possibleOnlyPhases: number
  unknowns: number
  failures: number
  affectedPairs: number
}

export function buildScorecard(
  orderedPhases: readonly { phase_id: string }[],
  phaseResults: Readonly<
    Record<
      string,
      {
        counts: Record<string, number>
        od_results: { origin_id: string; destination_id: string; confirmed_reachable: boolean; possibly_reachable: boolean }[]
      }
    >
  >,
  _profileId: string,
): Scorecard {
  let confirmedPhases = 0
  let interruptedPhases = 0
  let possibleOnlyPhases = 0
  let unknowns = 0
  let failures = 0
  let evaluated = 0
  // Pairs that are not confirmed in at least one evaluated phase.
  const affected = new Set<string>()

  for (const phase of orderedPhases) {
    const result = phaseResults[phase.phase_id]
    if (!result) continue
    evaluated += 1
    unknowns += result.counts.verdict_unknown ?? 0
    failures += result.counts.verdict_fail ?? 0

    const hasConfirmed = result.od_results.some((od) => od.confirmed_reachable)
    const hasPossibleOnly = result.od_results.some(
      (od) => !od.confirmed_reachable && od.possibly_reachable,
    )
    if (hasConfirmed) confirmedPhases += 1
    if (hasPossibleOnly) possibleOnlyPhases += 1
    if (!hasConfirmed) interruptedPhases += 1

    for (const od of result.od_results) {
      if (!od.confirmed_reachable) affected.add(`${od.origin_id}|${od.destination_id}`)
    }
  }

  return {
    evaluated,
    confirmedPhases,
    interruptedPhases,
    possibleOnlyPhases,
    unknowns,
    failures,
    affectedPairs: affected.size,
  }
}

function BranchContinuity({
  orderedPhases,
  phaseResults,
}: {
  orderedPhases: readonly { phase_id: string; order: number; label: string }[]
  phaseResults: ReturnType<typeof useWorkspace>['phaseResults']
}) {
  const inputs: TransitionInput[] = useMemo(
    () =>
      orderedPhases.map((entry) => ({
        entry: entry as TransitionInput['entry'],
        result: phaseResults[entry.phase_id] ?? null,
      })),
    [orderedPhases, phaseResults],
  )
  const keys = new Set<string>()
  for (const input of inputs) {
    for (const od of input.result?.od_results ?? []) keys.add(`${od.origin_id}|${od.destination_id}`)
  }
  const reports = [...keys].sort().map((key) => computeContinuity(key, inputs))

  if (reports.length === 0) {
    return (
      <div className="panel__body">
        <p className="inspector__note">Evaluate this branch's sequence to compare continuity.</p>
      </div>
    )
  }

  return (
    <table className="data-table" data-testid="branch-continuity">
      <caption>Continuity for this branch. Unevaluated phases remain visibly unevaluated.</caption>
      <thead>
        <tr>
          <th scope="col">Pair</th>
          {orderedPhases.map((phase) => (
            <th key={phase.phase_id} scope="col" className="mono">
              {phase.phase_id}
            </th>
          ))}
          <th scope="col">Continuity</th>
        </tr>
      </thead>
      <tbody>
        {reports.map((report) => (
          <tr key={report.key}>
            <th scope="row" className="data-table__mono">
              {report.key.replace('|', ' → ')}
            </th>
            {report.perPhase.map((entry) => (
              <td key={entry.phaseId} className={`cell cell--${entry.reachability}`}>
                {entry.reachability}
              </td>
            ))}
            <td>
              <StatusBadge
                meta={{
                  label: report.label,
                  glyph: '●',
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
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Exposed for reuse by tests: the reachability a stored result reports. */
export function reportedReachability(
  result: ReturnType<typeof useWorkspace>['phaseResults'][string] | null,
  key: string,
): string {
  if (!result) return 'not-evaluated'
  const state = reachabilityOf(result, key)
  return state === 'confirmed' ? 'confirmed' : state === 'possible' ? 'possible' : 'none'
}