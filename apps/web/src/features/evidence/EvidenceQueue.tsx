import { useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { SelectField, TextField } from '@/components/Field'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { useResource } from '@/lib/useResource'
import { criticalityMeta, evidenceStatusMeta, reachabilityOf } from '@/lib/gate6'
import type { Gate6ConflictReport, Gate6Issue } from '@/api/types'
import './evidence-queue.css'

/**
 * Evidence verification queue (Gate 6, G6-01..G6-04).
 *
 * Everything rendered here comes from the backend's derived queue. The client
 * performs no accessibility reasoning: it does not decide which attribute
 * matters, does not re-rank, and does not translate an unresolved condition
 * into a conclusion. Filtering asks the server the same question with a narrower
 * selection and renders exactly what comes back.
 *
 * Two honesty rules are enforced in the markup rather than left to copy:
 * - the machine-readable `resolution_status` is always rendered next to the
 *   readable label, so the five evidence conditions stay distinguishable;
 * - every priority carries its own rationale, and no numeric "importance"
 *   score is displayed, because none is computed.
 */

const STATUS_OPTIONS = [
  'NO_EVIDENCE',
  'CONFLICTING_EVIDENCE',
  'UNSUPPORTED_UNIT',
  'EVIDENCE_EXPIRED',
  'EVIDENCE_NOT_VERIFIED',
] as const

const CRITICALITY_OPTIONS = ['decision_blocking', 'decision_relevant', 'supporting'] as const

export function EvidenceQueue() {
  const ws = useWorkspace()
  const { api, scenarioId, profileId, phaseId, evaluationInstant } = ws
  const [statusFilter, setStatusFilter] = useState('')
  const [criticalityFilter, setCriticalityFilter] = useState('')
  const [elementFilter, setElementFilter] = useState('')
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)

  const queue = useResource(
    (signal) =>
      api.getEvidenceQueue(
        scenarioId as string,
        {
          phaseIds: [phaseId],
          profileIds: [profileId],
          statuses: statusFilter ? [statusFilter] : [],
          criticalities: criticalityFilter ? [criticalityFilter] : [],
          elementId: elementFilter.trim() || undefined,
        },
        signal,
      ),
    [api, scenarioId, phaseId, profileId, statusFilter, criticalityFilter, elementFilter],
    { enabled: Boolean(scenarioId && phaseId && profileId) },
  )

  const issues = queue.data?.issues ?? []

  const detail = useResource(
    (signal) =>
      api.getEvidenceIssue(
        scenarioId as string,
        selectedIssueId as string,
        { phaseIds: [phaseId], profileIds: [profileId] },
        signal,
      ),
    [api, scenarioId, selectedIssueId, phaseId, profileId],
    { enabled: Boolean(scenarioId && selectedIssueId) },
  )

  const totalUnresolved = queue.data?.total_unresolved_attributes_scanned ?? 0

  return (
    <div className="queue">
      <div data-testid="queue-main">
        <Panel
          title="Evidence verification queue"
          subtitle={`Phase ${phaseId} · profile ${profileId}`}
        >
          {queue.loading && issues.length === 0 ? (
            <Spinner label="Deriving the verification queue from the authoritative resolver" />
          ) : null}

          {queue.error ? (
            <ErrorPanel
              title="The queue could not be derived"
              message={queue.error.userMessage}
              code={queue.error.code}
              action={
                <Button variant="secondary" onClick={queue.reload} data-testid="queue-retry">
                  Retry
                </Button>
              }
            />
          ) : null}

          {queue.data ? (
            <>
              <p className="queue__scope" data-testid="queue-scope">
                {totalUnresolved} unresolved attribute{totalUnresolved === 1 ? '' : 's'} found for this
                selection; showing <strong data-testid="queue-count">{issues.length}</strong> after
                filtering. {queue.data.scope.scope_note}
              </p>

              <div className="queue__filters">
                <SelectField
                  label="Evidence condition"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  data-testid="queue-status-filter"
                >
                  <option value="">All conditions</option>
                  {STATUS_OPTIONS.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </SelectField>

                <SelectField
                  label="Decision relevance"
                  value={criticalityFilter}
                  onChange={(event) => setCriticalityFilter(event.target.value)}
                  data-testid="queue-criticality-filter"
                >
                  <option value="">All categories</option>
                  {CRITICALITY_OPTIONS.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </SelectField>

                <div data-testid="queue-element-filter">
                  <TextField
                    label="Element id"
                    value={elementFilter}
                    onChange={setElementFilter}
                    placeholder="e.g. E_K1"
                  />
                </div>

                <div className="queue__filter-actions">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setStatusFilter('')
                      setCriticalityFilter('')
                      setElementFilter('')
                    }}
                    data-testid="queue-clear-filters"
                  >
                    Clear filters
                  </Button>
                </div>
              </div>

              <div className="queue__counts" data-testid="queue-counts">
                {Object.entries(queue.data.counts_by_status).map(([status, count]) => (
                  <span key={status} data-testid={`queue-status-count-${status}`}>
                    <StatusBadge meta={evidenceStatusMeta(status)} detail={`${count}`} />
                    <span className="queue__status-label">{status}</span>
                  </span>
                ))}
              </div>

              {issues.length === 0 ? (
                <EmptyState
                  title="No unresolved attribute matches this selection"
                  description={
                    totalUnresolved === 0
                      ? 'Every attribute a rule in scope reads has been resolved for this phase and profile.'
                      : 'Every unresolved attribute was removed by the filters above.'
                  }
                />
              ) : (
                <table className="data-table" data-testid="queue-table">
                  <caption className="visually-hidden">
                    Unresolved attributes ordered by decision relevance. Priority is an explainable
                    category, not a score.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Rank</th>
                      <th scope="col">Element</th>
                      <th scope="col">Attribute</th>
                      <th scope="col">Evidence condition</th>
                      <th scope="col">Decision relevance</th>
                      <th scope="col">Affected</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.map((issue, index) => (
                      <tr
                        key={issue.issue_id}
                        data-testid={`queue-row-${issue.issue_id}`}
                        className={selectedIssueId === issue.issue_id ? 'is-selected' : undefined}
                      >
                        <td className="numeric">{index + 1}</td>
                        <th scope="row">
                          <span className="mono">{issue.element_id}</span>
                          <span className="queue__element-kind"> ({issue.element_kind})</span>
                        </th>
                        <td className="mono">{issue.attribute}</td>
                        <td>
                          <StatusBadge meta={evidenceStatusMeta(issue.resolution_status)} />
                          <span className="queue__status-label mono" data-testid={`queue-status-${issue.issue_id}`}>
                            {issue.resolution_status}
                          </span>
                        </td>
                        <td>
                          <StatusBadge
                            meta={criticalityMeta(issue.criticality)}
                            detail={issue.criticality}
                          />
                        </td>
                        <td className="queue__affected">
                          <span className="queue__affected-line">
                            profiles: {issue.affected_profile_ids.length}
                          </span>
                          <span className="queue__affected-line">
                            phases: {issue.affected_phase_ids.join(', ') || '—'}
                          </span>
                          <span className="queue__affected-line">OD pairs: {issue.od_pair_count}</span>
                        </td>
                        <td>
                          <Button
                            variant="secondary"
                            data-testid={`queue-inspect-${issue.issue_id}`}
                            onClick={() => setSelectedIssueId(issue.issue_id)}
                          >
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <p className="queue__method" data-testid="queue-method">
                <strong>How this order is produced.</strong> {queue.data.prioritization_method}
                <br />
                <strong>Ordering rule.</strong> {queue.data.ordering_rule}
              </p>
              <ul className="queue__limitations" data-testid="queue-limitations">
                {queue.data.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </>
          ) : null}
        </Panel>
      </div>

      <div className="queue__detail" data-testid="queue-detail">
        {selectedIssueId === null ? (
          <Panel title="Issue detail">
            <EmptyState
              title="Select an issue"
              description="Choose an entry from the queue to read the resolver's own explanation, every observation behind it, and what to check next."
            />
          </Panel>
        ) : detail.loading ? (
          <Panel title="Issue detail">
            <Spinner label="Loading the resolver explanation" />
          </Panel>
        ) : detail.error ? (
          <Panel title="Issue detail">
            <ErrorPanel
              title="This issue could not be loaded"
              message={detail.error.userMessage}
              code={detail.error.code}
              action={
                <Button variant="secondary" onClick={detail.reload} data-testid="detail-retry">
                  Retry
                </Button>
              }
            />
          </Panel>
        ) : detail.data ? (
          <IssueInspector
            detail={detail.data}
            onSelectElement={(elementId, kind) => {
              if (kind === 'edge') ws.selectEdge(elementId)
              else ws.selectNode(elementId)
              ws.setView('network')
            }}
            onOpenFailureLab={() => ws.setView('failure-lab')}
            onOpenAnalysis={() => ws.setView('analysis')}
          />
        ) : null}
      </div>

      <p className="visually-hidden" role="status" aria-live="polite">
        {queue.loading
          ? 'Deriving the evidence queue'
          : `${issues.length} unresolved attributes listed for phase ${phaseId}.`}
      </p>
      <p className="visually-hidden">
        Evaluation instant {evaluationInstant}. {queue.data?.ordering_rule ?? ''}
      </p>
    </div>
  )
}

function IssueInspector({
  detail,
  onSelectElement,
  onOpenFailureLab,
  onOpenAnalysis,
}: {
  detail: { issue: Gate6Issue; resolver_explanation: Gate6ConflictReport }
  onSelectElement: (elementId: string, kind: 'edge' | 'node') => void
  onOpenFailureLab: () => void
  onOpenAnalysis: () => void
}) {
  const { issue, resolver_explanation: explanation } = detail

  return (
    <Panel title={`${issue.element_id} · ${issue.attribute}`} subtitle={issue.status_label}>
      <div className="queue__detail-badges" data-testid="detail-badges">
        <StatusBadge meta={evidenceStatusMeta(issue.resolution_status)} detail={issue.resolution_status} />
        <StatusBadge meta={criticalityMeta(issue.criticality)} detail={issue.criticality} />
        <span className="mono queue__issue-id" data-testid="detail-issue-id">
          {issue.issue_id}
        </span>
      </div>

      <KeyValueList
        items={[
          { term: 'Scope', value: issue.scope, wide: true },
          {
            term: 'Element',
            value: `${issue.element_kind} ${issue.element_id} (${issue.element_name})`,
            wide: true,
          },
          { term: 'Affected profiles', value: issue.affected_profile_ids.join(', ') || 'none' },
          { term: 'Affected phases', value: issue.affected_phase_ids.join(', ') || 'none' },
          { term: 'Rules reading it', value: issue.rule_ids.join(', ') || 'none' },
          { term: 'Evidence records', value: issue.evidence_record_ids.join(', ') || 'none recorded' },
          {
            term: 'Recorded measurement',
            value: issue.recorded_measurement ?? 'none — the resolver has no value',
          },
          { term: 'Missing or conflicting', value: issue.missing_or_conflicting, wide: true },
        ]}
      />

      <h3 className="queue__subheading">Why this matters for the selected decision</h3>
      <ul className="queue__rationale" data-testid="detail-rationale">
        {issue.criticality_rationale.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>

      <h3 className="queue__subheading">Resolver explanation</h3>
      <p className="queue__explanation" data-testid="detail-explanation">
        {explanation.explanation}
      </p>
      <p className="queue__requirement">
        <strong>What is required to resolve it:</strong> {explanation.resolution_requirement}
      </p>
      <p className="queue__requirement" data-testid="detail-selection-note">
        {explanation.selected_value_note}
      </p>
      <p className="queue__requirement">
        <strong>Can this be resolved without field work?</strong>{' '}
        {explanation.can_be_resolved_without_field_work ? 'Yes.' : 'No.'}
      </p>

      <h3 className="queue__subheading">Observations behind this attribute</h3>
      {explanation.observations.length === 0 ? (
        <EmptyState
          title="No observation is recorded"
          description="There is nothing to reconcile. The attribute has no value at all, which is why it is unresolved."
        />
      ) : (
        <table className="data-table" data-testid="detail-observations">
          <thead>
            <tr>
              <th scope="col">Record</th>
              <th scope="col">Value</th>
              <th scope="col">Unit</th>
              <th scope="col">Observed</th>
              <th scope="col">Verification</th>
              <th scope="col">Provenance</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {explanation.observations.map((observation) => (
              <tr key={observation.evidence_id} data-testid={`observation-${observation.evidence_id}`}>
                <th scope="row" className="mono">
                  {observation.evidence_id}
                </th>
                <td className="numeric">
                  {observation.value === null ? '—' : String(observation.value)}
                </td>
                <td>{observation.unit ?? '—'}</td>
                <td>{observation.observed_at ?? 'no timestamp'}</td>
                <td>{observation.verification_status}</td>
                <td>{observation.provenance_class}</td>
                <td>{observation.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {explanation.distinct_values.length > 0 ? (
        <p className="queue__conflict" data-testid="detail-conflict-values">
          <strong>Distinct recorded claims:</strong> {explanation.distinct_values.join(' | ')} — all
          retained, none selected.
        </p>
      ) : null}

      {issue.od_pairs.length > 0 ? (
        <>
          <h3 className="queue__subheading">Connected origin-destination outcomes</h3>
          <table className="data-table" data-testid="detail-od-pairs">
            <thead>
              <tr>
                <th scope="col">Profile</th>
                <th scope="col">Phase</th>
                <th scope="col">Pair</th>
                <th scope="col">Role</th>
                <th scope="col">Current state</th>
              </tr>
            </thead>
            <tbody>
              {issue.od_pairs.map((pair) => (
                <tr key={`${pair.phase_id}|${pair.profile_id}|${pair.pair_id}`}>
                  <td>{pair.profile_id}</td>
                  <td>{pair.phase_id}</td>
                  <th scope="row" className="mono">
                    {pair.pair_id}
                  </th>
                  <td>
                    {pair.role}
                    {pair.role === 'relevant'
                      ? ' — structural relevance only, not a demonstrated cause'
                      : ''}
                  </td>
                  <td>{reachabilityOf(pair.confirmed_reachable, pair.possibly_reachable)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      <div className="queue__actions">
        <Button
          variant="secondary"
          data-testid={`detail-open-element-${issue.issue_id}`}
          onClick={() => onSelectElement(issue.element_id, issue.element_kind)}
        >
          Inspect {issue.element_id} on the graph
        </Button>
        <Button variant="ghost" data-testid={`detail-open-analysis-${issue.issue_id}`} onClick={onOpenAnalysis}>
          Back to analysis
        </Button>
        <Button
          variant="ghost"
          data-testid={`detail-open-failure-lab-${issue.issue_id}`}
          onClick={onOpenFailureLab}
        >
          Test what happens if this stays unresolved
        </Button>
      </div>

      <p className="queue__caveat" data-testid="detail-caveat">
        An unresolved attribute means the model cannot determine the condition. It is not a physical
        defect, and nothing here verifies, re-measures or resolves any observation.
      </p>
    </Panel>
  )
}