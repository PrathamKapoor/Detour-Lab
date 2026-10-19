import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiClient } from '@/api/client'
import type {
  CandidateEvaluation,
  InterventionCatalog,
  PromotionResult,
  SearchOutcome,
} from '@/api/types'
import { CandidateTable } from '@/features/optimization/CandidateTable'
import { CandidateDetail } from '@/features/optimization/CandidateDetail'
import { LibraryPanel } from '@/features/optimization/LibraryPanel'
import {
  budgetMeta,
  classificationMeta,
  formatCost,
  formatSignedMetres,
  solverStatusLabel,
} from '@/features/optimization/presentation'

const CURB = 'INT-MODEL-CURB-N_EK'
const BYPASS = 'INT-BYPASS-IN-PHASE-1'
const WHEELCHAIR = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'
const WALKER = 'DEMO_PROFILE_LIMITED_MOBILITY_WALKER'
const E_LIB = 'OD-E->OD-LIB'
const W_LIB = 'OD-W->OD-LIB'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function clientWith(fetchImpl: typeof fetch) {
  return new ApiClient({ baseUrl: '', fetchImpl, timeoutMs: 50 })
}

function curbCandidate(): CandidateEvaluation {
  return {
    proposal: {
      proposal_id: 'cand-curb',
      intervention_ids: [CURB],
      eligible: true,
      rejection_reasons: [],
      restored_required_od: true,
      requires_verification: false,
      passed_profiles: [WALKER, WHEELCHAIR],
      failed_profiles: [],
      cost_nominal: 18000,
      cost_max: null,
      cost_unknown: false,
      added_distance_m: 0,
      solver_status: 'OPTIMAL_IN_ENUMERATED_DOMAIN',
    },
    classification: 'certified',
    intervention_ids: [CURB],
    intervention_count: 1,
    restored_all_profiles: [E_LIB, W_LIB],
    restored_any_profile: [E_LIB, W_LIB],
    regressed_pairs: [],
    verifications: [
      {
        profile_id: WHEELCHAIR,
        source_semantic_hash: 'sha256:source',
        candidate_semantic_hash: 'sha256:candidate',
        candidate_phase_graph_id: 'demo-graph-v1~candidate~phase:phase-1',
        candidate_phase_graph_hash: 'sha256:pg',
        od_transitions: [
          {
            origin_id: 'OD-E',
            destination_id: 'OD-LIB',
            before_confirmed: false,
            before_possible: true,
            after_confirmed: true,
            after_possible: true,
            before_distance_m: null,
            after_distance_m: 18,
            added_distance_m: null,
          },
          {
            origin_id: 'OD-W',
            destination_id: 'OD-LIB',
            before_confirmed: true,
            before_possible: true,
            after_confirmed: true,
            after_possible: true,
            before_distance_m: 98,
            after_distance_m: 98,
            added_distance_m: 0,
          },
        ],
        restored_pairs: [E_LIB],
        gained_possible_pairs: [],
        regressed_pairs: [],
        new_fail_verdicts: [],
        new_unknown_verdicts: [],
        added_distance_m: 0,
        comparable_route_count: 1,
      },
    ],
    assumptions: [
      {
        intervention_id: CURB,
        element_id: 'N_EK',
        field: 'kerb_upstand_mm',
        value_display: '0',
        unit: 'mm',
        provenance_class: 'synthetic',
        verification_status: 'unverified',
        note: 'Modelled flush transition; demo value.',
        requires_field_verification: true,
      },
    ],
    applied_phase_changes: [],
    introduced_fail_verdict_count: 0,
    introduced_unknown_verdict_count: 0,
    cost: {
      currency: 'INR',
      nominal: 18000,
      maximum: null,
      unknown: false,
      mixed_currency: false,
      provenance_notes: ['Synthetic demo prices only.'],
      lines: [
        {
          intervention_id: CURB,
          cost_id: 'cost-curb',
          label: 'Flush the crossing transition',
          provenance: 'demo_only',
          currency: 'INR',
          quantity: 1,
          unit: 'item',
          total_nominal: 18000,
          total_max: null,
        },
      ],
    },
    budget: { status: 'not_requested', detail: '' },
    preview_scenario_hash: 'sha256:preview',
    preview_phase_graph_hash: 'sha256:preview-pg',
    rank: 1,
    pareto_optimal: true,
    tie_group: 0,
    evaluation_failure: null,
  }
}

function bypassCandidate(): CandidateEvaluation {
  return {
    proposal: {
      proposal_id: 'cand-bypass',
      intervention_ids: [BYPASS],
      eligible: false,
      rejection_reasons: [
        'introduces 1 new hard model-FAIL verdict(s), e.g. E_TMP::WIDTH_MIN (DEMO_PROFILE_LIMITED_MOBILITY_WALKER)',
      ],
      restored_required_od: false,
      requires_verification: false,
      passed_profiles: [WHEELCHAIR],
      failed_profiles: [WALKER],
      cost_nominal: null,
      cost_max: null,
      cost_unknown: true,
      added_distance_m: null,
      solver_status: 'FEASIBLE_NOT_PROVEN_OPTIMAL',
    },
    classification: 'rejected',
    intervention_ids: [BYPASS],
    intervention_count: 1,
    restored_all_profiles: [],
    restored_any_profile: [],
    regressed_pairs: [],
    verifications: [
      {
        profile_id: WALKER,
        source_semantic_hash: 'sha256:source',
        candidate_semantic_hash: 'sha256:candidate2',
        candidate_phase_graph_id: 'demo-graph-v1~candidate2~phase:phase-1',
        candidate_phase_graph_hash: 'sha256:pg2',
        od_transitions: [],
        restored_pairs: [],
        gained_possible_pairs: [],
        regressed_pairs: [],
        new_fail_verdicts: [{ element_id: 'TMP-BYPASS-LINK', rule_id: 'WIDTH_MIN' }],
        new_unknown_verdicts: [],
        added_distance_m: null,
        comparable_route_count: 0,
      },
    ],
    assumptions: [],
    applied_phase_changes: [],
    introduced_fail_verdict_count: 1,
    introduced_unknown_verdict_count: 0,
    cost: { currency: null, nominal: null, maximum: null, unknown: true, mixed_currency: false },
    budget: { status: 'not_requested', detail: '' },
    preview_scenario_hash: 'sha256:preview2',
    preview_phase_graph_hash: 'sha256:preview-pg2',
    rank: 2,
    pareto_optimal: false,
    tie_group: 1,
    evaluation_failure: null,
  }
}

function makeOutcome(): SearchOutcome {
  return {
    engine_version: 'detour-lab-engine/0.1.0',
    search_id: 'opt-tests',
    created_at: '2026-03-01T00:00:01Z',
    duration_ms: 123.4,
    scenario_id: 'scn-demo-baseline',
    scenario_revision: 1,
    scenario_content_hash: 'sha256:content',
    base_graph_version_id: 'demo-graph-v1',
    base_graph_hash: 'sha256:base',
    rulepack_id: 'DEMO_RULEPACK_NOT_LEGAL',
    rulepack_hash: 'sha256:rp',
    phase_id: 'phase-1',
    profile_ids: [WHEELCHAIR, WALKER],
    evaluation_instant: '2026-03-01T00:00:00+00:00',
    config: {
      max_interventions: 2,
      max_candidates: 60,
      max_duration_ms: 120000,
      excluded_intervention_ids: [],
      budget: null,
      monetary_objective: 'off',
    },
    domain: {
      eligible_intervention_ids: [CURB, BYPASS],
      excluded_interventions: [],
      domain_combination_count: 3,
      evaluated_count: 3,
      truncated_by: [],
      exhausted: true,
      dependency_blocked: [],
      mutually_exclusive_blocked: [],
      precondition_rejected: [],
    },
    baseline: [
      {
        profile_id: WHEELCHAIR,
        semantic_hash: 'sha256:b1',
        phase_graph_id: 'demo-graph-v1~scenario~phase:phase-1',
        phase_graph_hash: 'sha256:bpg',
        od_results: [],
      },
    ],
    candidates: [curbCandidate(), bypassCandidate()],
    ranking_policy: {
      id: 'DETOUR_LAB_LEXICOGRAPHIC_V1',
      version: '1.0.0',
      monetary_default: 'off',
      order: ['classification', 'restoration'],
      description: 'Fixed lexicographic order; ties break on proposal id.',
    },
    status: {
      solver_status: 'OPTIMAL_IN_ENUMERATED_DOMAIN',
      exhaustive: true,
      limits_hit: [],
      best_proposal_id: 'cand-curb',
      scope_note:
        'Results apply to the selected phase and profile set only. A single-phase improvement is not whole-project continuity.',
      notes: [],
    },
    input_hash: 'sha256:in',
    semantic_hash: 'sha256:sem',
    disclaimers: ['Modeled checks only; not legal compliance.', 'Synthetic demo data only.'],
  }
}

function makeCatalog(): InterventionCatalog {
  return {
    library: {
      id: 'DEMO_INTERVENTIONS_NOT_ENGINEERED',
      version: '1.0.0',
      notice: 'Synthetic demonstration interventions authored in this repository.',
      source: 'data/demo/interventions.demo.json',
    },
    scenario_id: 'scn-demo-baseline',
    scenario_revision: 1,
    phase_id: 'phase-1',
    declared_phases: ['phase-1', 'phase-2'],
    evaluated_as_of: '2026-03-01T00:00:00+00:00',
    interventions: [
      {
        id: CURB,
        name: 'Flush the crossing transition',
        applicable: true,
        eligibility_reasons: [],
        allowed_ops: ['update_attribute'],
        target_element_ids: ['N_EK'],
        phases: ['phase-1'],
        costs: [
          {
            id: 'cost-curb',
            label: 'Flush the crossing transition',
            provenance: 'demo_only',
            currency: 'INR',
            quantity: 1,
            unit: 'item',
            unit_price_nominal: 18000,
          },
        ],
      },
      {
        id: 'INT-TEMP-BACKLANE-TRACK',
        name: 'Back lane trackway',
        applicable: true,
        eligibility_reasons: [],
        allowed_ops: ['add_edge'],
        costs: [
          {
            id: 'cost-backlane',
            label: 'Lay trackway',
            provenance: 'unknown',
            currency: 'INR',
            quantity: 1,
            unit: 'item',
            unit_price_nominal: null,
          },
        ],
      },
      {
        id: 'INT-REOPEN-E_ES1-P2',
        name: 'Reopen the crossing',
        applicable: false,
        eligibility_reasons: ['declared for phase phase-2 only'],
        allowed_ops: ['link_crossing'],
        costs: [],
      },
    ],
    eligible_intervention_ids: [CURB, 'INT-TEMP-BACKLANE-TRACK'],
    excluded: [],
    precondition_rejected: [],
  }
}

const promotionResult: PromotionResult = {
  engine_version: 'detour-lab-engine/0.1.0',
  search_id: 'opt-tests',
  proposal_id: 'cand-curb',
  classification: 'certified',
  source: {
    scenario_id: 'scn-demo-baseline',
    revision: 1,
    content_hash: 'sha256:content',
    unchanged: true,
  },
  branch: {
    scenario_id: 'scn-fix-curb',
    name: 'Fix: Flush the crossing transition',
    revision: 1,
    parent_scenario_id: 'scn-demo-baseline',
    content_hash: 'sha256:branch',
    intervention_ids: [CURB],
  },
  verification: {
    content_hash_match: true,
    per_profile: [
      {
        profile_id: WHEELCHAIR,
        preview_semantic_hash: 'sha256:preview-sem',
        persisted_semantic_hash: 'sha256:preview-sem',
        match: true,
      },
    ],
    all_match: true,
  },
  od_summary: { restored_all_profiles: [E_LIB, W_LIB], restored_any_profile: [E_LIB, W_LIB], regressed_pairs: [] },
  disclaimers: [
    'The branch carries modelled demo values from the intervention library; they are not field-verified and are not legal or engineering approval.',
    'A single-phase improvement is not whole-project continuity.',
  ],
}

describe('optimization presentation helpers', () => {
  it('never estimates an unknown cost', () => {
    expect(formatCost(null, 'INR')).toBe('Not estimated')
    expect(formatCost(undefined, null)).toBe('Not estimated')
    expect(formatCost(18000, 'INR')).toContain('18,000')
    expect(formatCost(18000, 'INR')).toContain('INR')
  })

  it('marks a missing route comparison as not comparable', () => {
    expect(formatSignedMetres(null)).toBe('Not comparable')
    expect(formatSignedMetres(-14.137)).toBe('-14.1 m')
    expect(formatSignedMetres(0)).toBe('0.0 m')
  })

  it('maps classification and solver statuses without inventing certainty', () => {
    expect(classificationMeta('certified').tone).toBe('pass')
    expect(classificationMeta('requires_verification').tone).toBe('unknown')
    expect(classificationMeta('nonsense').tone).toBe('fail')
    expect(solverStatusLabel('FEASIBLE_NOT_PROVEN_OPTIMAL')).toMatch(/not proven/i)
    expect(budgetMeta('cannot_certify_unknown_cost').label).toMatch(/cannot be certified/i)
  })
})

describe('CandidateTable', () => {
  it('renders candidates in the engine order and reports selection', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <CandidateTable
        outcome={makeOutcome()}
        selectedProposalId="cand-curb"
        onSelect={onSelect}
        names={{ [CURB]: 'Flush the crossing transition' }}
      />,
    )

    const rows = screen.getAllByTestId(/^candidate-row-/)
    expect(rows).toHaveLength(2)
    const [curbRow, bypassRow] = rows
    if (!curbRow || !bypassRow) throw new Error('expected two candidate rows')
    expect(curbRow).toHaveAttribute('data-testid', 'candidate-row-cand-curb')
    expect(within(curbRow).getByText('Model-certified')).toBeInTheDocument()
    expect(within(curbRow).getByText(/Flush the crossing transition/)).toBeInTheDocument()
    expect(bypassRow).toHaveAttribute('data-testid', 'candidate-row-cand-bypass')
    expect(within(bypassRow).getByText('Rejected')).toBeInTheDocument()
    expect(within(bypassRow).getByText(/new hard model-FAIL/)).toBeInTheDocument()

    await user.click(bypassRow)
    expect(onSelect).toHaveBeenCalledWith('cand-bypass')
  })
})

describe('LibraryPanel', () => {
  it('shows eligibility reasons and never estimates an unlisted price', () => {
    render(<LibraryPanel catalog={makeCatalog()} excludedIds={[]} />)
    expect(screen.getByText(/declared for phase phase-2 only/)).toBeInTheDocument()
    expect(screen.getAllByText(/Not estimated/).length).toBeGreaterThan(0)
    expect(screen.getByText(/18,000/)).toBeInTheDocument()
  })

  it('toggles an intervention out of the search domain', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    render(
      <LibraryPanel catalog={makeCatalog()} excludedIds={[]} onToggleExcluded={onToggle} />,
    )
    await user.click(screen.getByLabelText(`Include ${CURB} in the search domain`))
    expect(onToggle).toHaveBeenCalledWith(CURB)
  })
})

describe('CandidateDetail', () => {
  it('renders transitions with unknown-discipline and field-verification flags', () => {
    render(
      <CandidateDetail
        outcome={makeOutcome()}
        candidate={curbCandidate()}
        expectedSourceRevision={1}
        api={clientWith(vi.fn() as unknown as typeof fetch)}
      />,
    )
    expect(screen.getAllByText('Model-confirmed').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Possible only').length).toBeGreaterThan(0)
    // Two "18.0 m" (after distance for E->LIB) and one "Not comparable" (added distance).
    expect(screen.getAllByText('18.0 m').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Not comparable').length).toBeGreaterThan(0)
    expect(screen.getByText('Field verification required')).toBeInTheDocument()
  })

  it('posts the promotion with the optimistic revision and renders the re-verification', async () => {
    const spy = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return jsonResponse(promotionResult, 201)
      return jsonResponse({}, 404)
    })
    const client = clientWith(spy as unknown as typeof fetch)
    const onPromoted = vi.fn()
    const user = userEvent.setup()

    render(
      <CandidateDetail
        outcome={makeOutcome()}
        candidate={curbCandidate()}
        expectedSourceRevision={1}
        api={client}
        onPromoted={onPromoted}
      />,
    )

    await user.click(screen.getByRole('button', { name: /apply to branch/i }))

    await screen.findByTestId('promotion-result')
    expect(screen.getByText('scn-fix-curb')).toBeInTheDocument()
    expect(screen.getByText('Reproduces preview')).toBeInTheDocument()
    expect(screen.getByText(/single-phase improvement/)).toBeInTheDocument()
    expect(onPromoted).toHaveBeenCalledTimes(1)

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/optimization/promote')
    const body = JSON.parse(init.body as string) as Record<string, unknown>
    expect(body).toMatchObject({
      search_id: 'opt-tests',
      proposal_id: 'cand-curb',
      new_scenario_id: 'scn-fix-curb',
      expected_source_revision: 1,
    })
  })

  it('surfaces a refused promotion with the backend envelope, never a silent success', async () => {
    const spy = vi.fn(async () =>
      jsonResponse(
        {
          code: 'SCENARIO_ID_EXISTS',
          message: 'scenario id scn-fix-curb already exists',
          details: {},
          request_id: 'req-1',
        },
        409,
      ),
    )
    const client = clientWith(spy as unknown as typeof fetch)
    const user = userEvent.setup()

    render(
      <CandidateDetail
        outcome={makeOutcome()}
        candidate={curbCandidate()}
        expectedSourceRevision={1}
        api={client}
      />,
    )

    await user.click(screen.getByRole('button', { name: /apply to branch/i }))

    await screen.findByText(/Promotion refused/)
    await waitFor(() => expect(screen.getByText('SCENARIO_ID_EXISTS')).toBeInTheDocument())
    expect(screen.queryByTestId('promotion-result')).not.toBeInTheDocument()
  })

  it('does not silently apply a rejected candidate: the refusal is shown', async () => {
    const spy = vi.fn(async () =>
      jsonResponse(
        {
          code: 'CANDIDATE_REJECTED',
          message: 'candidate is rejected under the hard constraints',
          details: { rejection_reasons: ['new hard model-FAIL'] },
          request_id: 'req-2',
        },
        409,
      ),
    )
    const client = clientWith(spy as unknown as typeof fetch)
    const user = userEvent.setup()

    render(
      <CandidateDetail
        outcome={makeOutcome()}
        candidate={bypassCandidate()}
        expectedSourceRevision={1}
        api={client}
      />,
    )

    expect(screen.getByTestId('rejection-reasons')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /apply to branch/i }))
    await screen.findByText('CANDIDATE_REJECTED')
  })
})
