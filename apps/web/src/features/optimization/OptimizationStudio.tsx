import { useMemo, useState } from 'react'
import { ApiError } from '@/api/client'
import { useWorkspace } from '@/app/workspace'
import { Button, EmptyState, ErrorPanel, Panel, Spinner } from '@/components/Button'
import { KeyValueList, ToneBadge } from '@/components/StatusBadge'
import { useResource } from '@/lib/useResource'
import { formatDuration, formatHash, formatTimestamp } from '@/lib/format'
import type { PromotionResult, SearchConfig, SearchOutcome } from '@/api/types'
import { CandidateDetail } from './CandidateDetail'
import { CandidateTable } from './CandidateTable'
import { LibraryPanel } from './LibraryPanel'
import { solverStatusLabel, solverStatusTone } from './presentation'
import './optimization.css'

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error))
}

function describeEntry(entry: Record<string, unknown>): string {
  return Object.entries(entry)
    .map(([key, value]) =>
      `${key}=${Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value)}`,
    )
    .join(' · ')
}

/**
 * Fix This Plan - Gate 5 optimisation studio (panels A-G).
 *
 * The browser orchestrates requests and renders results; every candidate,
 * verdict, delta, cost and promotion verification in this view was computed
 * and persisted by the backend engine. Search limits and honesty notes are
 * always visible, and a truncated search is never presented as optimal.
 */
export function OptimizationStudio() {
  const ws = useWorkspace()
  const { api, scenarioId } = ws
  const phaseId = ws.selectedPhaseId ?? ws.phaseId

  const catalog = useResource(
    (signal) => api.listInterventions(scenarioId as string, phaseId, signal),
    [scenarioId, phaseId],
    { enabled: Boolean(scenarioId) },
  )
  const history = useResource(
    (signal) => api.listOptimizationSearches(scenarioId as string, signal),
    [scenarioId],
    { enabled: Boolean(scenarioId) },
  )

  const [maxInterventions, setMaxInterventions] = useState(2)
  const [maxCandidates, setMaxCandidates] = useState(60)
  const [maxDurationMs, setMaxDurationMs] = useState(120_000)
  const [budgetEnabled, setBudgetEnabled] = useState(false)
  const [budgetAmount, setBudgetAmount] = useState('0')
  const [budgetCurrency, setBudgetCurrency] = useState('INR')
  const [budgetBasis, setBudgetBasis] = useState<'nominal' | 'conservative_max'>('nominal')
  const [monetary, setMonetary] = useState(false)
  const [excludedIds, setExcludedIds] = useState<string[]>([])
  const [outcome, setOutcome] = useState<SearchOutcome | null>(null)
  const [outcomeMode, setOutcomeMode] = useState<'live' | 'stored'>('live')
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const [replayingId, setReplayingId] = useState<string | null>(null)
  const [searchError, setSearchError] = useState<ApiError | null>(null)

  const names = useMemo(() => {
    const map: Record<string, string> = {}
    for (const item of catalog.data?.interventions ?? []) {
      if (item.name) map[item.id] = item.name
    }
    return map
  }, [catalog.data])

  if (!scenarioId) {
    return (
      <EmptyState
        title="No scenario selected"
        description="Choose a scenario, then Fix This Plan will search the bundled intervention library against its current revision and phase."
      />
    )
  }

  const currentOutcome =
    outcome && outcome.scenario_id === scenarioId && outcome.phase_id === phaseId ? outcome : null
  const staleRevision =
    currentOutcome && ws.scenarioSummary && currentOutcome.scenario_revision !== ws.scenarioSummary.revision
      ? ws.scenarioSummary.revision
      : null

  const selectedCandidate =
    currentOutcome?.candidates.find(
      (candidate) => candidate.proposal.proposal_id === selectedProposalId,
    ) ??
    currentOutcome?.candidates[0] ??
    null

  function toggleExcluded(interventionId: string) {
    setExcludedIds((previous) =>
      previous.includes(interventionId)
        ? previous.filter((id) => id !== interventionId)
        : [...previous, interventionId].sort(),
    )
  }

  async function runSearch() {
    setSearching(true)
    setSearchError(null)
    try {
      const config: SearchConfig = {
        max_interventions: maxInterventions,
        max_candidates: maxCandidates,
        max_duration_ms: maxDurationMs,
        budget: budgetEnabled
          ? { amount: Number(budgetAmount), currency: budgetCurrency.trim() || 'INR', basis: budgetBasis }
          : null,
        monetary_objective: monetary ? 'nominal' : 'off',
      }
      if (excludedIds.length > 0) {
        config.excluded_intervention_ids = [...excludedIds]
      }
      const body = await api.startOptimizationSearch(scenarioId as string, {
        phase_id: phaseId,
        ...(ws.evaluationInstant ? { evaluation_instant: ws.evaluationInstant } : {}),
        config,
      })
      setOutcome(body)
      setOutcomeMode('live')
      setSelectedProposalId(
        body.status.best_proposal_id ?? body.candidates[0]?.proposal.proposal_id ?? null,
      )
      history.reload()
    } catch (error) {
      setSearchError(asApiError(error))
    } finally {
      setSearching(false)
    }
  }

  async function replay(searchId: string) {
    setReplayingId(searchId)
    setSearchError(null)
    try {
      const body = await api.getOptimizationSearch(searchId)
      setOutcome(body)
      setOutcomeMode('stored')
      setSelectedProposalId(
        body.status.best_proposal_id ?? body.candidates[0]?.proposal.proposal_id ?? null,
      )
    } catch (error) {
      setSearchError(asApiError(error))
    } finally {
      setReplayingId(null)
    }
  }

  function openBranch(branchScenarioId: string) {
    ws.reloadScenarios()
    ws.selectScenario(branchScenarioId)
    ws.setView('analysis')
  }

  function handlePromoted(_result: PromotionResult) {
    ws.reloadScenarios()
  }

  return (
    <div className="opt-studio" data-testid="optimization-studio">
      <Panel
        title="Fix This Plan (A) - scope, limits and the search domain"
        subtitle="Bounded, deterministic search over the bundled synthetic intervention library. The backend enumerates and verifies every candidate with the real analysis engine."
      >
        <KeyValueList
          columns={2}
          items={[
            { term: 'Scenario', value: <span className="mono">{scenarioId}</span> },
            { term: 'Revision', value: ws.scenarioSummary ? String(ws.scenarioSummary.revision) : 'loading' },
            { term: 'Phase', value: <span className="mono">{phaseId}</span> },
            {
              term: 'Profiles',
              value: 'All profiles declared by the scenario are evaluated; the result lists them.',
            },
            { term: 'Evaluation instant', value: <span className="mono">{ws.evaluationInstant || 'service default'}</span> },
          ]}
        />
        <div className="opt-controls opt-section">
          <label className="opt-field">
            Max interventions per candidate
            <select
              value={maxInterventions}
              data-testid="limit-max-interventions"
              onChange={(event) => setMaxInterventions(Number(event.target.value))}
            >
              {[1, 2, 3, 4].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="opt-field">
            Max candidates
            <input
              type="number"
              min={1}
              max={500}
              value={maxCandidates}
              data-testid="limit-max-candidates"
              onChange={(event) => setMaxCandidates(Number(event.target.value))}
            />
          </label>
          <label className="opt-field">
            Max duration (ms)
            <input
              type="number"
              min={100}
              max={600000}
              step={100}
              value={maxDurationMs}
              data-testid="limit-max-duration"
              onChange={(event) => setMaxDurationMs(Number(event.target.value))}
            />
          </label>
          <label className="opt-check">
            <input
              type="checkbox"
              checked={monetary}
              data-testid="monetary-toggle"
              onChange={(event) => setMonetary(event.target.checked)}
            />
            Rank using nominal demo prices (default off)
          </label>
        </div>
        <div className="opt-controls opt-section">
          <label className="opt-check">
            <input
              type="checkbox"
              checked={budgetEnabled}
              data-testid="budget-toggle"
              onChange={(event) => setBudgetEnabled(event.target.checked)}
            />
            Filter by a budget
          </label>
          <label className="opt-field">
            Budget amount
            <input
              type="number"
              min={0}
              value={budgetAmount}
              disabled={!budgetEnabled}
              data-testid="budget-amount"
              onChange={(event) => setBudgetAmount(event.target.value)}
            />
          </label>
          <label className="opt-field">
            Currency
            <input
              type="text"
              value={budgetCurrency}
              disabled={!budgetEnabled}
              data-testid="budget-currency"
              onChange={(event) => setBudgetCurrency(event.target.value)}
            />
          </label>
          <label className="opt-field">
            Basis
            <select
              value={budgetBasis}
              disabled={!budgetEnabled}
              data-testid="budget-basis"
              onChange={(event) => setBudgetBasis(event.target.value as 'nominal' | 'conservative_max')}
            >
              <option value="nominal">Nominal demo prices</option>
              <option value="conservative_max">Declared upper bounds</option>
            </select>
          </label>
        </div>
        <p className="opt-note">
          Limits are hard: the engine stops at them, the result states which limit was hit, and a
          truncated search is reported as “feasible, not proven optimal”, never as optimal. Budgets
          are compared on the stated basis only - no exchange rate is ever invented, and candidates
          with unpriced items are refused rather than assumed to fit.
        </p>
        <div className="opt-section">
          <Button variant="primary" busy={searching} onClick={runSearch} data-testid="run-search">
            Run bounded search
          </Button>
        </div>
        {searchError ? (
          <ErrorPanel
            title="Search failed"
            message={searchError.userMessage}
            code={searchError.code}
          />
        ) : null}
        {excludedIds.length > 0 ? (
          <p className="opt-note" data-testid="excluded-count">
            Excluded from the search domain by you: {excludedIds.join(', ')}
          </p>
        ) : null}
      </Panel>

      <Panel
        title="Intervention library (B) - eligibility and cost discipline"
        subtitle="Unchecking an intervention excludes it from the next search domain; reasons come from the backend's own precondition assessment."
      >
        {catalog.loading ? (
          <Spinner label="Loading the intervention library" />
        ) : catalog.error ? (
          <ErrorPanel
            title="Intervention library unavailable"
            message={catalog.error.userMessage}
            code={catalog.error.code}
          />
        ) : catalog.data ? (
          <LibraryPanel
            catalog={catalog.data}
            excludedIds={excludedIds}
            onToggleExcluded={toggleExcluded}
          />
        ) : null}
      </Panel>

      {currentOutcome ? (
        <>
          <Panel
            title="Search status and honesty (F)"
            subtitle="What the solver can and cannot claim about this result."
          >
            <div className="opt-statusbar" data-testid="search-status">
              <ToneBadge
                tone={solverStatusTone(currentOutcome.status.solver_status)}
                glyph={currentOutcome.status.solver_status === 'OPTIMAL_IN_ENUMERATED_DOMAIN' ? '✓' : '~'}
                title={solverStatusLabel(currentOutcome.status.solver_status)}
              >
                {solverStatusLabel(currentOutcome.status.solver_status)}
              </ToneBadge>
              <span className="opt-chip" data-testid="exhaustive-chip">
                {currentOutcome.status.exhaustive ? 'Domain exhausted' : 'Domain not exhausted'}
              </span>
              <span className="opt-chip" data-testid="result-mode">
                {outcomeMode === 'live' ? 'Fresh search' : 'Stored payload replay'}
              </span>
              {(currentOutcome.status.limits_hit ?? []).map((limit) => (
                <span key={limit} className="opt-chip">
                  limit hit: {limit}
                </span>
              ))}
              {currentOutcome.status.best_proposal_id ? (
                <span className="opt-chip mono" data-testid="best-proposal">
                  best: {currentOutcome.status.best_proposal_id}
                </span>
              ) : null}
            </div>
            {staleRevision !== null ? (
              <p className="opt-banner" data-testid="stale-search">
                This result was computed against revision {currentOutcome.scenario_revision}; the
                scenario is now revision {staleRevision}. Promotion re-checks staleness and will
                refuse a stale search rather than apply it silently.
              </p>
            ) : null}
            <p className="opt-note">{currentOutcome.status.scope_note}</p>
            {(currentOutcome.status.notes ?? []).length > 0 ? (
              <ul className="opt-reasons">
                {(currentOutcome.status.notes ?? []).map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}
            <div className="opt-section">
              <KeyValueList
                columns={2}
                items={[
                  {
                    term: 'Search id',
                    value: (
                      <span className="mono" data-testid="search-id">
                        {currentOutcome.search_id}
                      </span>
                    ),
                  },
                  { term: 'Created', value: formatTimestamp(currentOutcome.created_at) },
                  { term: 'Duration', value: formatDuration(currentOutcome.duration_ms) },
                  { term: 'Engine', value: <span className="mono">{currentOutcome.engine_version}</span> },
                  {
                    term: 'Result semantic hash',
                    value: <span className="mono">{formatHash(currentOutcome.semantic_hash ?? '')}</span>,
                  },
                  { term: 'Rulepack', value: <span className="mono">{currentOutcome.rulepack_id}</span> },
                  {
                    term: 'Limits used',
                    value: (
                      <span className="mono" data-testid="limits-used">
                        max {currentOutcome.config.max_interventions ?? '—'} interventions, max{' '}
                        {currentOutcome.config.max_candidates ?? '—'} candidates, max{' '}
                        {currentOutcome.config.max_duration_ms ?? '—'} ms
                        {currentOutcome.config.budget
                          ? `, budget ${currentOutcome.config.budget.amount} ${currentOutcome.config.budget.currency ?? ''} (${currentOutcome.config.budget.basis ?? 'nominal'})`
                          : ', no budget'}
                      </span>
                    ),
                  },
                  { term: 'Monetary ranking', value: currentOutcome.config.monetary_objective === 'nominal' ? 'On (nominal demo prices)' : 'Off (default)' },
                  {
                    term: 'Ranking policy',
                    value: <span className="mono">{currentOutcome.ranking_policy.id ?? 'unknown'}</span>,
                  },
                ]}
              />
              {currentOutcome.ranking_policy.description ? (
                <p className="opt-note">{currentOutcome.ranking_policy.description}</p>
              ) : null}
              {(currentOutcome.ranking_policy.order ?? []).length > 0 ? (
                <p className="opt-note mono">
                  order: {(currentOutcome.ranking_policy.order ?? []).join(' → ')}
                </p>
              ) : null}
            </div>
            {(currentOutcome.disclaimers ?? []).length > 0 ? (
              <ul className="opt-disclaimers">
                {(currentOutcome.disclaimers ?? []).map((disclaimer) => (
                  <li key={disclaimer}>{disclaimer}</li>
                ))}
              </ul>
            ) : null}
          </Panel>

          <Panel
            title="Candidate ranking (D)"
            subtitle="Ordered by the declared lexicographic policy; ties are ordered deterministically by proposal id."
          >
            <div className="opt-note" data-testid="domain-stats">
              Enumerated domain: {currentOutcome.domain.domain_combination_count} combinations;{' '}
              {currentOutcome.domain.evaluated_count ?? 0} evaluated. Eligible:{' '}
              {currentOutcome.domain.eligible_intervention_ids.length} intervention(s). Blocked by
              dependencies: {currentOutcome.domain.dependency_blocked?.length ?? 0}; mutually
              exclusive: {currentOutcome.domain.mutually_exclusive_blocked?.length ?? 0}; failed
              preconditions: {currentOutcome.domain.precondition_rejected?.length ?? 0}.{' '}
              {(currentOutcome.domain.truncated_by ?? []).length > 0
                ? `Truncated by: ${(currentOutcome.domain.truncated_by ?? []).join(', ')}.`
                : 'Not truncated.'}
            </div>
            {currentOutcome.domain.excluded_interventions.length > 0 ? (
              <ul className="opt-reasons" data-testid="domain-excluded">
                {currentOutcome.domain.excluded_interventions.map((entry) => (
                  <li key={entry.intervention_id} className="mono">
                    {entry.intervention_id}: {entry.reasons.join('; ')}
                  </li>
                ))}
              </ul>
            ) : null}
            {(currentOutcome.domain.dependency_blocked ?? []).length > 0 ? (
              <ul className="opt-reasons">
                {(currentOutcome.domain.dependency_blocked ?? []).map((entry, index) => (
                  <li key={index} className="mono">
                    blocked: {describeEntry(entry)}
                  </li>
                ))}
              </ul>
            ) : null}
            {(currentOutcome.domain.mutually_exclusive_blocked ?? []).length > 0 ? (
              <ul className="opt-reasons">
                {(currentOutcome.domain.mutually_exclusive_blocked ?? []).map((entry, index) => (
                  <li key={index} className="mono">
                    excluded pair: {describeEntry(entry)}
                  </li>
                ))}
              </ul>
            ) : null}
            <CandidateTable
              outcome={currentOutcome}
              selectedProposalId={selectedCandidate?.proposal.proposal_id ?? null}
              onSelect={setSelectedProposalId}
              names={names}
            />
          </Panel>

          {selectedCandidate ? (
            <Panel
              title="Candidate detail (E) - verification, cost and apply-to-branch"
              subtitle="Before/after values are real engine runs of the source and of the materialised candidate."
            >
              <CandidateDetail
                key={selectedCandidate.proposal.proposal_id}
                outcome={currentOutcome}
                candidate={selectedCandidate}
                expectedSourceRevision={ws.scenarioSummary?.revision ?? null}
                api={api}
                names={names}
                onPromoted={handlePromoted}
                onOpenBranch={openBranch}
              />
            </Panel>
          ) : null}
        </>
      ) : (
        <Panel title="Results" subtitle="No search has been run for this scenario and phase in this session yet.">
          <EmptyState
            title="Nothing searched yet"
            description="Run a bounded search above, or replay a stored search from the history below."
          />
        </Panel>
      )}

      <Panel
        title="Search history (G) - stored payloads for deterministic replay"
        subtitle="Every search is persisted with its semantic hash; replay serves the stored payload byte-for-byte."
      >
        {history.loading ? (
          <Spinner label="Loading search history" />
        ) : history.error ? (
          <ErrorPanel
            title="Search history unavailable"
            message={history.error.userMessage}
            code={history.error.code}
          />
        ) : history.data && history.data.searches.length > 0 ? (
          <div className="opt-scroll">
            <table className="data-table" data-testid="search-history">
              <thead>
                <tr>
                  <th scope="col">Created</th>
                  <th scope="col">Search</th>
                  <th scope="col">Revision</th>
                  <th scope="col">Phase</th>
                  <th scope="col">Solver</th>
                  <th scope="col">Candidates</th>
                  <th scope="col">Best</th>
                  <th scope="col">Semantic hash</th>
                  <th scope="col">Replay</th>
                </tr>
              </thead>
              <tbody>
                {history.data.searches.map((entry) => (
                  <tr key={entry.search_id} className="opt-history-row">
                    <td>{formatTimestamp(entry.created_at)}</td>
                    <td className="data-table__mono">{entry.search_id}</td>
                    <td className="data-table__mono">{entry.scenario_revision}</td>
                    <td className="data-table__mono">{entry.phase_id}</td>
                    <td>{entry.solver_status ? solverStatusLabel(entry.solver_status) : 'Unknown'}</td>
                    <td className="data-table__mono">{entry.candidate_count}</td>
                    <td className="data-table__mono">{entry.best_proposal_id ?? '—'}</td>
                    <td className="data-table__mono">{formatHash(entry.semantic_hash)}</td>
                    <td>
                      <Button
                        variant="ghost"
                        busy={replayingId === entry.search_id}
                        onClick={() => replay(entry.search_id)}
                        data-testid={`replay-${entry.search_id}`}
                      >
                        Replay
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title="No stored searches for this scenario yet" />
        )}
        <p className="opt-note">
          Promotion from a replayed payload is possible and re-checked server-side: a stale revision,
          a taken branch id or a changed source is refused with an explicit conflict.
        </p>
      </Panel>
    </div>
  )
}
