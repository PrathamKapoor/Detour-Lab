import { useEffect, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { formatHash, formatDuration, formatTimestamp } from '@/lib/format'

/**
 * Screen 7 — analysis & export.
 *
 * The manifest is fetched from the backend and never rebuilt in the browser:
 * the canonical record of a review is the server's, not a re-serialisation of
 * what happens to be on screen.
 */
export function ReportsPanel() {
  const { current, manifest, manifestError, loadManifest, api } = useWorkspace()
  const [loading, setLoading] = useState(false)
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null)

  useEffect(() => {
    if (current && !manifest && !manifestError && !loading) {
      setLoading(true)
      void loadManifest(current.run.id).finally(() => setLoading(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.run.id])

  if (!current) {
    return (
      <Panel title="Analysis & export">
        <EmptyState
          title="Nothing to export yet"
          description="Run an analysis first; its canonical manifest can then be retrieved and downloaded."
          icon="⇩"
        />
      </Panel>
    )
  }

  const downloadManifest = async () => {
    if (!manifest) return
    const payload = `${JSON.stringify(manifest, null, 2)}\n`
    const blob = new Blob([payload], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `detour-lab-manifest-${manifest.semantic_hash.replace('sha256:', '').slice(0, 12)}.json`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    setDownloadNotice(
      `Downloaded the manifest exactly as returned by GET /api/v1/runs/${current.run.id}/manifest (${payload.length} bytes).`,
    )
  }

  return (
    <div className="reports">
      <Panel
        title="Canonical manifest"
        subtitle="Authoritative machine-readable record of this run, produced by the backend"
        actions={
          <>
            <Button onClick={() => void loadManifest(current.run.id)} busy={loading} disabled={!api}>
              Refresh
            </Button>
            <Button variant="primary" onClick={() => void downloadManifest()} disabled={!manifest}>
              Download JSON
            </Button>
          </>
        }
      >
        {downloadNotice ? (
          <p className="inspector__note" role="status" data-testid="download-notice">
            {downloadNotice}
          </p>
        ) : null}

        {manifestError ? (
          <ErrorPanel
            title="Could not load the manifest"
            code={manifestError.code}
            message={manifestError.userMessage}
            action={<Button onClick={() => void loadManifest(current.run.id)}>Retry</Button>}
          />
        ) : null}

        {loading && !manifest ? <Spinner label="Fetching manifest" /> : null}

        {manifest ? (
          <>
            <StatusBadge
              meta={{
                label: 'Planning analysis — not certified',
                glyph: '⚠',
                tone: 'unknown',
                description: manifest.disclaimer,
              }}
            />
            <KeyValueList
              items={[
                { term: 'Manifest schema', value: manifest.schema_version },
                { term: 'Semantic hash', value: <span className="mono" data-testid="manifest-hash">{formatHash(manifest.semantic_hash, 28)}</span> },
                { term: 'Run id', value: <span className="mono">{manifest.runtime.run_id}</span> },
                { term: 'Run created', value: formatTimestamp(manifest.runtime.created_at) },
                { term: 'Compute time', value: formatDuration(manifest.runtime.duration_ms) },
                { term: 'Evaluation instant', value: manifest.runtime.evaluation_instant },
                { term: 'Base graph', value: <span className="mono">{manifest.inputs.base_graph_version_id}</span> },
                { term: 'Base graph hash', value: <span className="mono">{formatHash(manifest.inputs.base_graph_hash, 20)}</span> },
                { term: 'Network size', value: `${manifest.inputs.node_count} nodes · ${manifest.inputs.edge_count} edges · ${manifest.inputs.evidence_count} evidence records` },
                { term: 'Scenario', value: <span className="mono">{manifest.scenario.id} (revision {manifest.scenario.revision})</span> },
                { term: 'Phase graph', value: <span className="mono">{manifest.scenario.phase_graph_id}</span> },
                { term: 'Rulepack', value: `${manifest.ruleset.id} v${manifest.ruleset.version}` },
                { term: 'Legal applicability', value: manifest.ruleset.legal_applicability },
                { term: 'Profile', value: <span className="mono">{manifest.profile.id}</span> },
                { term: 'Unknowns', value: String(manifest.results.unknowns.length) },
                { term: 'Known failures', value: String(manifest.results.known_failures.length) },
                { term: 'Canonical size', value: `${manifest.canonical_json_bytes} bytes` },
              ]}
            />

            <h3 className="inspector__heading">Determinism</h3>
            <p className="inspector__note">
              Two equivalent analyses produce <em>different</em> run ids but the <em>same</em> semantic
              hash (<span className="mono">{formatHash(manifest.semantic_hash, 20)}</span>). The run id
              identifies one execution; the hash identifies the engineering result. Volatile metadata
              (run id, timestamps, duration) is excluded from the hash by design.
            </p>

            <h3 className="inspector__heading">Limitations carried by this record</h3>
            <ul className="inspector__list">
              {manifest.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>

            <h3 className="inspector__heading">Attribution</h3>
            <ul className="inspector__list">
              {manifest.attributions.map((attribution) => (
                <li key={attribution.name}>
                  {attribution.name} — licence: {attribution.license}
                  {attribution.url ? ` — ${attribution.url}` : ''}
                </li>
              ))}
            </ul>

            <h3 className="inspector__heading">Reviewer actions from unresolved evidence</h3>
            {manifest.results.unknowns.length === 0 ? (
              <p className="inspector__note">This run has no unresolved attributes.</p>
            ) : (
              <ul className="inspector__list">
                {manifest.results.unknowns.map((unknown) => (
                  <li key={`${unknown.element_id}-${unknown.rule_id}`}>
                    <span className="mono">{unknown.element_id}</span> · {unknown.rule_id} —{' '}
                    {unknown.explanation}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}
      </Panel>

      <Panel title="Run identity" subtitle="Distinguish execution identity from result identity" flush>
        <table className="data-table" data-testid="run-table">
          <caption>What to record in a review: the semantic hash, not the run id</caption>
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Value</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Run id (per execution)</td>
              <td className="mono" data-testid="run-id">
                {current.run.id}
              </td>
            </tr>
            <tr>
              <td>Semantic hash (per result)</td>
              <td className="mono">{current.run.semantic_hash}</td>
            </tr>
            <tr>
              <td>Input hash</td>
              <td className="mono">{current.run.input_hash}</td>
            </tr>
            <tr>
              <td>Scenario revision</td>
              <td className="numeric">{current.run.scenario_revision}</td>
            </tr>
            <tr>
              <td>Engine version</td>
              <td className="mono">{current.run.engine_version}</td>
            </tr>
          </tbody>
        </table>
      </Panel>
    </div>
  )
}