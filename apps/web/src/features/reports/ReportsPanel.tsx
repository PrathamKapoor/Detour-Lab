import { useEffect, useMemo, useState } from 'react'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { KeyValueList, StatusBadge } from '@/components/StatusBadge'
import { formatHash, formatDuration, formatTimestamp } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { formatOptionalCost } from '@/lib/presentation-meta'
import type { GeneratedReportEnvelope, ReportEnvelope } from '@/api/types'
import './reports.css'

/**
 * Reports — canonical manifest, stored review packets and real PDF export.
 *
 * The manifest and the PDF packet are both built by the backend from stored
 * runs. Nothing here recomputes an accessibility result, re-serialises a
 * manifest, or fabricates a section: the packet is generated server-side and the
 * browser downloads exactly the bytes the server produced.
 *
 * A stored packet is historical. It always names the scenario revision it
 * describes, and a report from an older revision is labelled as such rather
 * than being presented as current.
 */
export function ReportsPanel() {
  const ws = useWorkspace()
  const { current, manifest, manifestError, loadManifest, api, scenarioId, projectId } = ws
  const [loading, setLoading] = useState(false)
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null)

  /* --- packet selection ------------------------------------------------- */
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([])
  const [selectedExperimentIds, setSelectedExperimentIds] = useState<string[]>([])
  const [includeEvidenceQueue, setIncludeEvidenceQueue] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [generated, setGenerated] = useState<GeneratedReportEnvelope | null>(null)
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)

  const runs = useResource(
    (signal) => api.listScenarioRuns(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )
  const experiments = useResource(
    (signal) => api.listFailureLabExperiments(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )
  const storedReports = useResource(
    (signal) => api.listReports(scenarioId as string, signal),
    [api, scenarioId],
    { enabled: Boolean(scenarioId) },
  )
  const reportDetail = useResource(
    (signal) => api.getReport(selectedReportId as string, signal),
    [api, selectedReportId],
    { enabled: Boolean(selectedReportId) },
  )

  // The run produced by the current analysis is preselected; nothing else is.
  // Derived during render rather than in an effect, so the selection is correct
  // on the first paint instead of arriving a frame later.
  const effectiveRunIds = selectedRunIds.length > 0 ? selectedRunIds : current ? [current.run.id] : []

  useEffect(() => {
    if (current && !manifest && !manifestError && !loading) {
      setLoading(true)
      void loadManifest(current.run.id).finally(() => setLoading(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.run.id])

  const selectedRuns = runs.data?.runs ?? []
  const selectedExperiments = experiments.data?.experiments ?? []

  const selectedDetail: ReportEnvelope | null = reportDetail.data ?? null

  const downloadUrls = useMemo(
    () => (generated ? api.reportDownloadUrls(generated.report.report_id) : null),
    [api, generated],
  )

  const toggleRun = (runId: string) =>
    setSelectedRunIds((ids) => (ids.includes(runId) ? ids.filter((id) => id !== runId) : [...ids, runId]))

  const toggleExperiment = (id: string) =>
    setSelectedExperimentIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))

  async function generate() {
    if (!scenarioId) return
    setGenerating(true)
    setGenerateError(null)
    try {
      const response = await api.createReport(scenarioId, {
        run_ids: effectiveRunIds,
        experiment_ids: selectedExperimentIds,
        include_evidence_queue: includeEvidenceQueue,
      })
      setGenerated(response)
      setSelectedReportId(response.report.report_id)
      setDownloadNotice(null)
      storedReports.reload()
    } catch (error) {
      setGenerateError(error instanceof Error ? error.message : String(error))
    } finally {
      setGenerating(false)
    }
  }

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
    const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `detour-lab-manifest-${manifest.semantic_hash.replace('sha256:', '').slice(0, 12)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    setDownloadNotice(
      `Canonical manifest downloaded verbatim from the server: ${blob.size} bytes. It was not re-serialised in the browser.`,
    )
  }

  return (
    <div className="reports">
      <Panel title="Review packet" subtitle="Select what the packet must describe, then generate it on the server">
        <fieldset className="reports__selection">
          <legend className="reports__legend">Stored analysis runs (at least one is required)</legend>
          {runs.loading && !runs.data ? <Spinner label="Loading stored runs" /> : null}
          {selectedRuns.map((run) => (
            <label key={run.id} className="reports__option">
              <input
                type="checkbox"
                checked={effectiveRunIds.includes(run.id)}
                onChange={() => toggleRun(run.id)}
                data-testid={`report-run-${run.id}`}
              />
              <span>
                <span className="mono">{run.id}</span>
                <span className="reports__option-detail">
                  phase {run.phase_id} · profile {run.profile_id} · revision {run.scenario_revision} ·
                  semantic {run.semantic_hash.slice(0, 16)}…
                </span>
              </span>
            </label>
          ))}
        </fieldset>

        <fieldset className="reports__selection">
          <legend className="reports__legend">Failure Lab experiments (optional)</legend>
          {selectedExperiments.length === 0 ? (
            <p className="reports__hint">
              No stored experiments for this scenario. Run some in the Failure Lab to include adversarial
              results in the packet; otherwise section 9 is marked unavailable rather than empty.
            </p>
          ) : (
            selectedExperiments.map((entry) => (
              <label key={entry.experiment_id} className="reports__option">
                <input
                  type="checkbox"
                  checked={selectedExperimentIds.includes(entry.experiment_id)}
                  onChange={() => toggleExperiment(entry.experiment_id)}
                  data-testid={`report-experiment-${entry.experiment_id}`}
                />
                <span>
                  <span className="mono">{entry.experiment_id}</span>
                  <span className="reports__option-detail">
                    {entry.suite_id ?? 'ad-hoc'} · {entry.status} · revision {entry.scenario_revision}
                  </span>
                </span>
              </label>
            ))
          )}
        </fieldset>

        <label className="reports__toggle">
          <input
            type="checkbox"
            checked={includeEvidenceQueue}
            onChange={(event) => setIncludeEvidenceQueue(event.target.checked)}
            data-testid="report-include-queue"
          />
          <span>Include the derived evidence verification queue</span>
        </label>

        <div className="reports__actions">
          <Button
            variant="primary"
            onClick={() => void generate()}
            disabled={generating || effectiveRunIds.length === 0}
            data-testid="generate-report"
          >
            {generating ? 'Generating the packet on the server…' : 'Generate PDF packet'}
          </Button>
          <span className="reports__hint">
            The packet is built from the stored runs above, never from what happens to be on screen.
          </span>
        </div>

        {generateError ? (
          <ErrorPanel
            title="The packet could not be generated"
            message={generateError}
            data-testid="report-generate-error"
            action={
              <Button variant="secondary" onClick={() => void generate()} data-testid="report-generate-retry">
                Retry
              </Button>
            }
          />
        ) : null}

        {generated ? (
          <div className="reports__generated" data-testid="generated-report">
            <KeyValueList
              items={[
                { term: 'Report id', value: generated.report.report_id },
                { term: 'Semantic hash', value: generated.report.semantic_hash, wide: true },
                { term: 'Schema', value: generated.report.schema_version },
                { term: 'Generator', value: generated.report.generator_version },
                { term: 'PDF pages', value: String(generated.report.page_count) },
                { term: 'PDF size', value: `${generated.report.pdf_bytes.toLocaleString()} bytes` },
                { term: 'PDF sha256', value: generated.report.pdf_sha256, wide: true },
              ]}
            />
            <div className="reports__actions">
              <a
                className="btn btn--primary"
                href={downloadUrls?.pdf}
                download
                data-testid="download-pdf"
              >
                Download PDF
              </a>
              <a
                className="btn btn--secondary"
                href={downloadUrls?.manifest}
                download
                data-testid="download-report-manifest"
              >
                Download canonical JSON
              </a>
            </div>
            <p className="reports__disclaimer" data-testid="report-disclaimer">
              {generated.report.disclaimer}
            </p>
            <h3 className="reports__subheading">Sections the packet will contain</h3>
            <ul className="reports__sections" data-testid="report-sections">
              {Object.entries(generated.report.section_availability).map(([key, entry]) => (
                <li key={key} data-testid={`report-section-${key}`}>
                  <StatusBadge
                    meta={
                      entry.status === 'available'
                        ? { label: 'available', glyph: '✓', tone: 'pass', description: 'Populated from stored runs.' }
                        : {
                            label: entry.status.replace(/_/g, ' '),
                            glyph: '○',
                            tone: 'neutral',
                            description: entry.reason || 'Not selected for this packet.',
                          }
                    }
                    detail={key}
                  />
                  {entry.status !== 'available' ? (
                    <span className="reports__section-reason">{entry.reason}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Panel>

      <Panel title="Stored review packets" subtitle="Each packet stays bound to the revision it described">
        {storedReports.loading && !storedReports.data ? (
          <Spinner label="Loading stored packets" />
        ) : storedReports.error ? (
          <ErrorPanel
            title="Stored packets could not be loaded"
            message={storedReports.error.userMessage}
            code={storedReports.error.code}
            action={
              <Button variant="secondary" onClick={storedReports.reload}>
                Retry
              </Button>
            }
          />
        ) : (storedReports.data?.report_count ?? 0) === 0 ? (
          <EmptyState
            title="No packets generated yet"
            description="Generate one above; it is stored and can be reopened or regenerated later."
          />
        ) : (
          <>
            <div className="table-scroll">
      <table className="data-table" data-testid="stored-report-table">
              <thead>
                <tr>
                  <th scope="col">Report</th>
                  <th scope="col">Revision</th>
                  <th scope="col">Current?</th>
                  <th scope="col">Pages</th>
                  <th scope="col">Semantic hash</th>
                  <th scope="col">Open</th>
                </tr>
              </thead>
              <tbody>
                {(storedReports.data?.reports ?? []).map((entry) => (
                  <tr key={entry.report_id} data-testid={`stored-report-${entry.report_id}`}>
                    <th scope="row" className="mono">
                      {entry.report_id}
                    </th>
                    <td className="numeric">{entry.scenario_revision}</td>
                    <td>
                      {entry.describes_current_revision ? (
                        'current'
                      ) : (
                        <span className="reports__historical">
                          historical — describes revision {entry.scenario_revision}
                        </span>
                      )}
                    </td>
                    <td className="numeric">{entry.pdf_page_count}</td>
                    <td className="mono">{entry.semantic_hash.slice(0, 20)}…</td>
                    <td>
                      <Button
                        variant="ghost"
                        data-testid={`open-report-${entry.report_id}`}
                        onClick={() => setSelectedReportId(entry.report_id)}
                      >
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
      </div>
            <p className="reports__hint">{storedReports.data?.historical_note}</p>
          </>
        )}
      </Panel>

      {selectedDetail ? (
        <Panel
          title={`Packet ${selectedDetail.report_id}`}
          subtitle={`Scenario revision ${selectedDetail.scenario_revision}`}
        >
          <KeyValueList
            items={[
              { term: 'Scenario', value: selectedDetail.scenario_id },
              { term: 'Described revision', value: String(selectedDetail.scenario_revision) },
              { term: 'Current revision', value: String(selectedDetail.current_scenario_revision) },
              {
                term: 'Still current',
                value: selectedDetail.describes_current_revision ? 'yes' : 'no — this is a historical packet',
              },
              { term: 'Semantic hash', value: selectedDetail.semantic_hash, wide: true },
              { term: 'PDF sha256', value: selectedDetail.pdf_sha256, wide: true },
              { term: 'PDF pages', value: String(selectedDetail.pdf_page_count) },
              { term: 'Created', value: formatTimestamp(selectedDetail.created_at) },
              { term: 'Runs included', value: selectedDetail.selected_run_ids.join(', ') || 'none' },
              {
                term: 'Experiments included',
                value: selectedDetail.selected_experiment_ids.join(', ') || 'none',
              },
            ]}
          />
          <div className="reports__actions">
            <a
              className="btn btn--primary"
              href={api.reportDownloadUrls(selectedDetail.report_id).pdf}
              download
              data-testid="download-stored-pdf"
            >
              Download this PDF
            </a>
            <a
              className="btn btn--secondary"
              href={api.reportDownloadUrls(selectedDetail.report_id).manifest}
              download
              data-testid="download-stored-manifest"
            >
              Download its JSON
            </a>
          </div>

          <h3 className="reports__subheading">Alternative-plan analysis in this packet</h3>
          {selectedDetail.payload.alternative_plans.length === 0 ? (
            <p className="reports__hint" data-testid="report-no-alternatives">
              No optimisation search was selected, so no alternative plan and no cost appears anywhere in
              this packet.
            </p>
          ) : (
            <div className="table-scroll">
      <table className="data-table" data-testid="report-alternatives">
              <thead>
                <tr>
                  <th scope="col">Search</th>
                  <th scope="col">Solver status</th>
                  <th scope="col">Exhaustive</th>
                  <th scope="col">Selected candidates and declared costs</th>
                </tr>
              </thead>
              <tbody>
                {selectedDetail.payload.alternative_plans.map((plan) => (
                  <tr key={plan.search_id} data-testid={`report-plan-${plan.search_id}`}>
                    <th scope="row" className="mono">
                      {plan.search_id}
                    </th>
                    <td>{plan.solver_status}</td>
                    <td>{plan.exhaustive ? 'yes — complete over the enumerated domain' : 'no'}</td>
                    <td>
                      {plan.selected_candidates.length === 0 ? (
                        'none included'
                      ) : (
                        plan.selected_candidates.map((candidate) => (
                          <span
                            key={candidate.proposal_id}
                            className="reports__option-detail"
                            data-testid={`report-candidate-${candidate.proposal_id}`}
                          >
                            {candidate.classification} · nominal{' '}
                            {formatOptionalCost(candidate.cost_nominal, candidate.cost_currency)} ·
                            maximum {formatOptionalCost(candidate.cost_maximum, candidate.cost_currency)}
                            {candidate.cost_unknown ? ' (declared cost incomplete)' : ''}
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
      </div>
          )}

          <h3 className="reports__subheading">Failure Lab experiments in this packet</h3>
          {selectedDetail.payload.experiments.length === 0 ? (
            <p className="reports__hint" data-testid="report-no-experiments">
              No Failure Lab experiment was selected. No adversarial result appears in this packet.
            </p>
          ) : (
            <ul className="reports__sections" data-testid="report-experiments">
              {selectedDetail.payload.experiments.map((experiment) => (
                <li key={experiment.experiment_id} data-testid={`report-experiment-${experiment.experiment_id}`}>
                  <span className="mono">{experiment.experiment_id}</span> — {experiment.status}
                  <span className="reports__section-reason">
                    {experiment.fault_kinds.join(', ')} → {experiment.observations.join(', ') || 'no modelled conclusion'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ) : null}

      <Panel title="Canonical run manifest" subtitle="The machine-readable record of the current analysis">
        {manifestError ? (
          <ErrorPanel
            title="The manifest could not be retrieved"
            message={manifestError.userMessage}
            code={manifestError.code}
            action={
              <Button variant="secondary" onClick={() => void loadManifest(current.run.id)}>
                Retry
              </Button>
            }
          />
        ) : !manifest ? (
          <Spinner label="Retrieving the canonical manifest" />
        ) : (
          <>
            <div className="reports__actions">
              <Button variant="primary" onClick={() => void downloadManifest()} data-testid="download-manifest">
                Download JSON manifest
              </Button>
            </div>
            {downloadNotice ? (
              <p className="reports__notice" role="status" data-testid="download-notice">
                {downloadNotice}
              </p>
            ) : null}
            <KeyValueList
              items={[
                { term: 'Schema version', value: manifest.schema_version },
                { term: 'Engine version', value: manifest.engine_version },
                {
                  term: 'Semantic hash',
                  value: (
                    <span className="mono" data-testid="manifest-hash">
                      {manifest.semantic_hash}
                    </span>
                  ),
                  wide: true,
                },
                {
                  term: 'Run id',
                  value: (
                    <span className="mono" data-testid="run-id">
                      {manifest.runtime?.run_id ?? ''}
                    </span>
                  ),
                },
                { term: 'Created', value: formatTimestamp(manifest.runtime?.created_at ?? '') },
                { term: 'Duration', value: formatDuration(manifest.runtime?.duration_ms ?? 0) },
                { term: 'Evaluation instant', value: manifest.runtime?.evaluation_instant ?? '' },
                { term: 'Base graph', value: manifest.inputs?.base_graph_version_id ?? '' },
                { term: 'Graph hash', value: formatHash(manifest.inputs?.base_graph_hash ?? ''), wide: true },
                { term: 'Nodes / edges', value: `${manifest.inputs?.node_count} / ${manifest.inputs?.edge_count}` },
                { term: 'Evidence records', value: String(manifest.inputs?.evidence_count ?? 0) },
                { term: 'Scenario', value: manifest.scenario?.id ?? '' },
                { term: 'Revision', value: String(manifest.scenario?.revision ?? 0) },
                { term: 'Phase graph', value: manifest.scenario?.phase_graph_id ?? '' },
                { term: 'Rulepack', value: `${manifest.ruleset?.id} ${manifest.ruleset?.version}` },
                {
                  term: 'Legal applicability',
                  value: manifest.ruleset?.legal_applicability ?? '',
                },
                { term: 'Unknowns', value: String(manifest.results?.unknowns?.length ?? 0) },
                { term: 'Known failures', value: String(manifest.results?.known_failures?.length ?? 0) },
                { term: 'Canonical JSON bytes', value: String(manifest.canonical_json_bytes ?? 0) },
              ]}
            />

            <h3 className="reports__subheading">Determinism</h3>
            <p className="reports__hint">
              The manifest carries a semantic hash computed over its content with the volatile runtime
              block excluded. Two runs over identical inputs share that hash while carrying different run
              identifiers.
            </p>

            <h3 className="reports__subheading">Limitations carried by the run</h3>
            <ul className="reports__sections" data-testid="manifest-limitations">
              {(manifest.limitations ?? []).map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>

            <h3 className="reports__subheading">Reviewer actions from unresolved evidence</h3>
            <ul className="reports__sections" data-testid="manifest-unknowns">
              {(manifest.results?.unknowns ?? []).map((unknown) => (
                <li key={`${unknown.element_id}-${unknown.rule_id}`}>
                  <span className="mono">{unknown.element_id}</span> — {unknown.reason_code}
                  <span className="reports__section-reason">{unknown.explanation}</span>
                </li>
              ))}
            </ul>

            <h3 className="reports__subheading">Attribution</h3>
            <ul className="reports__sections" data-testid="manifest-attributions">
              {(manifest.attributions ?? []).map((attribution) => (
                <li key={attribution.name}>
                  {attribution.name} — {attribution.license}
                  {attribution.attribution ? <span className="reports__section-reason">{attribution.attribution}</span> : null}
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <p className="visually-hidden">
        {generated
          ? `Report ${generated.report.report_id} generated with ${generated.report.page_count} pages.`
          : 'No review packet generated in this session.'}
        {projectId ? ` Project ${projectId}.` : ''}
      </p>
    </div>
  )
}