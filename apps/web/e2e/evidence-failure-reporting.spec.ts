import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { resetDemoBaseline } from './helpers'

/**
 * Gate 6 end-to-end journeys: evidence intelligence, the adversarial Failure
 * Lab, robustness comparison and real PDF export.
 *
 * Everything here runs against the real backend and a real seeded database. No
 * response is mocked and no assertion is satisfied by a screenshot alone: each
 * test names the fact it protects, because a suite that merely checks that
 * panels render would pass even if every number were invented.
 */

const SCENARIO = 'scn-demo-baseline'
const PROFILE_A = 'DEMO_PROFILE_MANUAL_WHEELCHAIR'

async function apiGet(page: Page, path: string) {
  return page.evaluate(async (target) => {
    const response = await fetch(target)
    return { status: response.status, body: await response.json() }
  }, path)
}

/**
 * Creates a scenario that copies the seed's plan but carries no edits, so a
 * journey that must mutate evidence cannot poison the shared demo scenario for
 * the tests that run after it.
 *
 * Creation is not idempotent. A duplicate id is refused with 409
 * SCENARIO_ID_EXISTS, which E2E-G6-04 asserts; this helper therefore treats
 * only 201 as success and reports anything else as the real failure it is.
 */
async function createIsolatedScenario(page: Page, id: string): Promise<string> {
  const status = await page.evaluate(async (scenarioId) => {
    const source = await (await fetch('/api/v1/scenarios/scn-demo-baseline')).json()
    const response = await fetch('/api/v1/projects/demo-project-synthetic/scenarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: scenarioId,
        name: `E2E working copy ${scenarioId}`,
        parent_scenario_id: source.id,
        base_graph_version_id: source.base_graph_version_id,
        phases: source.phases,
        origins_destinations: source.origins_destinations,
        temporary_edges: source.temporary_edges,
        note: 'Isolated working copy created by the Gate 6 end-to-end suite.',
      }),
    })
    return response.status
  }, id)
  if (status !== 201) {
    throw new Error(`could not create the isolated scenario: ${status}`)
  }
  return id
}

async function openEvidenceQueue(page: Page) {
  await page.getByTestId('nav-evidence').click()
  await expect(page.getByTestId('queue-table')).toBeVisible({ timeout: 30_000 })
}

async function openFailureLab(page: Page) {
  await page.getByTestId('nav-failure-lab').click()
  await expect(page.getByTestId('fault-suite-list')).toBeVisible({ timeout: 30_000 })
}

/** Select exactly the named suites, so ordering of earlier selections cannot leak. */
async function selectOnlySuites(page: Page, suiteIds: string[]) {
  const boxes = page.locator('[data-testid^="suite-toggle-"]')
  const count = await boxes.count()
  for (let index = 0; index < count; index += 1) {
    const box = boxes.nth(index)
    const testId = (await box.getAttribute('data-testid')) ?? ''
    const suiteId = testId.replace('suite-toggle-', '')
    if (suiteIds.includes(suiteId)) await box.check()
    else await box.uncheck()
  }
}

test.beforeAll(() => {
  resetDemoBaseline()
})

test.describe('Gate 6 — evidence intelligence', () => {
  test('E2E-G6-01 loads real unresolved issues derived by the backend', async ({ page }) => {
    await page.goto('/')
    await openEvidenceQueue(page)

    // The queue must match what the backend derives, not what the page assumed.
    const backend = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/evidence/queue`)
    expect(backend.status).toBe(200)
    const rows = page.locator('[data-testid^="queue-row-"]')
    await expect(rows).toHaveCount(backend.body.issues.length)
    expect(backend.body.issues.length).toBeGreaterThan(0)
    await expect(page.getByTestId('queue-count')).toHaveText(String(backend.body.issues.length))
  })

  test('E2E-G6-02 selecting an issue inspects the affected graph element', async ({ page }) => {
    await page.goto('/')
    await openEvidenceQueue(page)

    const firstIssue = await page.locator('[data-testid^="queue-row-"]').first().getAttribute('data-testid')
    const issueId = (firstIssue ?? '').replace('queue-row-', '')
    await page.getByTestId(`queue-inspect-${issueId}`).click()

    await expect(page.getByTestId('detail-issue-id')).toHaveText(issueId)
    await expect(page.getByTestId('detail-explanation')).not.toBeEmpty()
    await expect(page.getByTestId('detail-caveat')).toContainText('not a physical defect')

    // The detail must name the real element, matching the backend record.
    const backend = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/evidence/issues/${issueId}`)
    expect(backend.status).toBe(200)
    const elementId = backend.body.issue.element_id
    await expect(page.getByRole('heading', { name: `${elementId} · ${backend.body.issue.attribute}` })).toBeVisible()

    // Navigating to the graph must actually select that element.
    await page.getByTestId(`detail-open-element-${issueId}`).click()
    await expect(page.getByTestId('graph-canvas')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId(`inspect-${elementId}`)).toBeVisible({ timeout: 20_000 })
  })

  test('E2E-G6-03 displays the exact resolver status, never a generic label', async ({ page }) => {
    await page.goto('/')
    await openEvidenceQueue(page)

    const backend = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/evidence/queue`)
    const statuses = backend.body.issues.map((i: { issue_id: string; resolution_status: string }) => ({
      issueId: i.issue_id,
      status: i.resolution_status,
    }))
    // The seeded fixture genuinely leaves NO_EVIDENCE attributes unresolved.
    expect(statuses.length).toBeGreaterThan(0)
    for (const { issueId, status } of statuses) {
      await expect(page.getByTestId(`queue-status-${issueId}`)).toHaveText(status)
    }
    // The five conditions must remain distinguishable in the filter.
    for (const code of [
      'NO_EVIDENCE',
      'CONFLICTING_EVIDENCE',
      'UNSUPPORTED_UNIT',
      'EVIDENCE_EXPIRED',
      'EVIDENCE_NOT_VERIFIED',
    ]) {
      await expect(page.getByTestId('queue-status-filter')).toContainText(code)
    }
  })

  test('E2E-G6-04 conflicting evidence is shown without choosing a value', async ({ page }) => {
    await page.goto('/')
    // Works on its own scenario: edits are append-only, so mutating the shared
    // seed here would poison every later journey in this file.
    const scenarioId = await createIsolatedScenario(page, 'scn-e2e-conflict')

    // Creating the same id again is a conflict the caller can act on: the
    // backend must answer 409 SCENARIO_ID_EXISTS in the flat error envelope,
    // not a 500. A 500 here would mean the refusal was an unhandled database
    // error rather than a defined contract.
    const duplicate = await page.evaluate(async (id) => {
      const source = await (await fetch('/api/v1/scenarios/scn-demo-baseline')).json()
      const response = await fetch('/api/v1/projects/demo-project-synthetic/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id,
          name: 'duplicate',
          parent_scenario_id: source.id,
          base_graph_version_id: source.base_graph_version_id,
          phases: source.phases,
          origins_destinations: source.origins_destinations,
          temporary_edges: source.temporary_edges,
        }),
      })
      return { status: response.status, body: await response.json() }
    }, scenarioId)
    expect(duplicate.status).toBe(409)
    expect(duplicate.body.code).toBe('SCENARIO_ID_EXISTS')
    expect(Object.keys(duplicate.body).sort()).toEqual(['code', 'details', 'message', 'request_id'])
    expect(duplicate.body.details.scenario_id).toBe(scenarioId)

    const created = await page.evaluate(async (id) => {
      const source = await (await fetch(`/api/v1/scenarios/${id}`)).json()
      const response = await fetch(`/api/v1/scenarios/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_revision: source.revision,
          edits: [
            {
              op: 'update_attribute',
              target_id: 'E_K1',
              params: {
                field: 'width_mm',
                value: 1800,
                unit: 'mm',
                method: 'field_visit',
                source: 'second surveyor (e2e)',
              },
              reason: 'Gate 6 E2E conflicting measurement fixture',
            },
          ],
        }),
      })
      return { status: response.status, revision: (await response.json()).revision }
    }, scenarioId)
    expect(created.status).toBe(200)

    // The authoritative resolver decides, and picks nothing.
    const detail = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/scenarios/${id}/evidence/queue?statuses=CONFLICTING_EVIDENCE`, {
        headers: { 'Content-Type': 'application/json' },
      })
      return response.json()
    }, scenarioId)
    expect(detail.issues.length).toBeGreaterThan(0)
    const conflict = detail.issues.find((i: { element_id: string }) => i.element_id === 'E_K1')
    expect(conflict).toBeTruthy()
    expect(conflict.resolution_status).toBe('CONFLICTING_EVIDENCE')

    const explain = await page.evaluate(async () => {
      const response = await fetch('/api/v1/projects/demo-project-synthetic/evidence/attributes/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: 'demo-project-synthetic',
          element_id: 'E_K1',
          field: 'width_mm',
        }),
      })
      return response.json()
    })
    // The base graph still carries the single seeded observation, so the
    // resolver reports it as known; the conflict lives on the scenario branch.
    expect(explain.resolved).toBe(true)

    const conflicted = await page.evaluate(async (id) => {
      const response = await fetch(`/api/v1/scenarios/${id}/evidence/issues/${'EQ-any'}`, {
        headers: { 'Content-Type': 'application/json' },
      })
      return response.status
    }, scenarioId)
    expect(conflicted).toBe(404)

    // Open the isolated scenario in the UI and read the conflict there.
    await page.getByTestId('nav-scenario').click()
    await expect(page.getByTestId('scenario-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('scenario-select').selectOption(scenarioId)
    await page.getByTestId('nav-evidence').click()
    await expect(page.getByTestId('queue-table')).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('queue-status-filter').selectOption('CONFLICTING_EVIDENCE')

    const row = page.locator('[data-testid^="queue-row-"]').first()
    await expect(row).toBeVisible({ timeout: 20_000 })
    const rowId = ((await row.getAttribute('data-testid')) ?? '').replace('queue-row-', '')
    await expect(page.getByTestId(`queue-status-${rowId}`)).toHaveText('CONFLICTING_EVIDENCE')

    await page.getByTestId(`queue-inspect-${rowId}`).click()
    await expect(page.getByTestId('detail-conflict-values')).toContainText('1100')
    await expect(page.getByTestId('detail-conflict-values')).toContainText('1800')
    await expect(page.getByTestId('detail-selection-note')).toContainText('No observation is selected')
    await expect(page.getByTestId('detail-explanation')).toContainText('disagree')
  })

  test('E2E-G6-05 prioritisation is deterministic and explained, with no score', async ({ page }) => {
    await page.goto('/')
    await openEvidenceQueue(page)

    const first = await page.locator('[data-testid^="queue-row-"]').evaluateAll((rows) =>
      rows.map((row) => row.getAttribute('data-testid')),
    )
    await page.reload()
    await openEvidenceQueue(page)
    const second = await page.locator('[data-testid^="queue-row-"]').evaluateAll((rows) =>
      rows.map((row) => row.getAttribute('data-testid')),
    )
    expect(second).toEqual(first)

    await expect(page.getByTestId('queue-method')).toContainText('No probability')
    // No fabricated "importance" number anywhere in the queue surface.
    const queuePanel = page.getByTestId('queue-main')
    await expect(queuePanel).not.toContainText('%')
    await expect(queuePanel).not.toContainText(/importance score/i)

    // The first issue must carry a written rationale.
    const firstId = (first[0] ?? '').replace('queue-row-', '')
    await page.getByTestId(`queue-inspect-${firstId}`).click()
    const rationale = page.getByTestId('detail-rationale')
    await expect(rationale).toBeVisible()
    expect((await rationale.innerText()).length).toBeGreaterThan(40)
  })

  test('E2E-G6-06 the evidence queue is operable by keyboard alone', async ({ page }) => {
    await page.goto('/')
    await openEvidenceQueue(page)

    const firstId = (
      (await page.locator('[data-testid^="queue-row-"]').first().getAttribute('data-testid')) ?? ''
    ).replace('queue-row-', '')

    const inspect = page.getByTestId(`queue-inspect-${firstId}`)
    await inspect.focus()
    await expect(inspect).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('detail-issue-id')).toHaveText(firstId)

    // Every interactive control in the filter row must be reachable by Tab.
    for (const testId of [
      'queue-status-filter',
      'queue-criticality-filter',
      'queue-element-filter',
      'queue-clear-filters',
    ]) {
      const control = page.getByTestId(testId)
      await control.focus()
      await expect(control).toBeFocused()
    }
  })
})

test.describe('Gate 6 — adversarial failure laboratory', () => {
  test('E2E-G6-07 the Failure Lab opens from a persisted scenario', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)

    const backend = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/failure-lab/catalog`)
    expect(backend.status).toBe(200)
    await expect(page.getByTestId('panel-a-source')).toContainText(SCENARIO)
    await expect(page.getByTestId('panel-a-source')).toContainText('DEMO_RULEPACK_NOT_LEGAL')
    // Supported kinds are listed with their limitations, and omissions are named.
    await expect(page.getByTestId('fault-kind-list')).toContainText('edge_closure')
    await expect(page.getByTestId('fault-kind-list')).toContainText('evidence_removal')
    await expect(page.getByTestId('unsupported-scenarios')).toContainText('Physical obstruction geometry')
  })

  test('E2E-G6-08 only applicable suites are offered as runnable', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)

    // The temporary connection suite is declared only for phase-2, so with
    // phase-1 selected it must be listed as not tested, never as a passing test.
    await expect(page.getByTestId('unavailable-suite-connection_loss')).toContainText('not')
    await expect(page.getByTestId('unavailable-suites')).toContainText('has')
    await expect(page.locator('[data-testid="suite-toggle-connection_loss"]')).toHaveCount(0)

    // The backend must agree with the interface, and must say *why* the suite
    // does not apply. This is the authoritative statement; the panel above is
    // only its rendering.
    const catalog = await apiGet(
      page,
      `/api/v1/scenarios/${SCENARIO}/failure-lab/catalog?phase_id=phase-1`,
    )
    expect(catalog.status).toBe(200)
    const suites = catalog.body.suites as Array<{
      suite_id: string
      applicable: boolean
      applicable_phase_ids: string[]
      target_element_ids: string[]
      unavailable_reason: string
    }>
    const connectionLoss = suites.find((suite) => suite.suite_id === 'connection_loss')
    expect(connectionLoss).toBeTruthy()
    expect(connectionLoss!.applicable).toBe(false)
    expect(connectionLoss!.applicable_phase_ids).toEqual([])
    // The typed fault definition names the phase-2-only temporary connection.
    expect(connectionLoss!.target_element_ids).toContain('TMP-EAST-BYPASS')
    expect(connectionLoss!.unavailable_reason).toBeTruthy()
    expect(connectionLoss!.unavailable_reason.length).toBeGreaterThan(20)

    // A suite whose targets exist in the selected phase must remain runnable,
    // so the refusal is specific rather than a blanket "nothing applies".
    const closure = suites.find((suite) => suite.suite_id === 'critical_closure')
    expect(closure).toBeTruthy()
    expect(closure!.applicable).toBe(true)
    expect(closure!.applicable_phase_ids).toEqual(['phase-1'])
    expect(closure!.unavailable_reason).toBe('')
    await expect(page.locator('[data-testid="suite-toggle-critical_closure"]')).toHaveCount(1)
  })

  test('E2E-G6-09 executes a real backend experiment', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])

    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 60_000 })

    const rows = page.locator('[data-testid^="experiment-row-"]')
    await expect(rows).toHaveCount(1)
    await expect(page.getByTestId('execution-counts')).toContainText('Completed 1 of 1')

    // The experiment must really be persisted.
    const history = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/failure-lab/experiments`)
    expect(history.status).toBe(200)
    expect(history.body.experiment_count).toBeGreaterThanOrEqual(1)
  })

  test('E2E-G6-10 graph state genuinely changes under the fault', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('element-change-table')).toBeVisible({ timeout: 60_000 })

    await expect(page.getByTestId('element-change-E_K2')).toBeVisible()
    // The phase-graph hash must differ between baseline and faulted state.
    const experimentId = await page.locator('[data-testid^="experiment-row-"]').first().getAttribute('data-testid')
    const id = (experimentId ?? '').replace('experiment-row-', '')
    const diff = await apiGet(page, `/api/v1/failure-lab/experiments/${id}/graph-differences`)
    expect(diff.status).toBe(200)
    const changed = diff.body.phase_graph_identities.filter((p: { changed: boolean }) => p.changed)
    expect(changed.length).toBeGreaterThan(0)
    await expect(page.getByTestId('panel-e-visual')).toContainText('Faulted state')
  })

  test('E2E-G6-11 a model-confirmed route becomes disconnected under a critical closure', async ({
    page,
  }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('transition-table')).toBeVisible({ timeout: 60_000 })

    const row = page.getByTestId(`transition-${PROFILE_A}-OD-W->OD-GATE`)
    await expect(row).toBeVisible()
    await expect(row).toContainText('confirmed')
    await expect(row).toContainText('no route')
    await expect(row).toContainText('modelled disconnection')
    // Distance must be reported as not established, never as zero metres.
    await expect(row).toContainText('not established')
  })

  test('E2E-G6-12 an evidence fault produces the authoritative result', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['evidence_gap'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('transition-table')).toBeVisible({ timeout: 60_000 })

    // The masked width turns a confirmed route possible-only, not into a pass.
    const row = page.getByTestId(`transition-${PROFILE_A}-OD-W->OD-GATE`)
    await expect(row).toContainText('possible-only')
    await expect(row).toContainText('NOT confirmed accessibility')

    const experimentId = (await page.locator('[data-testid^="experiment-row-"]').first().getAttribute('data-testid')) ?? ''
    await expect(page.getByTestId('evidence-change-log')).toContainText('masked')
    expect(experimentId).toContain('experiment-row-')
  })

  test('E2E-G6-13 the failure explanation is accurate and bounded', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('fault-definition-list')).toBeVisible({ timeout: 60_000 })

    await expect(page.getByTestId('fault-definition-list')).toContainText('edge_closure')
    await expect(page.getByTestId('fault-definition-list')).toContainText('E_K2')
    await expect(page.getByTestId('experiment-limitations')).toContainText('not a prediction of a real-world failure')
    await expect(page.getByTestId('identity-note')).toContainText('three different identities')
  })

  test('E2E-G6-14 baseline and faulted states can be compared', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['incidental_closure', 'critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('[data-testid^="experiment-row-"]')).toHaveCount(2)

    // Each experiment opens its own element diff, so the two are comparable.
    const rows = page.locator('[data-testid^="experiment-row-"]')
    await rows.nth(0).getByRole('button', { name: 'Open' }).click()
    await expect(page.getByTestId('element-change-table')).toBeVisible({ timeout: 30_000 })
    const firstDiff = await page.getByTestId('element-change-table').innerText()
    await rows.nth(1).getByRole('button', { name: 'Open' }).click()
    await expect(page.getByTestId('element-change-table')).toBeVisible({ timeout: 30_000 })
    const secondDiff = await page.getByTestId('element-change-table').innerText()
    expect(firstDiff).not.toEqual(secondDiff)
  })

  test('E2E-G6-15 Try to Break My Plan executes a real bounded suite', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, [
      'critical_closure',
      'incidental_closure',
      'evidence_gap',
      'conflicting_measurement',
      'unsupported_unit',
      'modelled_obstruction',
      'expired_evidence',
    ])

    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 120_000 })
    await expect(page.locator('[data-testid^="experiment-row-"]')).toHaveCount(7)

    // Progress is a real count, never a fabricated percentage.
    const progress = page.getByTestId('execution-counts')
    await expect(progress).toContainText('Completed 7 of 7')
    await expect(progress).not.toContainText('%')
  })

  test('E2E-G6-16 multiple fault results and execution statuses are reported', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, [
      'critical_closure',
      'evidence_gap',
      'incidental_closure',
    ])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 120_000 })
    await expect(page.locator('[data-testid^="experiment-row-"]')).toHaveCount(3)

    const ids = await page
      .locator('[data-testid^="experiment-row-"]')
      .evaluateAll((rows) => rows.map((row) => (row.getAttribute('data-testid') ?? '').replace('experiment-row-', '')))
    const states = new Set<string>()
    for (const id of ids) {
      const text = await page.getByTestId(`experiment-status-${id}`).innerText()
      states.add(text)
    }
    expect(states.size).toBeGreaterThan(0)
    await expect(page.getByTestId('panel-robustness')).toContainText('Robustness')
  })

  test('E2E-G6-17 a refused experiment is never shown as a network failure', async ({ page }) => {
    await page.goto('/')
    // The connection-loss suite is inapplicable in phase-1 and must be refused.
    const response = await page.evaluate(async (scenario) => {
      const result = await fetch(`/api/v1/scenarios/${scenario}/failure-lab/experiments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phase_ids: ['phase-1'],
          profile_ids: ['DEMO_PROFILE_MANUAL_WHEELCHAIR'],
          suite_ids: ['connection_loss'],
        }),
      })
      return result.json()
    }, SCENARIO)

    const experiment = response.experiments[0]
    expect(experiment.status).toBe('invalid_experiment')
    expect(experiment.observations).toHaveLength(0)
    expect(experiment.error.code).toBe('NO_OP_FAULT')
    expect(response.robustness.experiments_invalid).toBe(1)
    expect(response.robustness.pairs_evaluated).toBe(0)
  })

  test('E2E-G6-18 the source scenario is never modified by an experiment', async ({ page }) => {
    await page.goto('/')
    const before = await apiGet(page, `/api/v1/scenarios/${SCENARIO}`)
    const beforeRuns = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/runs`)
    const beforeGraph = await apiGet(page, '/api/v1/projects/demo-project-synthetic/graph')

    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure', 'evidence_gap'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 60_000 })

    const after = await apiGet(page, `/api/v1/scenarios/${SCENARIO}`)
    const afterRuns = await apiGet(page, `/api/v1/scenarios/${SCENARIO}/runs`)
    const afterGraph = await apiGet(page, '/api/v1/projects/demo-project-synthetic/graph')

    expect(after.body.revision).toBe(before.body.revision)
    expect(after.body.content_hash).toBe(before.body.content_hash)
    expect(afterRuns.body.runs.length).toBe(beforeRuns.body.runs.length)
    expect(afterGraph.body.content_hash).toBe(beforeGraph.body.content_hash)
    expect(afterGraph.body.evidence.length).toBe(beforeGraph.body.evidence.length)
  })

  test('E2E-G6-19 a saved experiment is reproduced after a reload', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 60_000 })

    const experimentId = (
      (await page.locator('[data-testid^="experiment-row-"]').first().getAttribute('data-testid')) ?? ''
    ).replace('experiment-row-', '')

    await page.reload()
    await openFailureLab(page)
    await expect(page.getByTestId('history-table')).toBeVisible({ timeout: 30_000 })
    const row = page.getByTestId(`history-row-${experimentId}`)
    await expect(row).toBeVisible()

    await page.getByTestId(`history-replay-${experimentId}`).click()
    await expect(page.getByTestId('replay-result')).toContainText('Reproduced exactly', { timeout: 60_000 })
  })

  test('E2E-G6-20 the replayed semantic identity is reproducible over HTTP', async ({ page }) => {
    await page.goto('/')
    const created = await page.evaluate(async (scenario) => {
      const response = await fetch(`/api/v1/scenarios/${scenario}/failure-lab/experiments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phase_ids: ['phase-1'],
          profile_ids: ['DEMO_PROFILE_MANUAL_WHEELCHAIR'],
          evaluation_instant: '2026-03-01T00:00:00Z',
          suite_ids: ['critical_closure', 'evidence_gap', 'conflicting_measurement'],
        }),
      })
      return response.json()
    }, SCENARIO)

    expect(created.experiments.length).toBe(3)
    for (const experiment of created.experiments) {
      const replay = await page.evaluate(async (id) => {
        const response = await fetch(`/api/v1/failure-lab/experiments/${id}/replay`, { method: 'POST' })
        return response.json()
      }, experiment.experiment_id)
      expect(replay.reproduced).toBe(true)
      expect(replay.replayed_semantic_hash).toBe(replay.stored_semantic_hash)
      // A replay is a new execution with a new id, never a rewrite.
      expect(replay.replayed_experiment_id).not.toBe(experiment.experiment_id)
    }
  })

  test('E2E-G6-21 failure configuration is operable by keyboard', async ({ page }) => {
    await page.goto('/')
    await openFailureLab(page)

    const box = page.getByTestId('suite-toggle-critical_closure')
    await box.focus()
    await expect(box).toBeFocused()
    await expect(box).toBeChecked()
    await page.keyboard.press('Space')
    await expect(box).not.toBeChecked({ timeout: 10_000 })
    await page.keyboard.press('Space')
    await expect(box).toBeChecked()

    const runButton = page.getByTestId('run-fault-suite')
    await runButton.focus()
    await expect(runButton).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 60_000 })
  })
})

test.describe('Gate 6 — audit-ready PDF reporting', () => {
  test('E2E-G6-22 report generation starts from a real stored analysis', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })

    await page.getByTestId('nav-reports').click()
    await expect(page.getByTestId('generate-report')).toBeVisible({ timeout: 20_000 })
    // Either a stored packet exists or the panel states honestly that none does.
    await expect(
      page.getByTestId('stored-report-table').or(page.getByText('No packets generated yet')),
    ).toBeVisible({ timeout: 30_000 })
  })

  test('E2E-G6-23 generates and downloads a genuine PDF packet', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })

    await page.getByTestId('nav-reports').click()
    await expect(page.getByTestId('generate-report')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('generate-report').click()
    await expect(page.getByTestId('generated-report')).toBeVisible({ timeout: 90_000 })

    // Validate the bytes the browser actually receives.
    const validated = await page.evaluate(async () => {
      const anchor = document.querySelector('[data-testid="download-pdf"]')
      if (!anchor) return { ok: false, reason: 'no download link' }
      const response = await fetch((anchor as HTMLAnchorElement).getAttribute('href') as string)
      const buffer = await response.arrayBuffer()
      const bytes = new Uint8Array(buffer.slice(0, 5))
      const head = String.fromCharCode(...Array.from(bytes))
      return {
        ok: head === '%PDF-',
        reason: head,
        bytes: buffer.byteLength,
        contentType: response.headers.get('content-type'),
        sha256: response.headers.get('x-detour-lab-pdf-sha256'),
        notCertified: response.headers.get('x-detour-lab-not-certified'),
      }
    })
    expect(validated.ok).toBe(true)
    expect(validated.reason).toContain('%PDF-')
    expect(validated.bytes).toBeGreaterThan(10_000)
    expect(validated.contentType).toBe('application/pdf')
    expect(validated.notCertified).toBe('true')
    expect(validated.sha256).toMatch(/^[0-9a-f]{64}$/)
  })

  test('E2E-G6-24 the packet preserves unknown and non-certification disclosures', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('nav-reports').click()
    await page.getByTestId('generate-report').click()
    await expect(page.getByTestId('generated-report')).toBeVisible({ timeout: 90_000 })

    await expect(page.getByTestId('report-disclaimer')).toContainText('PLANNING ANALYSIS - NOT CERTIFIED')
    await expect(page.getByTestId('report-disclaimer')).toContainText('All bundled geometry')
    // A section that was not selected must be marked unavailable, not rendered empty.
    await expect(page.getByTestId('report-section-experiments')).toContainText('not selected')
  })

  test('E2E-G6-25 the canonical report manifest is retrievable and matches', async ({ page }) => {
    await page.goto('/')
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('nav-reports').click()
    await page.getByTestId('generate-report').click()
    await expect(page.getByTestId('generated-report')).toBeVisible({ timeout: 90_000 })

    const reportId = await page.locator('[data-testid="generated-report"]').innerText()
    expect(reportId).toContain('rpt-')

    const manifest = await page.evaluate(async () => {
      const anchor = document.querySelector('[data-testid="download-report-manifest"]')
      const response = await fetch((anchor as HTMLAnchorElement).getAttribute('href') as string)
      return { status: response.status, hash: response.headers.get('x-detour-lab-semantic-hash'), body: await response.json() }
    })
    expect(manifest.status).toBe(200)
    expect(manifest.hash).toMatch(/^sha256:[0-9a-f]{64}$/)
    expect(manifest.body.schema_version).toBeTruthy()
    expect(manifest.body.disclaimer).toContain('NOT CERTIFIED')
    // The packet must name the exact runs it describes.
    expect(manifest.body.reproducibility.selected_run_ids.length).toBeGreaterThan(0)
    expect(manifest.body.identity.scenario_id).toBe(SCENARIO)
  })

  test('E2E-G6-26 report generation failure is surfaced, not faked', async ({ page }) => {
    await page.goto('/')
    const outcome = await page.evaluate(async (scenario) => {
      const response = await fetch(`/api/v1/scenarios/${scenario}/reports`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_ids: ['run-that-does-not-exist'] }),
      })
      return { status: response.status, body: await response.json() }
    }, SCENARIO)
    expect(outcome.status).toBe(404)
    expect(Object.keys(outcome.body).sort()).toEqual(['code', 'details', 'message', 'request_id'])
    expect(outcome.body.code).toBe('NOT_FOUND')

    const missing = await page.evaluate(async () => {
      const response = await fetch('/api/v1/reports/rpt-nope/document.pdf')
      return response.status
    })
    expect(missing).toBe(404)
  })
})

test.describe('Gate 6 — robustness comparison and end-to-end journey', () => {
  test('E2E-G6-27 the robustness summary states its denominator and refuses a probability', async ({
    page,
  }) => {
    await page.goto('/')
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure', 'incidental_closure', 'evidence_gap'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('panel-robustness')).toBeVisible({ timeout: 120_000 })

    await expect(page.getByTestId('robustness-denominator')).toContainText('Only COMPLETED experiments contribute')
    await expect(page.getByTestId('robustness-interpretation')).toContainText('NOT a probability')
    await expect(page.getByTestId('robustness-interpretation')).toContainText('test-coverage')
  })

  test('E2E-G6-28 the new interfaces have no critical automated accessibility violations', async ({
    page,
  }) => {
    for (const nav of ['nav-evidence', 'nav-failure-lab', 'nav-reports']) {
      await page.goto('/')
      await page.getByTestId(nav).click()
      await page.waitForTimeout(600)
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze()
      const serious = results.violations.filter(
        (violation) => violation.impact === 'serious' || violation.impact === 'critical',
      )
      expect(
        serious.map((violation) => `${nav}: ${violation.id}`),
        'serious automated accessibility findings',
      ).toEqual([])
    }
  })

  test('E2E-G6-29 the new interfaces remain usable at a small viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')

    await openEvidenceQueue(page)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)

    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 90_000 })
    const labOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(labOverflow).toBeLessThanOrEqual(1)
  })

  test('E2E-G6-30 the complete flow: evidence to fault suite to robustness to PDF', async ({ page }) => {
    await page.goto('/')

    /* 1. a real analysis */
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })

    /* 2. unresolved evidence */
    await openEvidenceQueue(page)
    const issueId = (
      (await page.locator('[data-testid^="queue-row-"]').first().getAttribute('data-testid')) ?? ''
    ).replace('queue-row-', '')
    await page.getByTestId(`queue-inspect-${issueId}`).click()
    await expect(page.getByTestId('detail-explanation')).toBeVisible()
    const queueText = await page.getByTestId('queue-detail').innerText()
    expect(queueText).toMatch(/NOT|never|no observation/i)

    /* 3. run a fault suite */
    await openFailureLab(page)
    await selectOnlySuites(page, ['critical_closure', 'evidence_gap'])
    await page.getByTestId('run-fault-suite').click()
    await expect(page.getByTestId('experiment-table')).toBeVisible({ timeout: 90_000 })

    /* 4. robustness comparison */
    await expect(page.getByTestId('panel-robustness')).toBeVisible()
    await expect(page.getByTestId('robustness-denominator')).toContainText('Only COMPLETED')

    /* 5. export the packet including the experiments */
    await page.getByTestId('nav-reports').click()
    await expect(page.getByTestId('generate-report')).toBeVisible({ timeout: 20_000 })
    await page.locator('[data-testid^="report-experiment-"]').first().check()
    await page.getByTestId('generate-report').click()
    await expect(page.getByTestId('generated-report')).toBeVisible({ timeout: 120_000 })

    const download = await page.evaluate(async () => {
      const anchor = document.querySelector('[data-testid="download-pdf"]') as HTMLAnchorElement | null
      if (!anchor) return { ok: false }
      const response = await fetch(anchor.getAttribute('href') as string)
      const buffer = await response.arrayBuffer()
      const head = String.fromCharCode(...Array.from(new Uint8Array(buffer.slice(0, 5))))
      return { ok: head === '%PDF-', bytes: buffer.byteLength }
    })
    expect(download.ok).toBe(true)
    expect(download.bytes).toBeGreaterThan(10_000)
  })
})