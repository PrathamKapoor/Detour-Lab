import { useState, type FormEvent, type ReactNode } from 'react'
import { ApiError, type ApiClient } from '@/api/client'
import { Button, ErrorPanel } from '@/components/Button'
import { KeyValueList, ToneBadge } from '@/components/StatusBadge'
import type {
  CandidateEvaluation,
  ODTransition,
  PromotionResult,
  SearchOutcome,
} from '@/api/types'
import { formatHash, formatMetres } from '@/lib/format'
import { REACHABILITY_META, reachabilityOf } from '@/lib/status'
import {
  budgetMeta,
  classificationMeta,
  formatCost,
  formatSignedMetres,
  solverStatusLabel,
} from './presentation'

interface CandidateDetailProps {
  outcome: SearchOutcome
  candidate: CandidateEvaluation
  /** Current revision of the source scenario; promotion is refused if stale. */
  expectedSourceRevision: number | null
  api: Pick<ApiClient, 'promoteProposal'>
  names?: Readonly<Record<string, string>>
  onPromoted?: (result: PromotionResult) => void
  onOpenBranch?: (scenarioId: string) => void
}

function reachabilityCell(
  confirmed: boolean,
  possible: boolean,
  distance: number | null | undefined,
): ReactNode {
  const reach = reachabilityOf(confirmed, possible)
  const meta = REACHABILITY_META[reach]
  return (
    <span className="opt-chips">
      <ToneBadge tone={meta.tone} glyph={meta.glyph} title={meta.description}>
        {meta.label}
      </ToneBadge>
      {reach !== 'none' ? <span className="mono">{formatMetres(distance)}</span> : null}
    </span>
  )
}

function transitionKey(transition: ODTransition): string {
  return `${transition.origin_id}->${transition.destination_id}`
}

function verdictEntryLabel(entry: Record<string, string>): string {
  return Object.entries(entry)
    .map(([key, value]) => `${key}=${value}`)
    .join(' · ')
}

/**
 * Panel E - one candidate in full: per-profile OD transitions, introduced
 * verdicts, assumptions, costs and the explicit apply-to-branch action.
 *
 * Mount with `key={proposal_id}` so the promotion form resets per candidate.
 */
export function CandidateDetail({
  outcome,
  candidate,
  expectedSourceRevision,
  api,
  names,
  onPromoted,
  onOpenBranch,
}: CandidateDetailProps) {
  const proposal = candidate.proposal
  const meta = classificationMeta(candidate.classification)
  const [branchId, setBranchId] = useState(
    () => `scn-fix-${proposal.proposal_id.replace(/^cand-/, '')}`,
  )
  const [branchName, setBranchName] = useState(
    () => `Fix: ${candidate.intervention_ids.map((id) => names?.[id] ?? id).join(' + ')}`,
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [result, setResult] = useState<PromotionResult | null>(null)
  const [idTouched, setIdTouched] = useState(false)

  const promotionAllowed = expectedSourceRevision !== null && !submitting

  async function submitPromotion(event: FormEvent) {
    event.preventDefault()
    if (!promotionAllowed || expectedSourceRevision === null) return
    setSubmitting(true)
    setError(null)
    try {
      const promotion = await api.promoteProposal({
        search_id: outcome.search_id,
        proposal_id: proposal.proposal_id,
        new_scenario_id: branchId.trim(),
        new_scenario_name: branchName.trim(),
        expected_source_revision: expectedSourceRevision,
      })
      setResult(promotion)
      onPromoted?.(promotion)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, { code: 'UNEXPECTED' }, String(caught)),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div data-testid="candidate-detail">
      <div className="opt-chips">
        <ToneBadge tone={meta.tone} glyph={meta.glyph} title={meta.description}>
          {meta.label}
        </ToneBadge>
        {candidate.rank !== null && candidate.rank !== undefined ? (
          <span className="opt-chip">rank {candidate.rank}</span>
        ) : null}
        {candidate.pareto_optimal ? (
          <span className="opt-chip" title="Not dominated on restoration, count or distance">
            Pareto-optimal
          </span>
        ) : null}
        {candidate.tie_group !== null && candidate.tie_group !== undefined ? (
          <span
            className="opt-chip"
            title="Ties on every measured axis; ordered deterministically by proposal id"
          >
            tie group {candidate.tie_group}
          </span>
        ) : null}
        <span className="opt-chip mono" data-testid="proposal-id">
          {proposal.proposal_id}
        </span>
      </div>

      <div className="opt-section">
        <h4>Interventions</h4>
        <ul className="opt-reasons">
          {candidate.intervention_ids.map((id) => (
            <li key={id}>
              <span className="mono">{id}</span>
              {names?.[id] ? ` - ${names[id]}` : ''}
            </li>
          ))}
        </ul>
      </div>

      {(proposal.rejection_reasons ?? []).length > 0 ? (
        <div className="opt-section">
          <h4>Rejection reasons (hard constraints)</h4>
          <ul className="opt-reasons" data-testid="rejection-reasons">
            {(proposal.rejection_reasons ?? []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {candidate.evaluation_failure ? (
        <div className="opt-banner" data-testid="evaluation-failure">
          The engine could not complete the evaluation for this candidate:{' '}
          <span className="mono">
            {Object.entries(candidate.evaluation_failure)
              .map(([key, value]) => `${key}=${String(value)}`)
              .join(' · ')}
          </span>
        </div>
      ) : null}

      <div className="opt-section">
        <h4>Origin-destination transitions (real runs, before vs after)</h4>
        <div className="opt-scroll">
          <table className="data-table" data-testid="transition-table">
            <thead>
              <tr>
                <th scope="col">Profile</th>
                <th scope="col">Pair</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
                <th scope="col">Added distance</th>
              </tr>
            </thead>
            <tbody>
              {candidate.verifications.flatMap((verification) =>
                verification.od_transitions.map((transition) => {
                  const restored = verification.restored_pairs.includes(transitionKey(transition))
                  const regressed = verification.regressed_pairs.includes(transitionKey(transition))
                  return (
                    <tr key={`${verification.profile_id}-${transitionKey(transition)}`}>
                      <td className="data-table__mono">{verification.profile_id}</td>
                      <td className="data-table__mono">
                        {transitionKey(transition)}
                        {restored ? (
                          <>
                            {' '}
                            <ToneBadge tone="pass" glyph="↺" title="Not confirmed before; confirmed after">
                              Restored
                            </ToneBadge>
                          </>
                        ) : null}
                        {regressed ? (
                          <>
                            {' '}
                            <ToneBadge tone="fail" glyph="↓" title="Confirmed or possible before; lost after">
                              Regressed
                            </ToneBadge>
                          </>
                        ) : null}
                      </td>
                      <td>
                        {reachabilityCell(
                          transition.before_confirmed,
                          transition.before_possible,
                          transition.before_distance_m,
                        )}
                      </td>
                      <td>
                        {reachabilityCell(
                          transition.after_confirmed,
                          transition.after_possible,
                          transition.after_distance_m,
                        )}
                      </td>
                      <td className="data-table__mono">
                        {formatSignedMetres(transition.added_distance_m)}
                      </td>
                    </tr>
                  )
                }),
              )}
            </tbody>
          </table>
        </div>
        <p className="opt-note">
          Added distance is only stated when both sides have a confirmed route; a missing route is
          never counted as 0 m.
        </p>
      </div>

      {candidate.assumptions && candidate.assumptions.length > 0 ? (
        <div className="opt-section">
          <h4>Modelled values this candidate introduces</h4>
          <ul className="opt-reasons" data-testid="assumptions">
            {candidate.assumptions.map((assumption) => (
              <li key={`${assumption.intervention_id}-${assumption.element_id}-${assumption.field}`}>
                <span className="mono">{assumption.element_id}</span> {assumption.field} ={' '}
                {assumption.value_display}
                {assumption.unit ? ` ${assumption.unit}` : ''} - provenance{' '}
                <span className="mono">{assumption.provenance_class}</span>, evidence{' '}
                <span className="mono">{assumption.verification_status}</span>.{' '}
                {assumption.note}
                {assumption.requires_field_verification ? (
                  <>
                    {' '}
                    <ToneBadge
                      tone="temp"
                      glyph="◇"
                      title="A modelled value that must be confirmed in the field before construction use"
                    >
                      Field verification required
                    </ToneBadge>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {candidate.applied_phase_changes && candidate.applied_phase_changes.length > 0 ? (
        <div className="opt-section">
          <h4>Phase changes applied by this candidate</h4>
          <ul className="opt-reasons" data-testid="phase-changes">
            {candidate.applied_phase_changes.map((change, index) => (
              <li key={index} className="mono">
                {Object.entries(change)
                  .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
                  .join(' · ')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {candidate.verifications.some(
        (verification) =>
          verification.new_fail_verdicts.length > 0 || verification.new_unknown_verdicts.length > 0,
      ) ? (
        <div className="opt-section">
          <h4>Verdict transitions introduced (never traded against gains)</h4>
          {candidate.verifications.map((verification) =>
            verification.new_fail_verdicts.length > 0 ||
            verification.new_unknown_verdicts.length > 0 ? (
              <div key={verification.profile_id}>
                <h5 className="opt-note">{verification.profile_id}</h5>
                {verification.new_fail_verdicts.length > 0 ? (
                  <ul className="opt-reasons" data-testid="new-fails">
                    {verification.new_fail_verdicts.map((entry, index) => (
                      <li key={index} className="mono">
                        FAIL {verdictEntryLabel(entry)}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {verification.new_unknown_verdicts.length > 0 ? (
                  <ul className="opt-reasons" data-testid="new-unknowns">
                    {verification.new_unknown_verdicts.map((entry, index) => (
                      <li key={index} className="mono">
                        UNKNOWN {verdictEntryLabel(entry)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null,
          )}
        </div>
      ) : null}

      <div className="opt-section">
        <h4>Cost (demo prices only - never estimated on your behalf)</h4>
        <KeyValueList
          items={[
            {
              term: 'Nominal total',
              value: formatCost(proposal.cost_nominal ?? null, candidate.cost.currency ?? null),
            },
            {
              term: 'Declared upper bound',
              value: formatCost(proposal.cost_max ?? null, candidate.cost.currency ?? null),
            },
            {
              term: 'Unknown cost items',
              value: candidate.cost.unknown ? 'Yes - "Not estimated" wherever a price is absent' : 'None',
            },
            {
              term: 'Budget check',
              value: (() => {
                const budget = budgetMeta(candidate.budget.status)
                return (
                  <span className="opt-chips">
                    <ToneBadge tone={budget.tone} glyph={budget.tone === 'pass' ? '✓' : '?'} title={budget.description}>
                      {budget.label}
                    </ToneBadge>
                    {candidate.budget.detail ? (
                      <span className="opt-note">{candidate.budget.detail}</span>
                    ) : null}
                  </span>
                )
              })(),
            },
          ]}
        />
        {candidate.cost.lines && candidate.cost.lines.length > 0 ? (
          <div className="opt-scroll opt-section">
            <table className="data-table" data-testid="cost-table">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Provenance</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Nominal</th>
                  <th scope="col">Upper bound</th>
                </tr>
              </thead>
              <tbody>
                {candidate.cost.lines.map((line) => (
                  <tr key={`${line.intervention_id}-${line.cost_id}`}>
                    <td>
                      <span className="mono">{line.label}</span>
                      <div className="opt-note">{line.intervention_id}</div>
                    </td>
                    <td className="data-table__mono">{line.provenance}</td>
                    <td className="data-table__mono">
                      {line.quantity}
                      {line.unit ? ` ${line.unit}` : ''}
                    </td>
                    <td className="data-table__mono">
                      {formatCost(line.total_nominal ?? null, line.currency)}
                    </td>
                    <td className="data-table__mono">{formatCost(line.total_max ?? null, line.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {candidate.cost.provenance_notes && candidate.cost.provenance_notes.length > 0 ? (
          <ul className="opt-reasons">
            {candidate.cost.provenance_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="opt-section">
        <h4>Verification identity</h4>
        <KeyValueList
          items={[
            { term: 'Search id', value: <span className="mono">{outcome.search_id}</span> },
            {
              term: 'Preview scenario hash',
              value: <span className="mono">{formatHash(candidate.preview_scenario_hash)}</span>,
            },
            {
              term: 'Preview phase graph hash',
              value: <span className="mono">{formatHash(candidate.preview_phase_graph_hash)}</span>,
            },
            {
              term: 'Solver status',
              value: solverStatusLabel(proposal.solver_status),
            },
          ]}
        />
      </div>

      <div className="opt-section" data-testid="promote-section">
        <h4>Apply to branch (creates a new scenario; the source is never modified)</h4>
        {candidate.classification === 'rejected' ? (
          <div className="opt-banner">
            This candidate is rejected under the hard constraints above. If you submit it anyway the
            server will refuse it with the recorded reasons.
          </div>
        ) : null}
        <form className="opt-promote" onSubmit={submitPromotion}>
          <label className="opt-field">
            New scenario id
            <input
              type="text"
              value={branchId}
              data-testid="promote-id"
              onChange={(event) => {
                setIdTouched(true)
                setBranchId(event.target.value)
              }}
              required
            />
          </label>
          <label className="opt-field">
            New scenario name
            <input
              type="text"
              value={branchName}
              data-testid="promote-name"
              onChange={(event) => setBranchName(event.target.value)}
              required
            />
          </label>
          <Button
            type="submit"
            variant="primary"
            busy={submitting}
            disabled={!promotionAllowed}
            data-testid="promote-submit"
          >
            Apply to branch
          </Button>
        </form>
        <p className="opt-note">
          The branch is created transactionally against source revision{' '}
          {expectedSourceRevision ?? 'unknown'} and re-verified with the real engine; a mismatch or
          stale revision is refused, never silently accepted.
          {idTouched ? '' : ' The suggested id is derived from the proposal id.'}
        </p>
        {error ? (
          <ErrorPanel
            title="Promotion refused"
            message={error.userMessage}
            code={error.code}
          />
        ) : null}
      </div>

      {result ? (
        <div className="opt-section" data-testid="promotion-result">
          <h4>Branch created and re-verified</h4>
          <KeyValueList
            items={[
              { term: 'Branch', value: <span className="mono">{result.branch.scenario_id}</span> },
              { term: 'Name', value: result.branch.name },
              { term: 'Branch revision', value: String(result.branch.revision) },
              {
                term: 'Parent',
                value: <span className="mono">{result.branch.parent_scenario_id ?? '—'}</span>,
              },
              {
                term: 'Content hash',
                value: <span className="mono">{formatHash(result.branch.content_hash)}</span>,
              },
              {
                term: 'Source unchanged',
                value: result.source.unchanged ? 'Yes (revision and hash identical)' : 'NO - investigate',
              },
            ]}
          />
          <div className="opt-section">
            <h5>Persisted-vs-preview verification</h5>
            <ul className="opt-reasons">
              {result.verification.per_profile.map((row) => (
                <li key={row.profile_id}>
                  <span className="mono">{row.profile_id}</span>{' '}
                  {row.match ? (
                    <ToneBadge tone="pass" glyph="✓" title="Persisted analysis reproduces the preview exactly">
                      Reproduces preview
                    </ToneBadge>
                  ) : (
                    <ToneBadge tone="fail" glyph="✕" title="Persisted analysis differs from the preview">
                      MISMATCH
                    </ToneBadge>
                  )}
                </li>
              ))}
            </ul>
            {result.od_summary.restored_all_profiles.length > 0 ? (
              <p className="opt-note">
                Restored for every selected profile: {result.od_summary.restored_all_profiles.join(', ')}
              </p>
            ) : null}
          </div>
          <ul className="opt-disclaimers">
            {result.disclaimers.map((disclaimer) => (
              <li key={disclaimer}>{disclaimer}</li>
            ))}
          </ul>
          {onOpenBranch ? (
            <Button
              variant="secondary"
              onClick={() => onOpenBranch(result.branch.scenario_id)}
              data-testid="open-branch"
            >
              Open the branch
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
