import { useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, Panel } from '@/components/Button'
import { StatusBadge } from '@/components/StatusBadge'
import { formatObservation, formatTimestamp } from '@/lib/format'
import { evidenceProblemMeta, verdictMeta } from '@/lib/status'

/**
 * Screen 6 — evidence & findings centre.
 *
 * Lists every unresolved attribute in the current run, grouped by the specific
 * evidence condition the engine reported. The five conditions are never merged:
 * "conflicting" and "unsupported unit" mean different things and lead to
 * different next steps.
 */
export function EvidenceCentre() {
  const { current, graph, scenario, setView, selectEdge, selectNode } = useWorkspace()
  const [selected, setSelected] = useState<string | null>(null)

  const unresolved = useMemo(() => {
    if (!current) return []
    const byKey = new Map<string, { elementId: string; ruleId: string; reason: string; explanation: string; evidenceIds: string[] }>()
    for (const verdict of current.result.verdicts) {
      if (verdict.state !== 'UNKNOWN') continue
      for (const attribute of verdict.inputs) {
        if (attribute.known) continue
        const key = `${verdict.element_id}|${attribute.field}`
        if (byKey.has(key)) continue
        byKey.set(key, {
          elementId: verdict.element_id,
          ruleId: verdict.rule_id,
          reason: attribute.reason_code ?? verdict.reason_code ?? 'UNRESOLVED',
          explanation: attribute.explanation ?? verdict.explanation,
          evidenceIds: attribute.evidence_ids ?? [],
        })
      }
    }
    return Array.from(byKey.values()).sort((a, b) => a.elementId.localeCompare(b.elementId))
  }, [current])

  const grouped = useMemo(() => {
    const groups = new Map<string, typeof unresolved>()
    for (const item of unresolved) {
      const list = groups.get(item.reason) ?? []
      list.push(item)
      groups.set(item.reason, list)
    }
    return Array.from(groups.entries())
  }, [unresolved])

  const selectedItem = unresolved.find((item) => `${item.elementId}|${item.ruleId}` === selected) ?? null

  if (!current) {
    return (
      <Panel title="Evidence centre">
        <EmptyState
          title="No analysis to inspect"
          description="Run an analysis; unresolved attributes will be listed here with their exact cause."
          icon="◌"
          action={
            <Button variant="primary" onClick={() => setView('analysis')}>
              Go to analysis
            </Button>
          }
        />
      </Panel>
    )
  }

  return (
    <div className="evidence">
      <Panel
        title="Unresolved attributes"
        subtitle={`${unresolved.length} attribute(s) keep their rules Unknown in this run`}
        flush
      >
        {grouped.length === 0 ? (
          <div className="panel__body">
            <p className="inspector__note">
              Every evaluated attribute resolved. That does not mean the plan is safe — it means the
              modeled checks had adequate evidence for this phase and profile.
            </p>
          </div>
        ) : (
          grouped.map(([reason, items]) => {
            const meta = evidenceProblemMeta(reason)
            return (
              <div key={reason} className="evidence__group">
                <div className="evidence__group-head">
                  <StatusBadge meta={meta} />
                  <span className="inspector__note">{meta.action}</span>
                </div>
                <table className="data-table">
                  <caption className="visually-hidden">
                    Attributes unresolved because of {meta.label}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Element</th>
                      <th scope="col">Rule</th>
                      <th scope="col">Evidence</th>
                      <th scope="col">What the engine said</th>
                      <th scope="col">Inspect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr key={`${item.elementId}-${item.ruleId}`}>
                        <td className="data-table__mono">{item.elementId}</td>
                        <td className="data-table__mono">{item.ruleId}</td>
                        <td className="data-table__mono">
                          {item.evidenceIds.length > 0 ? item.evidenceIds.join(', ') : 'none'}
                        </td>
                        <td>{item.explanation}</td>
                        <td>
                          <Button
                            onClick={() => {
                              setSelected(`${item.elementId}|${item.ruleId}`)
                              if (item.elementId.startsWith('TMP::') || graph?.edges.some((edge) => edge.id === item.elementId)) {
                                selectEdge(item.elementId)
                              } else {
                                selectNode(item.elementId)
                              }
                            }}
                            data-testid={`inspect-${item.elementId}`}
                          >
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          })
        )}
      </Panel>

      <Panel title="Evidence register" subtitle={`${graph?.evidence.length ?? 0} records on the base graph`} flush>
        {!graph ? (
          <div className="panel__body">
            <p className="inspector__note">No graph loaded.</p>
          </div>
        ) : (
          <table className="data-table">
            <caption>
              Every observation, with its source. Synthetic records are flagged; none are field-verified.
            </caption>
            <thead>
              <tr>
                <th scope="col">Record</th>
                <th scope="col">Element</th>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
                <th scope="col">Source</th>
                <th scope="col">Observed</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {graph.evidence.map((record) => (
                <tr key={record.id} data-testid={`evidence-${record.id}`}>
                  <td className="data-table__mono">{record.id}</td>
                  <td className="data-table__mono">{record.element_id}</td>
                  <td className="data-table__mono">{record.field}</td>
                  <td className="numeric">{formatObservation(record.value, record.unit)}</td>
                  <td>
                    {record.source}
                    {record.synthetic ? (
                      <StatusBadge
                        meta={{
                          label: 'Synthetic',
                          glyph: '⚑',
                          tone: 'info',
                          description: 'Invented for demonstration. Not a field measurement.',
                        }}
                        size="sm"
                      />
                    ) : null}
                  </td>
                  <td className="numeric">{formatTimestamp(record.observed_at)}</td>
                  <td>
                    {record.invalidated ? (
                      <StatusBadge
                        meta={{
                          label: 'Invalidated',
                          glyph: '⊗',
                          tone: 'unknown',
                          description: 'Explicitly invalidated and not eligible for resolution.',
                        }}
                        size="sm"
                      />
                    ) : (
                      <StatusBadge
                        meta={{
                          label: record.verification_status ?? 'unverified',
                          glyph: record.verification_status === 'verified' ? '✓' : '◌',
                          tone: record.verification_status === 'verified' ? 'pass' : 'unknown',
                          description: 'Verification status recorded with the observation.',
                        }}
                        size="sm"
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {selectedItem ? (
        <Panel title={`Selected: ${selectedItem.elementId}`} subtitle={selectedItem.ruleId}>
          <p>{selectedItem.explanation}</p>
          <StatusBadge meta={verdictMeta('UNKNOWN')} />
        </Panel>
      ) : null}

      {scenario ? (
        <p className="inspector__note">
          Phases in this scenario: {scenario.phases.map((phase) => phase.id).join(', ')}. Phase order is
          logical; no construction calendar is asserted by the model.
        </p>
      ) : null}
    </div>
  )
}