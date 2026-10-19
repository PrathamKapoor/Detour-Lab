import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { GraphCanvas } from '@/features/network/GraphCanvas'
import { useResource } from '@/lib/useResource'
import {
  executionStatusMeta,
  FAULT_KIND_LABEL,
  formatDistance,
  observationMeta,
  reachabilityOf,
} from '@/lib/gate6'
import type {
  ExperimentReplay,
  FailureLabRunEnvelope,
  Gate6Experiment,
  Gate6Limits,
  Gate6Robustness,
} from '@/api/types'
import './failure-lab.css'

/**
 * Adversarial Failure Laboratory (Gate 6, G6-10..G6-12).
 *
 * Seven panels, in the order an engineer actually uses them:
 *   A source configuration · B fault selection · C execution · D results
 *   E visual comparison      · F failure explanation · G reproducibility
 *
 * The interface computes no verdict and predicts no outcome. Every state it
 * shows is the backend's answer: which suites exist and whether they apply, what
 * the engine returned, and which elements changed. A suite that does not apply
 * is shown as unavailable rather than as a passing test.
 *
 * Progress is always a real completed/total count read back from the response.
 * No fake percentage is ever rendered.
 */

export function FailureLab() {
  const ws = useWorkspace()
  const { api, scenarioId, phaseId, profileId, evaluationInstant } = ws
  const [selectedSuites, setSelectedSuites] = useState<string[]>([
    'critical_closure',
    'evidence_gap',
  ])
  const [run, setRun] = useState<FailureLabRunEnvelope | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null)
  const [replay, setReplay] = useState<ExperimentReplay | null>(null)
  const [replayBusy, setReplayBusy] = useState(false)

  const catalog = useResource(
    (signal) => api.failureLabCatalog(scenarioId as string, phaseId, signal),
    [api, scenarioId, phaseId],
    { enabled: Boolean(scenarioId) },
  )

  const limits = useResource(
    (signal) => api.failureLabLimits(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )

  const history = useResource(
    (signal) => api.listFailureLabExperiments(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )

  const experiments = useMemo(() => run?.experiments ?? [], [run])
  const selected: Gate6Experiment | null = useMemo(
    () => experiments.find((e) => e.experiment_id === selectedExperimentId) ?? experiments[0] ?? null,
    [experiments, selectedExperimentId],
  )

  const applicableSuites = (catalog.data?.suites ?? []).filter((suite) => suite.applicable)
  const unavailableSuites = (catalog.data?.suites ?? []).filter((suite) => !suite.applicable)

  function toggleSuite(suiteId: string) {
    setSelectedSuites((current) =>
      current.includes(suiteId) ? current.filter((id) => id !== suiteId) : [...current, suiteId],
    )
  }

  async function execute() {
    if (!scenarioId) return
    setRunning(true)
    setRunError(null)
    setReplay(null)
    try {
      const response = await api.runFailureLabExperiments(scenarioId, {
        phase_ids: [phaseId],
        profile_ids: [profileId],
        evaluation_instant: evaluationInstant,
        suite_ids: selectedSuites,
      })
      setRun(response)
      setSelectedExperimentId(response.experiments[0]?.experiment_id ?? null)
    } catch (error) {
      setRunError(error instanceof Error ? error.message : String(error))
    } finally {
      setRunning(false)
    }
  }

  async function replayExperiment(experimentId: string) {
    setReplayBusy(true)
    try {
      setReplay(await api.replayFailureLabExperiment(experimentId))
    } finally {
      setReplayBusy(false)
    }
  }

  return (
    <div className="failure-lab">
      <div data-testid="panel-try-to-break">
        <Panel
          title="Try to Break My Plan"
          subtitle="Run explicitly modelled adversarial conditions through the authoritative engine"
        >
          <p className="failure-lab__intro" data-testid="try-to-break-intro">
            Each suite below is an authored, deterministic condition. The system does not search for
            hazards and does not predict failures: it applies one modelled condition to an isolated
            copy of this scenario revision and re-runs the same evaluation engine.
          </p>
          <div className="failure-lab__break">
            <Button
              variant="primary"
              onClick={() => void execute()}
              disabled={running || selectedSuites.length === 0 || !scenarioId}
              data-testid="run-fault-suite"
            >
              {running
                ? 'Executing experiments on the backend…'
                : `Try to break my plan (${selectedSuites.length} suite${selectedSuites.length === 1 ? '' : 's'})`}
            </Button>
            <p className="failure-lab__break-note" data-testid="run-progress">
              {running
                ? 'Executing. Each condition runs to completion on the backend; progress is reported as completed / total.'
                : 'The source scenario, its evidence and its stored analyses are never modified.'}
            </p>
          </div>
        </Panel>
      </div>

      <div className="failure-lab__grid">
        <div data-testid="panel-a-source">
          <Panel title="A · Source configuration">
            {catalog.data ? (
              <KeyValueList
                items={[
                  { term: 'Scenario', value: catalog.data.scenario_id },
                  { term: 'Revision', value: String(catalog.data.scenario_revision) },
                  { term: 'Content hash', value: catalog.data.scenario_content_hash, wide: true },
                  { term: 'Phase', value: phaseId },
                  { term: 'Mobility profile', value: profileId },
                  { term: 'Evaluation instant', value: evaluationInstant },
                  {
                    term: 'Rulepack',
                    value: `${catalog.data.rulepack.id} v${catalog.data.rulepack.version}`,
                  },
                  { term: 'Legal applicability', value: catalog.data.rulepack.legal_applicability },
                  { term: 'Declared phases', value: catalog.data.declared_phase_ids.join(', ') },
                ]}
              />
            ) : (
              <Spinner label="Loading the source configuration" />
            )}
          </Panel>
        </div>

        <div data-testid="panel-b-faults">
          <Panel title="B · Fault selection" subtitle="Only supported, applicable conditions are offered">
            {catalog.error ? (
              <ErrorPanel
                title="The fault catalogue could not be loaded"
                message={catalog.error.userMessage}
                code={catalog.error.code}
                action={
                  <Button variant="secondary" onClick={catalog.reload}>
                    Retry
                  </Button>
                }
              />
            ) : !catalog.data ? (
              <Spinner label="Loading supported faults" />
            ) : (
              <>
                <fieldset className="failure-lab__suites" data-testid="fault-suite-list">
                  <legend className="visually-hidden">Select fault suites to execute</legend>
                  {applicableSuites.map((suite) => (
                    <label key={suite.suite_id} className="failure-lab__suite">
                      <input
                        type="checkbox"
                        checked={selectedSuites.includes(suite.suite_id)}
                        onChange={() => toggleSuite(suite.suite_id)}
                        data-testid={`suite-toggle-${suite.suite_id}`}
                      />
                      <span>
                        <span className="failure-lab__suite-title">{suite.title}</span>
                        <span className="failure-lab__suite-desc">{suite.description}</span>
                        <span className="failure-lab__suite-targets mono">
                          targets: {suite.target_element_ids.join(', ') || 'n/a'}
                        </span>
                      </span>
                    </label>
                  ))}
                </fieldset>

                {unavailableSuites.length > 0 ? (
                  <div className="failure-lab__unavailable" data-testid="unavailable-suites">
                    <h3 className="failure-lab__subheading">Not applicable to this scenario</h3>
                    <ul>
                      {unavailableSuites.map((suite) => (
                        <li key={suite.suite_id} data-testid={`unavailable-suite-${suite.suite_id}`}>
                          <strong>{suite.title}</strong> — {suite.unavailable_reason} This condition has{' '}
                          <strong>not</strong> been tested.
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <h3 className="failure-lab__subheading">Supported fault kinds</h3>
                <ul className="failure-lab__kinds" data-testid="fault-kind-list">
                  {catalog.data.fault_kinds.map((entry) => (
                    <li key={entry.kind}>
                      <span className="mono">{entry.kind}</span>
                      <span>{entry.description}</span>
                      {entry.mutation_note ? (
                        <span className="failure-lab__note">Note: {entry.mutation_note}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>

                <h3 className="failure-lab__subheading">Deliberately not modelled</h3>
                <ul className="failure-lab__kinds" data-testid="unsupported-scenarios">
                  {catalog.data.unsupported_scenarios.map((entry) => (
                    <li key={entry.name}>
                      <strong>{entry.name}</strong>
                      <span>{entry.reason}</span>
                    </li>
                  ))}
                </ul>

                <LimitsPanel limits={limits.data?.limits ?? null} loading={limits.loading} />
              </>
            )}
          </Panel>
        </div>

        <div data-testid="panel-c-execution">
          <Panel title="C · Experiment execution">
            {runError ? (
              <ErrorPanel
                title="The experiment request failed"
                message={runError}
                action={
                  <Button variant="secondary" onClick={() => void execute()}>
                    Retry
                  </Button>
                }
              />
            ) : !run ? (
              <EmptyState
                title="No experiments executed in this session"
                description="Select one or more suites above and run them. Results appear here with real counts."
              />
            ) : (
              <>
                <KeyValueList
                  items={[
                    { term: 'Suites requested', value: String(selectedSuites.length) },
                    { term: 'Experiments returned', value: String(run.experiment_count) },
                    { term: 'Completed', value: String(run.robustness?.experiments_completed ?? 0) },
                    {
                      term: 'Partially completed',
                      value: String(run.robustness?.experiments_partially_completed ?? 0),
                    },
                    {
                      term: 'Invalid (refused, not tested)',
                      value: String(run.robustness?.experiments_invalid ?? 0),
                    },
                    { term: 'Execution failed', value: String(run.robustness?.experiments_failed ?? 0) },
                  ]}
                />
                <p
                  className="failure-lab__progress"
                  role="status"
                  aria-live="polite"
                  data-testid="execution-counts"
                >
                  Completed {run.robustness?.experiments_completed ?? 0} of {run.experiment_count}.
                </p>
              </>
            )}
          </Panel>
        </div>

        <div data-testid="panel-d-results">
          <Panel title="D · Experiment results">
            {!run ? (
              <EmptyState
                title="No results yet"
                description="Results are reported per experiment so a failure and a resilience case read the same way."
              />
            ) : (
              <div className="table-scroll">
      <table className="data-table" data-testid="experiment-table">
                <thead>
                  <tr>
                    <th scope="col">Experiment</th>
                    <th scope="col">Condition</th>
                    <th scope="col">Status</th>
                    <th scope="col">What the engine reported</th>
                    <th scope="col">Select</th>
                  </tr>
                </thead>
                <tbody>
                  {experiments.map((experiment) => (
                    <tr
                      key={experiment.experiment_id}
                      data-testid={`experiment-row-${experiment.experiment_id}`}
                      className={
                        selected?.experiment_id === experiment.experiment_id ? 'is-selected' : undefined
                      }
                    >
                      <th scope="row" className="mono">
                        {experiment.experiment_id}
                        <span className="failure-lab__suite-name">{experiment.suite_id ?? 'ad-hoc'}</span>
                      </th>
                      <td>
                        {experiment.faults.map((fault) => (
                          <span key={fault.fault_id} className="failure-lab__fault-line">
                            <span className="mono">{FAULT_KIND_LABEL[fault.kind] ?? fault.kind}</span>
                            {fault.target_ids.length > 0 ? (
                              <span className="failure-lab__fault-targets mono">
                                {' '}
                                {fault.target_ids.join(', ')}
                              </span>
                            ) : null}
                          </span>
                        ))}
                      </td>
                      <td>
                        <StatusBadge meta={executionStatusMeta(experiment.status)} />
                        <span
                          className="failure-lab__muted"
                          data-testid={`experiment-status-${experiment.experiment_id}`}
                        >
                          {experiment.status}
                        </span>
                      </td>
                      <td>
                        {experiment.observations.length === 0 ? (
                          <span className="failure-lab__muted">
                            no modelled conclusion — see the execution status
                          </span>
                        ) : (
                          experiment.observations.map((observation) => (
                            <StatusBadge
                              key={observation}
                              meta={observationMeta(observation)}
                              detail={observation.replace(/_/g, ' ')}
                            />
                          ))
                        )}
                      </td>
                      <td>
                        <Button
                          variant="secondary"
                          data-testid={`experiment-open-${experiment.experiment_id}`}
                          onClick={() => setSelectedExperimentId(experiment.experiment_id)}
                        >
                          Open
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
      </div>
            )}
          </Panel>
        </div>

        <div data-testid="panel-e-visual">
          <Panel title="E · Visual comparison" subtitle="Baseline graph against the faulted state">
            {selected ? (
              <ExperimentVisualComparison experiment={selected} />
            ) : (
              <EmptyState
                title="No experiment selected"
                description="Open an experiment to compare the baseline network with the faulted one."
              />
            )}
          </Panel>
        </div>

        <div data-testid="panel-f-explanation">
          <Panel title="F · Failure explanation">
            {selected ? (
              <ExperimentExplanation experiment={selected} />
            ) : (
              <EmptyState
                title="No experiment selected"
                description="The explanation names the elements, evidence and rules that changed, and says what the change does and does not prove."
              />
            )}
          </Panel>
        </div>

        <div data-testid="panel-g-reproducibility">
          <Panel title="G · Reproducibility">
            {selected ? (
              <ExperimentReproducibility
                experiment={selected}
                replay={replay}
                onReplay={() => void replayExperiment(selected.experiment_id)}
                replaying={replayBusy}
              />
            ) : (
              <EmptyState
                title="No experiment selected"
                description="Execution id, input hash and semantic hash appear here."
              />
            )}
          </Panel>
        </div>
      </div>

      <RobustnessPanel summary={run?.robustness ?? null} />

      <div data-testid="panel-history">
        <Panel title="Stored experiments" subtitle="Append-only history for this scenario revision">
          {history.loading && !history.data ? (
            <Spinner label="Loading stored experiments" />
          ) : history.error ? (
            <ErrorPanel
              title="History could not be loaded"
              message={history.error.userMessage}
              code={history.error.code}
              action={
                <Button variant="secondary" onClick={history.reload}>
                  Retry
                </Button>
              }
            />
          ) : (history.data?.experiment_count ?? 0) === 0 ? (
            <EmptyState
              title="No stored experiments yet"
              description="Executed experiments are persisted and replayable."
            />
          ) : (
            <div className="table-scroll">
      <table className="data-table" data-testid="history-table">
              <thead>
                <tr>
                  <th scope="col">Experiment</th>
                  <th scope="col">Suite</th>
                  <th scope="col">Revision</th>
                  <th scope="col">Status</th>
                  <th scope="col">Semantic hash</th>
                  <th scope="col">Replay</th>
                </tr>
              </thead>
              <tbody>
                {(history.data?.experiments ?? []).map((entry) => (
                  <tr key={entry.experiment_id} data-testid={`history-row-${entry.experiment_id}`}>
                    <th scope="row" className="mono">
                      {entry.experiment_id}
                    </th>
                    <td>{entry.suite_id ?? 'ad-hoc'}</td>
                    <td className="numeric">{entry.scenario_revision}</td>
                    <td>{entry.status}</td>
                    <td className="mono">{entry.semantic_hash.slice(0, 20)}…</td>
                    <td>
                      <Button
                        variant="ghost"
                        data-testid={`history-replay-${entry.experiment_id}`}
                        onClick={() => {
                          setSelectedExperimentId(entry.experiment_id)
                          void replayExperiment(entry.experiment_id)
                        }}
                      >
                        Replay
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
      </div>
          )}
          {replay ? (
            <p
              className={`failure-lab__replay ${replay.reproduced ? 'is-ok' : 'is-problem'}`}
              role="status"
              aria-live="polite"
              data-testid="replay-result"
            >
              <strong>{replay.reproduced ? 'Reproduced exactly' : 'Not reproduced'}.</strong>{' '}
              {replay.detail}
            </p>
          ) : null}
        </Panel>
      </div>
    </div>
  )
}

function LimitsPanel({ limits, loading }: { limits: Gate6Limits | null; loading: boolean }) {
  if (loading && !limits) return <Spinner label="Loading enforced limits" />
  if (!limits) return null
  return (
    <div className="failure-lab__limits" data-testid="fault-limits">
      <h3 className="failure-lab__subheading">Enforced limits</h3>
      <KeyValueList
        items={[
          { term: 'Faults per request', value: String(limits.max_faults_per_request) },
          { term: 'Faults per suite', value: String(limits.max_faults_per_suite) },
          { term: 'Experiments per suite', value: String(limits.max_experiments_per_suite) },
          { term: 'Targets per fault', value: String(limits.max_target_ids_per_fault) },
          { term: 'Suite duration bound', value: `${limits.max_suite_duration_ms} ms` },
          { term: 'Graph element bound', value: String(limits.max_graph_elements) },
        ]}
      />
      <p className="failure-lab__note">{limits.note}</p>
    </div>
  )
}

function ExperimentVisualComparison({ experiment }: { experiment: Gate6Experiment }) {
  const ws = useWorkspace()
  const diff = useResource(
    (signal) => ws.api.getFailureLabGraphDiff(experiment.experiment_id, signal),
    [ws.api, experiment.experiment_id],
    { enabled: Boolean(experiment.experiment_id) },
  )

  const changedIds = useMemo(
    () => new Set((diff.data?.element_changes ?? []).map((change) => change.element_id)),
    [diff.data],
  )

  const nodes = (ws.graph?.nodes ?? []) as never
  const edges = (ws.graph?.edges ?? []) as never

  return (
    <div className="failure-lab__compare">
      <div className="failure-lab__graphs">
        <figure className="failure-lab__graph">
          <figcaption>Baseline — phase {experiment.source.phase_ids.join(', ')}</figcaption>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            crossings={[]}
            overlays={{
              confirmedRouteEdgeIds: [],
              possibleRouteEdgeIds: [],
              closedEdgeIds: [],
              temporaryEdgeIds: [],
            }}
            height={260}
            ariaLabel="Baseline pedestrian network"
          />
        </figure>
        <figure className="failure-lab__graph">
          <figcaption>Faulted state — {diff.data?.isolated.graph_version_id ?? 'isolated copy'}</figcaption>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            crossings={[]}
            overlays={{
              confirmedRouteEdgeIds: [],
              possibleRouteEdgeIds: [],
              closedEdgeIds: [...changedIds],
              temporaryEdgeIds: [],
            }}
            height={260}
            ariaLabel="Faulted pedestrian network. Elements that changed are marked."
          />
        </figure>
      </div>

      <h3 className="failure-lab__subheading">Changed graph elements (text equivalent)</h3>
      {diff.loading && !diff.data ? (
        <Spinner label="Loading the element diff" />
      ) : (diff.data?.element_changes ?? []).length === 0 ? (
        <EmptyState
          title="No element changed"
          description="The modelled network state is identical before and after."
        />
      ) : (
        <div className="table-scroll">
      <table className="data-table" data-testid="element-change-table">
          <thead>
            <tr>
              <th scope="col">Element</th>
              <th scope="col">Change</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
              <th scope="col">Meaning</th>
            </tr>
          </thead>
          <tbody>
            {(diff.data?.element_changes ?? []).map((change) => (
              <tr
                key={`${change.phase_id}|${change.element_id}|${change.change}`}
                data-testid={`element-change-${change.element_id}`}
              >
                <th scope="row" className="mono">
                  {change.element_id}
                </th>
                <td>{change.change.replace(/_/g, ' ')}</td>
                <td>{change.before_state ?? '—'}</td>
                <td>{change.after_state ?? '—'}</td>
                <td>{change.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}

function ExperimentExplanation({ experiment }: { experiment: Gate6Experiment }) {
  const changed = experiment.transitions.filter(
    (transition) => transition.observation !== 'no_relevant_modelled_change',
  )

  return (
    <div className="failure-lab__explanation">
      {experiment.error ? (
        <div className="failure-lab__error" data-testid="experiment-error" role="alert">
          <h3 className="failure-lab__subheading">
            Execution problem — a software outcome, not a modelled failure
          </h3>
          <KeyValueList
            items={[
              { term: 'Stage', value: experiment.error.stage },
              { term: 'Code', value: experiment.error.code },
              { term: 'Message', value: experiment.error.message, wide: true },
            ]}
          />
          <p className="failure-lab__note">
            The plan was not tested. Nothing here indicates that the network failed.
          </p>
        </div>
      ) : null}

      <h3 className="failure-lab__subheading">What changed, and what it proves</h3>
      {changed.length === 0 ? (
        <EmptyState
          title="No modelled outcome changed"
          description="The injected condition left every selected origin-destination outcome and verdict as it was. That is reported as 'no relevant modelled change' — it is not presented as proof of safety."
        />
      ) : (
        <div className="table-scroll">
      <table className="data-table" data-testid="transition-table">
          <thead>
            <tr>
              <th scope="col">Profile</th>
              <th scope="col">Phase</th>
              <th scope="col">Pair</th>
              <th scope="col">Before</th>
              <th scope="col">After</th>
              <th scope="col">Consequence</th>
              <th scope="col">Distance</th>
            </tr>
          </thead>
          <tbody>
            {changed.map((transition) => (
              <tr
                key={`${transition.profile_id}|${transition.phase_id}|${transition.pair_id}`}
                data-testid={`transition-${transition.profile_id}-${transition.pair_id}`}
              >
                <td>{transition.profile_id}</td>
                <td>{transition.phase_id}</td>
                <th scope="row" className="mono">
                  {transition.pair_id}
                </th>
                <td>{reachabilityOf(transition.before_confirmed, transition.before_possible)}</td>
                <td>{reachabilityOf(transition.after_confirmed, transition.after_possible)}</td>
                <td>
                  <StatusBadge
                    meta={observationMeta(transition.observation)}
                    detail={transition.observation.replace(/_/g, ' ')}
                  />
                  <span
                    className="failure-lab__explanation-text"
                    data-testid={`transition-explanation-${transition.pair_id}`}
                  >
                    {transition.explanation}
                  </span>
                </td>
                <td>
                  {formatDistance(transition.before_distance_m)} →{' '}
                  {formatDistance(transition.after_distance_m)}
                  {transition.distance_delta_m === null ? (
                    <span className="failure-lab__muted"> (not comparable)</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}

      <h3 className="failure-lab__subheading">Fault definitions applied</h3>
      <ul className="failure-lab__fault-detail" data-testid="fault-definition-list">
        {experiment.faults.map((fault) => (
          <li key={fault.fault_id} data-testid={`fault-definition-${fault.fault_id}`}>
            <span className="mono">{fault.kind}</span>
            {fault.label ? <span> — {fault.label}</span> : null}
            {fault.target_ids.length > 0 ? (
              <span className="mono"> ({fault.target_ids.join(', ')})</span>
            ) : null}
            {fault.note ? <span className="failure-lab__note"> {fault.note}</span> : null}
            <span className="failure-lab__note mono">
              {' '}
              semantic hash {fault.semantic_hash.slice(0, 18)}…
            </span>
          </li>
        ))}
      </ul>

      <h3 className="failure-lab__subheading">Evidence changed inside the isolated context only</h3>
      {experiment.evidence_change_log.length === 0 ? (
        <p className="failure-lab__muted">No observation was masked or injected by this experiment.</p>
      ) : (
        <ul className="failure-lab__fault-detail" data-testid="evidence-change-log">
          {experiment.evidence_change_log.map((change, index) => (
            <li key={`${String(change.fault_id)}-${index}`}>
              <span className="mono">{String(change.kind)}</span> — {String(change.action)}
              {Array.isArray(change.element_ids) && change.element_ids.length > 0
                ? ` on ${(change.element_ids as string[]).join(', ')}`
                : ''}
              {change.field ? ` (${String(change.field)})` : ''}
              {Array.isArray(change.masked_evidence_ids)
                ? ` — masked ${(change.masked_evidence_ids as string[]).join(', ')}`
                : ''}
              {change.injected_evidence_id ? ` — injected ${String(change.injected_evidence_id)}` : ''}
              {change.note ? <span className="failure-lab__note"> {String(change.note)}</span> : null}
            </li>
          ))}
        </ul>
      )}

      <h3 className="failure-lab__subheading">Limits of this experiment</h3>
      <ul className="failure-lab__fault-detail" data-testid="experiment-limitations">
        {experiment.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  )
}

function ExperimentReproducibility({
  experiment,
  replay,
  onReplay,
  replaying,
}: {
  experiment: Gate6Experiment
  replay: ExperimentReplay | null
  onReplay: () => void
  replaying: boolean
}) {
  return (
    <div className="failure-lab__reproducibility">
      <KeyValueList
        items={[
          { term: 'Execution id', value: experiment.experiment_id },
          { term: 'Experiment semantic hash', value: experiment.semantic_hash, wide: true },
          { term: 'Input hash', value: experiment.input_hash, wide: true },
          {
            term: 'Source scenario',
            value: `${experiment.source.scenario_id} revision ${experiment.source.scenario_revision}`,
          },
          { term: 'Source scenario hash', value: experiment.source.scenario_content_hash, wide: true },
          { term: 'Source graph', value: experiment.source.base_graph_version_id },
          {
            term: 'Rulepack',
            value: `${experiment.source.rulepack_id} v${experiment.source.rulepack_version}`,
          },
          { term: 'Baseline instant', value: experiment.source.evaluation_instant },
          { term: 'Faulted instant', value: experiment.faulted_evaluation_instant },
          { term: 'Isolated graph hash', value: experiment.isolated_graph_hash, wide: true },
          { term: 'Isolated scenario hash', value: experiment.isolated_scenario_hash, wide: true },
          { term: 'Duration', value: `${experiment.duration_ms.toFixed(1)} ms` },
        ]}
      />
      <div className="failure-lab__actions">
        <Button
          variant="secondary"
          onClick={onReplay}
          disabled={replaying}
          data-testid="replay-experiment"
        >
          Replay this experiment
        </Button>
      </div>
      {replay ? (
        <p
          className={`failure-lab__replay ${replay.reproduced ? 'is-ok' : 'is-problem'}`}
          role="status"
          aria-live="polite"
          data-testid="replay-detail"
        >
          <strong>{replay.reproduced ? 'Reproduced exactly.' : 'Not reproduced.'}</strong> {replay.detail}
        </p>
      ) : null}
      <p className="failure-lab__note" data-testid="identity-note">
        The execution id, the input hash and the semantic hash are three different identities and are
        never substituted for one another.
      </p>
    </div>
  )
}

function RobustnessPanel({ summary }: { summary: Gate6Robustness | null }) {
  if (!summary) return null
  return (
    <div data-testid="panel-robustness">
      <Panel
        title="Robustness across the executed experiments"
        subtitle="A test-coverage result over the chosen conditions — not a probability of field failure"
      >
        <KeyValueList
          items={[
            { term: 'Experiments requested', value: String(summary.experiments_requested) },
            { term: 'Completed', value: String(summary.experiments_completed) },
            { term: 'Partially completed', value: String(summary.experiments_partially_completed) },
            { term: 'Invalid (refused, not tested)', value: String(summary.experiments_invalid) },
            { term: 'Execution failed', value: String(summary.experiments_failed) },
            { term: 'Fault kinds tested', value: summary.fault_kinds_tested.join(', ') || 'none', wide: true },
            {
              term: 'Fault kinds NOT tested',
              value: summary.fault_kinds_untested.join(', ') || 'none',
              wide: true,
            },
            { term: 'Origin-destination comparisons', value: String(summary.pairs_evaluated) },
            {
              term: 'Retained model-confirmed connectivity',
              value: String(summary.pairs_retaining_confirmed),
            },
            { term: 'Lost model-confirmed connectivity', value: String(summary.pairs_losing_confirmed) },
            { term: 'Became possible-only', value: String(summary.pairs_becoming_possible_only) },
            { term: 'Became disconnected', value: String(summary.pairs_becoming_disconnected) },
            { term: 'New known violations', value: String(summary.pairs_with_new_known_violation) },
            {
              term: 'New unresolved conditions',
              value: String(summary.pairs_with_new_unknown_condition),
            },
          ]}
        />
        <p className="failure-lab__note" data-testid="robustness-denominator">
          <strong>Denominator:</strong> {summary.denominator_note}
        </p>
        <p className="failure-lab__note" data-testid="robustness-interpretation">
          <strong>Interpretation:</strong> {summary.interpretation_note}
        </p>
      </Panel>
    </div>
  )
}