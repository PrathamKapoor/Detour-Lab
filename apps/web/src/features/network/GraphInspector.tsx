import { useMemo } from 'react'
import type { GraphEdge, Node } from '@/api/types'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import type { EvidenceRecord, Finding, RuleVerdict } from '@contracts/types'
import type { NormalisedAnalysisResult } from '@/api/normalize'
import { formatHash, formatObservation, formatTimestamp } from '@/lib/format'
import { evidenceProblemMeta, verdictMeta } from '@/lib/status'

interface GraphInspectorProps {
  edge?: GraphEdge | null
  node?: Node | null
  evidence: readonly EvidenceRecord[]
  verdicts: readonly RuleVerdict[]
  findings: readonly Finding[]
  edgeState: VerdictStateSummary | null
  isClosed: boolean
  isTemporary: boolean
  result: NormalisedAnalysisResult | null
  originLabel: (nodeId: string) => string
}

export interface VerdictStateSummary {
  state: 'PASS' | 'FAIL' | 'UNKNOWN' | 'NOT_APPLICABLE'
  reasonCodes: string[]
  relevantChecks: number
  confirmedEligible: boolean
  possiblyEligible: boolean
}

/**
 * Attribute + evidence inspector for the selected edge or node.
 *
 * It shows only what the backend actually returned. An attribute with no
 * evidence is shown as “Unknown” with the reason code, never as 0 or a dash.
 */
export function GraphInspector({
  edge,
  node,
  evidence,
  verdicts,
  findings,
  edgeState,
  isClosed,
  isTemporary,
  result,
  originLabel,
}: GraphInspectorProps) {
  const elementId = edge?.id ?? node?.id ?? null
  const elementEvidence = useMemo(
    () => evidence.filter((record) => record.element_id === elementId),
    [evidence, elementId],
  )
  const elementVerdicts = useMemo(
    () => verdicts.filter((verdict) => verdict.element_id === elementId),
    [verdicts, elementId],
  )
  const elementFindings = useMemo(
    () => findings.filter((finding) => finding.element_id === elementId),
    [findings, elementId],
  )

  if (!elementId) {
    return (
      <div className="inspector">
        <p className="inspector__note">
          Select an edge or node — on the canvas or in the table — to inspect its attributes,
          evidence and modeled results.
        </p>
      </div>
    )
  }

  const resolutionByField = new Map<string, (typeof elementVerdicts)[number]>()
  for (const verdict of elementVerdicts) {
    for (const attribute of verdict.inputs ?? []) {
      if (!attribute.known) {
        const existing = resolutionByField.get(attribute.field)
        if (!existing) resolutionByField.set(attribute.field, verdict)
      }
    }
  }

  return (
    <div className="inspector" data-testid="graph-inspector">
      {edge ? (
        <div className="inspector__section" data-testid={`inspect-${edge.id}`}>
          <h3 className="inspector__heading">Edge {edge.id}</h3>
          <KeyValueList
            items={[
              { term: 'Direction', value: `${edge.u} → ${edge.v}`, wide: true },
              { term: 'Edge type', value: edge.edge_type ?? '—' },
              { term: 'Length', value: `${edge.length_m.toFixed(3)} m` },
              { term: 'Provenance', value: edge.provenance_class ?? '—' },
              ...(isTemporary ? [{ term: 'Temporary', value: 'Modelled temporary connection' }] : []),
              ...(isClosed
                ? [{ term: 'Phase status', value: <StatusBadge meta={{ label: 'Closed for construction', glyph: '╳', tone: 'fail' as const, description: 'Closed in this phase; never routed.' }} /> }]
                : []),
              { term: 'Name', value: edge.name ?? '—', wide: true },
            ]}
          />
        </div>
      ) : null}

      {node ? (
        <div className="inspector__section" data-testid={`inspect-${node.id}`}>
          <h3 className="inspector__heading">Node {node.id}</h3>
          <KeyValueList
            items={[
              { term: 'Node type', value: node.node_type ?? 'node' },
              { term: 'Planar position', value: `${node.x.toFixed(2)}, ${node.y.toFixed(2)} (metres)` },
              { term: 'Origin/destination', value: originLabel(node.id) },
              { term: 'Provenance', value: node.provenance_class ?? '—' },
              { term: 'Name', value: node.name ?? '—', wide: true },
            ]}
          />
        </div>
      ) : null}

      <div className="inspector__section">
        <h3 className="inspector__heading">Modeled state</h3>
        {edgeState ? (
          <>
            <StatusBadge meta={verdictMeta(edgeState.state)} />
            <KeyValueList
              items={[
                { term: 'Applicable checks', value: String(edgeState.relevantChecks) },
                {
                  term: 'Confirmed eligible',
                  value: edgeState.confirmedEligible ? 'Yes' : 'No — cannot be part of a confirmed route',
                },
                {
                  term: 'Possible eligible',
                  value: edgeState.possiblyEligible
                    ? 'Yes — usable only if unknown conditions resolve'
                    : 'No',
                },
                { term: 'Reason codes', value: edgeState.reasonCodes.length ? edgeState.reasonCodes.join(', ') : '—', wide: true },
              ]}
            />
          </>
        ) : (
          <p className="inspector__note">
            No analysis has been run for this element in the current phase and profile. Run an
            analysis to see modeled results.
          </p>
        )}
      </div>

      <div className="inspector__section">
        <h3 className="inspector__heading">Evidence ({elementEvidence.length})</h3>
        {elementEvidence.length === 0 ? (
          <p className="inspector__note">
            No observation exists for this element. Missing evidence is never treated as a pass — any
            rule that needs it returns Unknown.
          </p>
        ) : (
          elementEvidence.map((record) => {
            const unresolvedVerdict = resolutionByField.get(record.field)
            return (
              <div key={record.id} className="evidence-card">
                <div className="evidence-card__head">
                  <span className="evidence-card__field">{record.field}</span>
                  <span className="evidence-card__value">
                    {formatObservation(record.value, record.unit)}
                  </span>
                </div>
                {unresolvedVerdict ? (
                  <div>
                    <StatusBadge
                      meta={evidenceProblemMeta(unresolvedVerdict.reason_code)}
                      size="sm"
                      showLabel
                    />
                    <p className="evidence-card__meta">{unresolvedVerdict.explanation}</p>
                  </div>
                ) : null}
                <dl className="evidence-card__meta">
                  <div>
                    <dt className="visually-hidden">Source</dt>
                    <dd>
                      Source: {record.source} · method: {record.method} · observed:{' '}
                      {formatTimestamp(record.observed_at)} · verification:{' '}
                      {record.verification_status ?? 'unverified'}
                      {record.synthetic ? ' · SYNTHETIC' : ''}
                    </dd>
                  </div>
                </dl>
                {record.note ? <p className="evidence-card__note">{record.note}</p> : null}
              </div>
            )
          })
        )}
      </div>

      {elementVerdicts.length > 0 ? (
        <div className="inspector__section">
          <h3 className="inspector__heading">Rule results ({elementVerdicts.length})</h3>
          {elementVerdicts.map((verdict) => (
            <details key={`${verdict.rule_id}-${verdict.scope}`} className="inspector__rule">
              <summary>
                <StatusBadge meta={verdictMeta(verdict.state)} size="sm" />
                <span className="mono inspector__rule-id">{verdict.rule_id}</span>
                <span className="inspector__rule-version">v{verdict.rule_version}</span>
              </summary>
              <p className="inspector__note">{verdict.explanation}</p>
              <p className="inspector__note">
                Reason code: <code>{verdict.reason_code}</code> · basis: {verdict.basis_label}
              </p>
            </details>
          ))}
        </div>
      ) : null}

      {elementFindings.length > 0 ? (
        <div className="inspector__section">
          <h3 className="inspector__heading">Findings ({elementFindings.length})</h3>
          {elementFindings.map((finding) => (
            <div key={finding.id} className="evidence-card">
              <div className="evidence-card__head">
                <StatusBadge meta={verdictMeta(finding.state)} size="sm" />
                <span className="evidence-card__field">{finding.severity}</span>
              </div>
              <p className="evidence-card__meta">{finding.explanation}</p>
              {finding.remedy_hint ? (
                <p className="evidence-card__note">Next step: {finding.remedy_hint}</p>
              ) : null}
              {(finding.evidence_ids ?? []).length > 0 ? (
                <p className="evidence-card__note">Evidence: {(finding.evidence_ids ?? []).join(', ')}</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {result ? (
        <div className="inspector__section">
          <h3 className="inspector__heading">Run context</h3>
          <KeyValueList
            items={[
              { term: 'Phase graph', value: result.phase_graph_id },
              { term: 'Phase hash', value: formatHash(result.phase_graph_hash) },
              { term: 'Rulepack', value: `${result.rulepack_id} v${result.rulepack_version}` },
              { term: 'Profile', value: result.profile_id },
              { term: 'Scenario', value: result.scenario_id },
            ]}
          />
        </div>
      ) : null}
    </div>
  )
}