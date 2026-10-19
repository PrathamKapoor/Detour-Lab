import { ToneBadge } from '@/components/StatusBadge'
import type { InterventionCatalog } from '@/api/types'
import { formatCost } from './presentation'

interface LibraryPanelProps {
  catalog: InterventionCatalog
  /** Intervention ids the user has excluded from the next search. */
  excludedIds: readonly string[]
  onToggleExcluded?: (interventionId: string) => void
}

/**
 * Panel B - the bundled intervention library as applicable to the selected
 * phase. Eligibility reasons come from the backend's own precondition and
 * target assessment; this component only renders them.
 */
export function LibraryPanel({ catalog, excludedIds, onToggleExcluded }: LibraryPanelProps) {
  const excluded = new Set(excludedIds)
  return (
    <div data-testid="library-panel">
      <p className="opt-note" data-testid="library-notice">
        {catalog.library.id} v{catalog.library.version} - {catalog.library.notice}
      </p>
      <p className="opt-note">
        Phase {catalog.phase_id} of {catalog.scenario_id} at revision {catalog.scenario_revision};
        eligibility computed as of {catalog.evaluated_as_of}. Applicable items:{' '}
        {catalog.eligible_intervention_ids.length} of {catalog.interventions.length}.
      </p>
      <div className="opt-scroll">
        <table className="data-table" data-testid="intervention-table">
          <thead>
            <tr>
              {onToggleExcluded ? <th scope="col">Include</th> : null}
              <th scope="col">Intervention</th>
              <th scope="col">Eligibility</th>
              <th scope="col">Declared for</th>
              <th scope="col">Operators</th>
              <th scope="col">Dependencies</th>
              <th scope="col">Cost</th>
            </tr>
          </thead>
          <tbody>
            {catalog.interventions.map((item) => {
              const isExcluded = excluded.has(item.id)
              return (
                <tr key={item.id} data-testid={`intervention-row-${item.id}`}>
                  {onToggleExcluded ? (
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Include ${item.id} in the search domain`}
                        checked={!isExcluded}
                        disabled={!item.applicable}
                        onChange={() => onToggleExcluded(item.id)}
                      />
                    </td>
                  ) : null}
                  <td>
                    <div className="mono">{item.id}</div>
                    <div>{item.name ?? ''}</div>
                    {item.description ? <div className="opt-note">{item.description}</div> : null}
                  </td>
                  <td>
                    {item.applicable ? (
                      <ToneBadge tone="pass" glyph="✓" title="All declared preconditions hold in this phase">
                        Applicable
                      </ToneBadge>
                    ) : (
                      <>
                        <ToneBadge
                          tone="neutral"
                          glyph="–"
                          title="At least one declared precondition does not hold; the engine will not emit this intervention as a candidate"
                        >
                          Not applicable
                        </ToneBadge>
                        {item.eligibility_reasons.length > 0 ? (
                          <ul className="opt-reasons">
                            {item.eligibility_reasons.map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        ) : null}
                      </>
                    )}
                    {isExcluded && item.applicable ? (
                      <div className="opt-note">Excluded from the search domain by you.</div>
                    ) : null}
                  </td>
                  <td className="data-table__mono">
                    {(item.phases ?? []).length > 0 ? (item.phases ?? []).join(', ') : 'any phase'}
                    {(item.target_element_ids ?? []).length > 0 ? (
                      <div className="opt-note">{(item.target_element_ids ?? []).join(', ')}</div>
                    ) : null}
                  </td>
                  <td className="data-table__mono">{(item.allowed_ops ?? []).join(', ')}</td>
                  <td className="data-table__mono">
                    {(item.requires_intervention_ids ?? []).length > 0 ? (
                      <div>requires: {(item.requires_intervention_ids ?? []).join(', ')}</div>
                    ) : null}
                    {(item.excludes_intervention_ids ?? []).length > 0 ? (
                      <div>excludes: {(item.excludes_intervention_ids ?? []).join(', ')}</div>
                    ) : null}
                    {((item.requires_intervention_ids ?? []).length === 0 &&
                      (item.excludes_intervention_ids ?? []).length === 0) ? (
                      <span>none declared</span>
                    ) : null}
                  </td>
                  <td>
                    {(item.costs ?? []).length === 0 ? (
                      <span>Not estimated</span>
                    ) : (
                      <ul className="opt-reasons">
                        {(item.costs ?? []).map((cost) => (
                          <li key={cost.id}>
                            {cost.label}:{' '}
                            {formatCost(cost.unit_price_nominal ?? null, cost.currency ?? null)}
                            {cost.unit ? ` / ${cost.unit}` : ''}
                            {cost.provenance ? ` (${cost.provenance})` : ''}
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {catalog.precondition_rejected.length > 0 ? (
        <p className="opt-note" data-testid="precondition-rejected">
          {catalog.precondition_rejected.length} intervention(s) have a declared precondition that
          does not hold; they are not offered as candidates for this phase.
        </p>
      ) : null}
    </div>
  )
}
