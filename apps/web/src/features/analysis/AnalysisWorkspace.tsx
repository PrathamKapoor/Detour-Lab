import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { SelectField, TextField } from '@/components/Field'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { formatHash, formatMetres, pluralise } from '@/lib/format'
import { REACHABILITY_META, reachabilityOf, verdictMeta } from '@/lib/status'

/**
 * Screen 4 — mobility profile & analysis workspace.
 *
 * Everything displayed here is a projection of the backend's `AnalysisResult`.
 * The browser never recomputes feasibility, never fills in a distance, and never
 * upgrades a possible route to a confirmed one.
 */
export function AnalysisWorkspace() {
  const {
    rulesets,
    scenario,
    scenarioLoading,
    profileId,
    setProfileId,
    phaseId,
    setPhaseId,
    evaluationInstant,
    setEvaluationInstant,
    runAnalysis,
    running,
    runError,
    current,
    stale,
    promoteToBaseline,
    setView,
  } = useWorkspace()
  const [filter, setFilter] = useState<'all' | 'fail' | 'unknown'>('all')

  const findings = useMemo(() => {
    const all = current?.result.edge_evaluations.flatMap((evaluation) => evaluation.findings ?? []) ?? []
    if (filter === 'fail') return all.filter((finding) => finding.state === 'FAIL')
    if (filter === 'unknown') return all.filter((finding) => finding.state === 'UNKNOWN')
    return all
  }, [current, filter])

  // Distinguish "still loading" from "there is nothing here": a premature empty
  // state would tell the user they have no scenario while the fetch is in flight.
  if (scenarioLoading && !scenario) {
    return (
      <Panel title="Run model verification">
        <Spinner label="Loading scenario" />
      </Panel>
    )
  }
  if (!scenario) return <EmptyState title="No scenario selected" description="Open a project first." />

  const profiles = rulesets?.profiles ?? []
  const phases = scenario.phases

  return (
    <div className="analysis">
      <Panel
        title="Run model verification"
        subtitle="Deterministic evaluation on the server. The browser submits inputs and renders the returned result."
        actions={
          <Button
            variant="primary"
            onClick={() => void runAnalysis()}
            busy={running}
            data-testid="run-analysis"
          >
            Run analysis
          </Button>
        }
      >
        <div className="analysis__controls">
          <SelectField
            label="Mobility profile"
            value={profileId}
            onChange={(event) => setProfileId(event.target.value)}
            hint={profiles.find((profile) => profile.id === profileId)?.description}
            data-testid="profile-select"
          >
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </SelectField>

          <SelectField
            label="Construction phase"
            value={phaseId}
            onChange={(event) => setPhaseId(event.target.value)}
            hint={phases.find((phase) => phase.id === phaseId)?.notes}
            data-testid="phase-select"
          >
            {phases.map((phase) => (
              <option key={phase.id} value={phase.id}>
                {phase.label || phase.id}
              </option>
            ))}
          </SelectField>

          <TextField
            label="Evaluation instant"
            value={evaluationInstant}
            onChange={setEvaluationInstant}
            hint="The instant at which evidence freshness is judged. Stored with the run and reused on replay."
          />
        </div>

        {runError ? (
          <ErrorPanel
            title="Analysis failed"
            code={runError.code}
            message={runError.userMessage}
            action={<Button onClick={() => void runAnalysis()}>Retry</Button>}
          />
        ) : null}

        {stale && current ? (
          <p className="dirty-banner" role="status">
            <span className="dirty-banner__glyph" aria-hidden="true">
              ●
            </span>
            These results describe revision {current.run.scenario_revision}; the scenario has changed
            since. Run the analysis again before relying on them.
          </p>
        ) : null}
      </Panel>

      {running ? (
        <Panel title="Running analysis">
          <Spinner label="Evaluating rules, evidence and routes on the server" />
        </Panel>
      ) : null}

      {!current && !running ? (
        <Panel title="No analysis yet">
          <EmptyState
            title="Run an analysis to see modeled results"
            description="Pick a profile and phase, then run. Results are stored on the server and replayable by run id."
            icon="◷"
          />
        </Panel>
      ) : null}

      {current ? (
        <>
          <Panel
            title="Run identity"
            subtitle="Every result is traceable to these identifiers"
            actions={
              <>
                <Button onClick={promoteToBaseline} data-testid="set-baseline">
                  Use as baseline
                </Button>
                <Button onClick={() => setView('reports')}>Export manifest</Button>
              </>
            }
          >
            <KeyValueList
              items={[
                { term: 'Run id', value: <span className="mono" data-testid="run-id">{current.run.id}</span> },
                { term: 'Scenario revision', value: String(current.run.scenario_revision) },
                { term: 'Phase', value: <span className="mono" data-testid="run-phase">{current.result.phase_id}</span> },
                {
                  term: 'Profile',
                  value: (
                    <span className="mono" data-testid="run-profile">
                      {current.result.profile_id}
                    </span>
                  ),
                },
                { term: 'Semantic hash', value: <span className="mono" data-testid="semantic-hash">{formatHash(current.run.semantic_hash, 24)}</span> },
                { term: 'Input hash', value: <span className="mono">{formatHash(current.run.input_hash, 24)}</span> },
                { term: 'Rulepack', value: `${current.result.rulepack_id} v${current.result.rulepack_version}` },
                { term: 'Phase graph hash', value: <span className="mono">{formatHash(current.result.phase_graph_hash, 16)}</span> },
                { term: 'Evaluated at', value: current.run.evaluation_instant },
                { term: 'Counts', value: <span className="mono">{JSON.stringify(current.result.counts)}</span>, wide: true },
              ]}
            />
          </Panel>

          <Panel
            title="Origin–destination reachability"
            subtitle="Confirmed and possible-only routes are reported separately and never merged"
            flush
          >
            <table className="data-table" data-testid="od-table">
              <caption>
                Reachability per origin–destination pair. Distance is only reported when a route was
                actually proven.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Pair</th>
                  <th scope="col">Status</th>
                  <th scope="col">Confirmed distance</th>
                  <th scope="col">Confirmed route (edge IDs)</th>
                  <th scope="col">Findings</th>
                </tr>
              </thead>
              <tbody>
                {current.result.od_results.map((od) => {
                  const kind = reachabilityOf(od.confirmed_reachable, od.possibly_reachable)
                  const meta = REACHABILITY_META[kind]
                  return (
                    <tr key={`${od.origin_id}-${od.destination_id}`} data-testid={`od-${od.origin_id}-${od.destination_id}`}>
                      <td className="data-table__mono">
                        {od.origin_id} → {od.destination_id}
                      </td>
                      <td>
                        <StatusBadge meta={meta} />
                      </td>
                      <td className="numeric" data-testid={`od-distance-${od.origin_id}-${od.destination_id}`}>
                        {od.confirmed_reachable ? formatMetres(od.confirmed_distance_m) : '—'}
                      </td>
                      <td>
                        {od.confirmed_path_edge_ids.length > 0 ? (
                          <span className="od-route">
                            {od.confirmed_path_edge_ids.map((edgeId, index) => (
                              <span key={edgeId} className="inspector__route-edge">
                                {edgeId}
                                {index < od.confirmed_path_edge_ids.length - 1 ? ' →' : ''}
                              </span>
                            ))}
                          </span>
                        ) : od.possible_path_edge_ids.length > 0 ? (
                          <>
                            <span className="od-route">
                              {od.possible_path_edge_ids.map((edgeId) => (
                                <span key={edgeId} className="inspector__route-edge">
                                  {edgeId}
                                </span>
                              ))}
                            </span>
                            <div className="inspector__note">{od.possible_distance_label}</div>
                          </>
                        ) : (
                          <span className="inspector__note">No route in the possible graph.</span>
                        )}
                      </td>
                      <td className="numeric">
                        {od.relevant_finding_ids.length} relevant
                        {od.blocking_finding_ids.length > 0 ? (
                          <>
                            <div className="delta-down">{od.blocking_finding_ids.length} proven blocking</div>
                          </>
                        ) : null}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="panel__foot-note">
              A pair marked “{REACHABILITY_META.possible.label}” would become confirmed only if every
              unknown condition on its path were resolved. The engine does not assume that.
            </p>
          </Panel>

          <Panel
            title="Findings"
            subtitle={pluralise(findings.length, 'finding')}
            flush
            actions={
              <div className="tabs tabs--inline" role="group" aria-label="Finding filter">
                {(['all', 'fail', 'unknown'] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={`btn btn--sm ${filter === option ? 'btn--primary' : 'btn--ghost'}`}
                    aria-pressed={filter === option}
                    onClick={() => setFilter(option)}
                    data-testid={`filter-${option}`}
                  >
                    {option === 'all' ? 'All' : option === 'fail' ? 'Failures' : 'Unknowns'}
                  </button>
                ))}
              </div>
            }
          >
            {findings.length === 0 ? (
              <div className="panel__body">
                <p className="inspector__note">No findings match this filter for the current run.</p>
              </div>
            ) : (
              <table className="data-table" data-testid="findings-table">
                <caption>Findings produced by the evaluation engine, in canonical order</caption>
                <thead>
                  <tr>
                    <th scope="col">State</th>
                    <th scope="col">Element</th>
                    <th scope="col">Rule</th>
                    <th scope="col">Reason</th>
                    <th scope="col">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((finding) => (
                    <tr key={finding.id} data-testid={`finding-${finding.id}`}>
                      <td>
                        <StatusBadge meta={verdictMeta(finding.state)} size="sm" />
                      </td>
                      <td className="data-table__mono">{finding.element_id}</td>
                      <td className="data-table__mono">{finding.rule_id ?? '—'}</td>
                      <td className="data-table__mono">{finding.reason_code}</td>
                      <td>
                        {finding.explanation}
                        {finding.evidence_ids.length > 0 ? (
                          <div className="inspector__note">Evidence: {finding.evidence_ids.join(', ')}</div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      ) : null}
    </div>
  )
}