import { ToneBadge } from '@/components/StatusBadge'
import type { CandidateEvaluation, SearchOutcome } from '@/api/types'
import {
  classificationMeta,
  formatCostSummary,
  formatSignedMetres,
  solverStatusLabel,
  solverStatusTone,
} from './presentation'

interface CandidateTableProps {
  outcome: SearchOutcome
  selectedProposalId: string | null
  onSelect: (proposalId: string) => void
  /** Display names for intervention ids, from the library catalogue. */
  names?: Readonly<Record<string, string>>
}

function interventionLabel(id: string, names: Readonly<Record<string, string>> | undefined): string {
  const name = names?.[id]
  return name ? `${name} (${id})` : id
}

/**
 * Panel D - the ranked candidate list. Rank, classification, restoration and
 * deltas are the engine's own values; the table never re-orders them.
 */
export function CandidateTable({ outcome, selectedProposalId, onSelect, names }: CandidateTableProps) {
  return (
    <div className="opt-scroll">
      <table className="data-table" data-testid="candidate-table">
        <thead>
          <tr>
            <th scope="col">Rank</th>
            <th scope="col">Classification</th>
            <th scope="col">Interventions</th>
            <th scope="col">Restores (all profiles)</th>
            <th scope="col">Added distance</th>
            <th scope="col">Cost</th>
            <th scope="col">New hard FAILs</th>
            <th scope="col">New UNKNOWNs</th>
            <th scope="col">Solver status</th>
          </tr>
        </thead>
        <tbody>
          {outcome.candidates.map((candidate: CandidateEvaluation) => {
            const proposal = candidate.proposal
            const meta = classificationMeta(candidate.classification)
            const selected = proposal.proposal_id === selectedProposalId
            const isBest = outcome.status.best_proposal_id === proposal.proposal_id
            return (
              <tr
                key={proposal.proposal_id}
                className={selected ? 'opt-row opt-row--selected' : 'opt-row'}
                data-testid={`candidate-row-${proposal.proposal_id}`}
                data-intervention-ids={candidate.intervention_ids.join(' ')}
                aria-selected={selected}
                onClick={() => onSelect(proposal.proposal_id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(proposal.proposal_id)
                  }
                }}
                tabIndex={0}
              >
                <td className="data-table__mono">
                  {candidate.rank ?? '–'}
                  {isBest ? (
                    <div>
                      <ToneBadge tone="info" glyph="★" title="Ranked first by the declared policy">
                        Best
                      </ToneBadge>
                    </div>
                  ) : null}
                  {candidate.pareto_optimal ? (
                    <div>
                      <ToneBadge
                        tone="temp"
                        glyph="◇"
                        title="Not dominated on restoration, intervention count or comparable distance"
                      >
                        Pareto
                      </ToneBadge>
                    </div>
                  ) : null}
                </td>
                <td>
                  <ToneBadge tone={meta.tone} glyph={meta.glyph} title={meta.description}>
                    {meta.label}
                  </ToneBadge>
                  {(proposal.rejection_reasons ?? []).length > 0 ? (
                    <ul className="opt-reasons">
                      {(proposal.rejection_reasons ?? []).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}
                </td>
                <td>
                  {candidate.intervention_ids.length === 0 ? (
                    <span className="mono">(no intervention)</span>
                  ) : (
                    <ul className="opt-reasons">
                      {candidate.intervention_ids.map((id) => (
                        <li key={id} className="mono">
                          {interventionLabel(id, names)}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
                <td className="data-table__mono">
                  {candidate.restored_all_profiles && candidate.restored_all_profiles.length > 0
                    ? candidate.restored_all_profiles.join(', ')
                    : 'none'}
                  {candidate.restored_any_profile && candidate.restored_any_profile.length > 0 ? (
                    <div className="opt-note">
                      some profile: {candidate.restored_any_profile.join(', ')}
                    </div>
                  ) : null}
                </td>
                <td className="data-table__mono">{formatSignedMetres(proposal.added_distance_m)}</td>
                <td className="data-table__mono">{formatCostSummary(candidate.cost)}</td>
                <td className="data-table__mono">{candidate.introduced_fail_verdict_count ?? 0}</td>
                <td className="data-table__mono">{candidate.introduced_unknown_verdict_count ?? 0}</td>
                <td>
                  <ToneBadge
                    tone={solverStatusTone(proposal.solver_status)}
                    glyph={proposal.solver_status === 'OPTIMAL_IN_ENUMERATED_DOMAIN' ? '✓' : '~'}
                    title={solverStatusLabel(proposal.solver_status)}
                  >
                    {proposal.solver_status === 'OPTIMAL_IN_ENUMERATED_DOMAIN'
                      ? 'Optimal in domain'
                      : 'Feasible, not proven optimal'}
                  </ToneBadge>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
