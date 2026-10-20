import { expect, test, type Page } from '@playwright/test'
import { gotoProjects, useIsolatedScenario } from './helpers'

/**
 * Gate 5 browser acceptance (E2E-G5-01..25), executed against the real backend.
 *
 * Everything this suite exercises runs the real optimisation engine against the
 * real seeded database, and every promotion goes through the transactional
 * apply path. The browser renders verdicts, deltas, costs and rankings; it
 * never derives them.
 *
 * Isolation: every test works on its own scenario copy (see `useIsolatedScenario`),
 * so nothing depends on the order the suite runs in or on edits another spec made.
 */

const CURB = 'INT-MODEL-CURB-N_EK'
const REMEASURE = 'INT-REMEASURE-ALT-TRACK'
const BACKLANE = 'INT-TEMP-BACKLANE-TRACK'
const BYPASS = 'INT-BYPASS-IN-PHASE-1'
const REOPEN = 'INT-REOPEN-E_ES1-P2'
const E_LIB = 'OD-E->OD-LIB'
const W_LIB = 'OD-W->OD-LIB'

async function openStudio(page: Page) {
  await page.getByTestId('nav-optimization').click()
  await expect(page.getByTestId('optimization-studio')).toBeVisible({ timeout: 20_000 })
}

async function waitForLibrary(page: Page) {
  await expect(page.getByTestId('intervention-table')).toBeVisible({ timeout: 20_000 })
}

/**
 * Runs one search and waits for **that** search's identity, not merely for a
 * status panel that may already be on screen from a previous run.
 */
async function runSearch(page: Page) {
  const before = (await page.getByTestId('search-id').count())
    ? await page.getByTestId('search-id').innerText()
    : null
  await page.getByTestId('run-search').click()
  await expect(page.getByTestId('search-status')).toBeVisible({ timeout: 40_000 })
  if (before === null) {
    await expect(page.getByTestId('search-id')).not.toHaveText('', { timeout: 40_000 })
  } else {
    await expect(page.getByTestId('search-id')).not.toHaveText(before, { timeout: 40_000 })
  }
}

function candidateRow(page: Page, ...interventionIds: string[]) {
  return page
    .getByTestId('candidate-table')
    .locator(`tr[data-intervention-ids="${interventionIds.join(' ')}"]`)
}

async function selectCandidate(page: Page, ...interventionIds: string[]) {
  await candidateRow(page, ...interventionIds).click()
  await expect(page.getByTestId('candidate-detail')).toBeVisible({ timeout: 20_000 })
}

async function promote(page: Page, branchId: string) {
  await page.getByTestId('promote-id').fill(branchId)
  await page.getByTestId('promote-name').fill(`E2E branch ${branchId}`)
  await page.getByTestId('promote-submit').click()
}

async function getScenario(page: Page, id: string) {
  return page.evaluate(async (scenarioId) => {
    const response = await fetch(`/api/v1/scenarios/${scenarioId}`)
    const body = await response.json().catch(() => null)
    return { status: response.status, body }
  }, id)
}

test('G5-01: the studio opens with scope, hard limits and the bundled library', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-01-studio')
  await openStudio(page)
  await waitForLibrary(page)

  await expect(page.getByTestId('library-notice')).toContainText('DEMO_INTERVENTIONS_NOT_ENGINEERED')
  await expect(page.getByTestId('limit-max-interventions')).toBeVisible()
  await expect(page.getByTestId('limit-max-candidates')).toBeVisible()
  await expect(page.getByTestId('run-search')).toBeEnabled()
})

test('G5-02: library eligibility comes from the backend, with reasons for exclusions', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-02-library')
  await openStudio(page)
  await waitForLibrary(page)

  await expect(page.getByTestId('intervention-table').locator('tbody tr')).toHaveCount(5)
  await expect(page.getByTestId('library-panel')).toContainText('Applicable items: 4 of 5')
  const reopen = page.getByTestId(`intervention-row-${REOPEN}`)
  await expect(reopen).toContainText('Not applicable')
  await expect(reopen).toContainText('not applicable to')
})

test('G5-03: costs are shown as declared and an absent price is never estimated', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-03-costs')
  await openStudio(page)
  await waitForLibrary(page)

  const backlane = page.getByTestId(`intervention-row-${BACKLANE}`)
  await expect(backlane).toContainText('Not estimated')
  const curb = page.getByTestId(`intervention-row-${CURB}`)
  await expect(curb).toContainText('18,000')
  await expect(curb).toContainText('demo_only')
})

test('G5-04: a bounded search runs against the real engine and states its limits', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-04-search')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  await expect(page.getByTestId('search-status')).toContainText('Optimal in the enumerated domain')
  await expect(page.getByTestId('exhaustive-chip')).toHaveText('Domain exhausted')
  await expect(page.getByTestId('limits-used')).toContainText('max 2 interventions')
  await expect(page.getByTestId('limits-used')).toContainText('no budget')
  await expect(page.getByTestId('result-mode')).toHaveText('Fresh search')
})

test('G5-05: the top candidate is the model-certified curb intervention for both profiles', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-05-rank1')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const rank1 = page.getByTestId('candidate-table').locator('tbody tr').first()
  await expect(rank1).toHaveAttribute('data-intervention-ids', CURB)
  await expect(rank1).toContainText('Model-certified')
  await expect(rank1).toContainText(E_LIB)
  await expect(rank1).toContainText(W_LIB)
  await expect(page.getByTestId('best-proposal')).toContainText('cand-')
})

test('G5-06: a candidate that fails a hard model check is rejected with its reasons', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-06-rejected')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const bypass = candidateRow(page, BYPASS)
  await expect(bypass).toContainText('Rejected')
  await expect(bypass).toContainText('new hard model-FAIL')
})

test('G5-07: an intervention that cannot resolve the unknown is needs-verification, not certified', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-07-verify')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const backlane = candidateRow(page, BACKLANE)
  await expect(backlane).toContainText('Needs verification')
  await expect(backlane).toContainText('Not estimated')
})

test('G5-08: candidate detail shows real per-profile transitions, before and after', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-08-detail')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)

  const detail = page.getByTestId('candidate-detail')
  await expect(detail).toContainText('Restored')
  await expect(detail).toContainText('18.0 m')
  await expect(detail).toContainText('Not comparable')
  await expect(page.getByTestId('transition-table')).toContainText('DEMO_PROFILE_MANUAL_WHEELCHAIR')
})

test('G5-09: modelled values are flagged for field verification, never presented as verified', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-09-assumptions')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)

  const assumptions = page.getByTestId('assumptions')
  await expect(assumptions).toContainText('N_EK')
  await expect(assumptions).toContainText('curb_transition')
  await expect(assumptions).toContainText('Field verification required')
})

test('G5-10: stored searches replay from their persisted payload', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-10-replay')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const bestBefore = await page.getByTestId('best-proposal').innerText()
  const history = page.getByTestId('search-history')
  await expect(history.locator('tbody tr')).toHaveCount(1, { timeout: 20_000 })
  await history.getByRole('button', { name: 'Replay' }).first().click()

  await expect(page.getByTestId('result-mode')).toHaveText('Stored payload replay')
  await expect(page.getByTestId('best-proposal')).toHaveText(bestBefore)
})

test('G5-11: two identical searches order the same candidate first', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-11-determinism')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const firstRun = await page
    .getByTestId('candidate-table')
    .locator('tbody tr')
    .first()
    .getAttribute('data-testid')
  await runSearch(page)
  const secondRun = await page
    .getByTestId('candidate-table')
    .locator('tbody tr')
    .first()
    .getAttribute('data-testid')
  expect(secondRun).toBe(firstRun)
})

test('G5-12: a zero budget refuses every candidate instead of pretending to fit', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-12-budget-zero')
  await openStudio(page)
  await waitForLibrary(page)
  await page.getByTestId('budget-toggle').check()
  await page.getByTestId('budget-amount').fill('0')
  await runSearch(page)

  await expect(page.getByTestId('search-status')).toContainText(
    'No feasible candidate in the enumerated domain',
  )
  await selectCandidate(page, CURB)
  await expect(page.getByTestId('rejection-reasons')).toContainText('budget')
  await expect(page.getByTestId('rejection-reasons')).toContainText('exceeds the budget')
})

test('G5-13: a budget in another currency is refused, never silently converted', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-13-currency')
  await openStudio(page)
  await waitForLibrary(page)
  await page.getByTestId('budget-toggle').check()
  await page.getByTestId('budget-amount').fill('100000')
  await page.getByTestId('budget-currency').fill('USD')
  await page.getByTestId('run-search').click()

  await expect(page.getByText('Search failed')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('INVALID_BUDGET_CURRENCY')).toBeVisible()
  await expect(page.getByText(/does not match any declared demo cost currency/)).toBeVisible()
})

test('G5-14: excluding an intervention shrinks the domain and re-ranks honestly', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-14-exclude')
  await openStudio(page)
  await waitForLibrary(page)
  await page.getByLabel(`Include ${CURB} in the search domain`).uncheck()
  await expect(page.getByTestId('excluded-count')).toContainText(CURB)
  await runSearch(page)

  await expect(page.getByTestId('domain-stats')).toContainText('Eligible: 3')
  await expect(page.getByTestId('domain-excluded')).toContainText(
    'excluded from this search by the request',
  )
  const rank1 = page.getByTestId('candidate-table').locator('tbody tr').first()
  await expect(rank1).toContainText(REMEASURE)
  await expect(rank1).toContainText(W_LIB)
})

test('G5-15: applying a certified candidate creates a branch and re-verifies it', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-15-promote')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)
  await promote(page, 'scn-g5-15-branch')

  const result = page.getByTestId('promotion-result')
  await expect(result).toBeVisible({ timeout: 30_000 })
  await expect(result).toContainText('scn-g5-15-branch')
  await expect(result).toContainText('Reproduces preview')
  await expect(result).toContainText('Yes (revision and hash identical)')
  await expect(result).toContainText('single-phase improvement is not whole-project continuity')
})

test('G5-16: the promoted branch can be opened like any other scenario', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-16-open')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)
  await promote(page, 'scn-g5-16-branch')
  await expect(page.getByTestId('promotion-result')).toBeVisible({ timeout: 30_000 })

  await page.getByTestId('open-branch').click()
  await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByTestId('context-scenario')).toContainText('scn-g5-16-branch')
})

test('G5-17: on the branch, the applied intervention is no longer eligible (its field is known)', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-17-known')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)
  await promote(page, 'scn-g5-17-branch')
  await expect(page.getByTestId('promotion-result')).toBeVisible({ timeout: 30_000 })

  await page.getByTestId('open-branch').click()
  await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
  await openStudio(page)
  await waitForLibrary(page)
  const curb = page.getByTestId(`intervention-row-${CURB}`)
  await expect(curb).toContainText('Not applicable', { timeout: 20_000 })
  await expect(curb).toContainText('known=True')
})

test('G5-18: promotion refuses a stale revision instead of applying it', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-18-stale')

  // A concurrent editor moves the scenario to revision 2; this browser still
  // believes revision 1 and keeps its optimistic revision in the form.
  const patched = await page.evaluate(async (scenarioId) => {
    const response = await fetch(`/api/v1/scenarios/${scenarioId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expected_revision: 1,
        edits: [{ op: 'close_edge', target_id: 'E_ES1', params: { phases: ['phase-1'] } }],
        note: 'G5-18 concurrent edit',
      }),
    })
    return response.status
  }, 'scn-g5-18-stale')
  expect(patched).toBe(200)

  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await page.getByTestId('candidate-table').locator('tbody tr').first().click()
  await expect(page.getByTestId('candidate-detail')).toBeVisible()
  await promote(page, 'scn-g5-18-refused')

  await expect(page.getByText('Promotion refused')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('STALE_REVISION')).toBeVisible()
})

test('G5-19: a taken branch id is refused with an explicit conflict', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-19-duplicate')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)
  await promote(page, 'scn-g5-19-branch')
  await expect(page.getByTestId('promotion-result')).toBeVisible({ timeout: 30_000 })

  await page.getByTestId('promote-submit').click()
  await expect(page.getByText('Promotion refused')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('SCENARIO_ID_EXISTS')).toBeVisible()
})

test('G5-20: a rejected candidate cannot be applied, and nothing is written', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-20-reject')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, BYPASS)
  await promote(page, 'scn-g5-20-rejected')

  await expect(page.getByText('Promotion refused')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('CANDIDATE_REJECTED')).toBeVisible()
  const branch = await getScenario(page, 'scn-g5-20-rejected')
  expect(branch.status).toBe(404)
})

test('G5-21: candidates are selectable with the keyboard', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-21-keyboard')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  const first = page.getByTestId('candidate-table').locator('tbody tr').first()
  const testId = await first.getAttribute('data-testid')
  expect(testId).toBeTruthy()
  const proposalId = (testId as string).replace('candidate-row-', '')
  await first.focus()
  await first.press('Enter')

  await expect(page.getByTestId('candidate-detail')).toBeVisible()
  await expect(page.getByTestId('proposal-id')).toHaveText(proposalId)
  await expect(first).toHaveAttribute('aria-selected', 'true')
})

test('G5-22: a truncated search says so and never claims optimality', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-22-truncated')
  await openStudio(page)
  await waitForLibrary(page)
  await page.getByTestId('limit-max-candidates').fill('2')
  await runSearch(page)

  await expect(page.getByTestId('search-status')).toContainText('limit hit: candidate_limit')
  await expect(page.getByTestId('exhaustive-chip')).toHaveText('Domain not exhausted')
  await expect(page.getByTestId('candidate-table').locator('tbody tr')).toHaveCount(2)
  await expect(
    page.getByTestId('candidate-table').locator('tbody tr').first(),
  ).toContainText('Feasible, not proven optimal')
})

test('G5-23: ranking is monetary-free by default and says which policy ran', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-23-money-free')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)

  await expect(page.getByText('Off (default)')).toBeVisible()
  await expect(page.getByText('DETOUR_LAB_LEXICOGRAPHIC_V1')).toBeVisible()
  await expect(page.getByTestId('limits-used')).toContainText('no budget')
})

test('G5-24: promotion never mutates the source scenario', async ({ page }) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-24-immutable')
  const before = await getScenario(page, 'scn-g5-24-immutable')
  expect(before.status).toBe(200)

  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  await selectCandidate(page, CURB)
  await promote(page, 'scn-g5-24-branch')
  await expect(page.getByTestId('promotion-result')).toBeVisible({ timeout: 30_000 })

  const after = await getScenario(page, 'scn-g5-24-immutable')
  expect(after.body.revision).toBe(before.body.revision)
  expect(after.body.content_hash).toBe(before.body.content_hash)

  const branch = await getScenario(page, 'scn-g5-24-branch')
  expect(branch.status).toBe(200)
  expect(branch.body.parent_scenario_id).toBe('scn-g5-24-immutable')
  expect(branch.body.revision).toBe(1)
  expect(branch.body.intervention_ids).toContain(CURB)
})

test('G5-25: a search survived by the server is replayable after leaving the view', async ({
  page,
}) => {
  await gotoProjects(page)
  await useIsolatedScenario(page, 'scn-g5-25-persistence')
  await openStudio(page)
  await waitForLibrary(page)
  await runSearch(page)
  const firstRun = await page
    .getByTestId('candidate-table')
    .locator('tbody tr')
    .first()
    .getAttribute('data-testid')

  await page.getByTestId('nav-projects').click()
  await expect(page.getByTestId('project-table')).toBeVisible({ timeout: 20_000 })
  await openStudio(page)
  await expect(page.getByText('Nothing searched yet')).toBeVisible({ timeout: 20_000 })

  const history = page.getByTestId('search-history')
  await expect(history).toBeVisible({ timeout: 20_000 })
  await history.getByRole('button', { name: 'Replay' }).first().click()
  await expect(page.getByTestId('result-mode')).toHaveText('Stored payload replay')
  await expect(page.getByTestId('candidate-table').locator('tbody tr').first()).toHaveAttribute(
    'data-testid',
    firstRun ?? '',
  )
})
