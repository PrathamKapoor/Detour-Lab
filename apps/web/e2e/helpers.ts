import { expect, type Page } from '@playwright/test'

/**
 * Shared helpers for the DETOUR LAB E2E suite.
 *
 * Locators use roles and accessible names rather than CSS selectors wherever the
 * interface offers one, so the tests also prove that the UI is navigable the way
 * a screen-reader or keyboard user navigates it.
 */

export async function gotoProjects(page: Page) {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'DETOUR LAB', level: 1 })).toBeVisible()
  await page.getByTestId('nav-projects').click()
  await expect(page.getByTestId('project-table')).toBeVisible({ timeout: 20_000 })
}

export async function openNetwork(page: Page) {
  await page.getByTestId('nav-network').click()
  await expect(page.getByTestId('graph-canvas')).toBeVisible({ timeout: 20_000 })
}

export async function openScenarioEditor(page: Page) {
  await page.getByTestId('nav-scenario').click()
  await expect(page.getByTestId('scenario-revision')).toBeVisible({ timeout: 20_000 })
}

/**
 * Runs a real analysis and waits for **its** result, not merely for a result.
 *
 * The result table from a previous run stays on screen while the next run is in
 * flight, so waiting only for the table to be visible would read stale results.
 * Waiting for the returned run identity to match the requested profile/phase is
 * what makes a profile switch provably effective.
 */
export async function runAnalysis(page: Page, profileId?: string, phaseId?: string) {
  await page.getByTestId('nav-analysis').click()
  // Wait for the scenario to finish loading rather than racing it.
  await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
  if (profileId) await page.getByTestId('profile-select').selectOption(profileId)
  if (phaseId) await page.getByTestId('phase-select').selectOption(phaseId)

  const runBefore = await page.getByTestId('run-id').count()
    ? await page.getByTestId('run-id').innerText()
    : null

  await page.getByTestId('run-analysis').click()

  await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 30_000 })
  if (profileId) {
    await expect(page.getByTestId('run-profile')).toHaveText(profileId, { timeout: 30_000 })
  }
  if (phaseId) {
    await expect(page.getByTestId('run-phase')).toHaveText(phaseId, { timeout: 30_000 })
  }
  // A fresh execution must produce a new run identity, never reuse the old one.
  await expect
    .poll(async () => (await page.getByTestId('run-id').count()) ? await page.getByTestId('run-id').innerText() : null, {
      timeout: 30_000,
    })
    .not.toBe(runBefore === null ? '' : runBefore)
}

export async function selectEdgeInTable(page: Page, edgeId: string) {
  await page.getByTestId('nav-network').click()
  await page.getByRole('tab', { name: 'Entity table' }).click()
  await page.getByTestId(`edge-row-${edgeId}`).click()
}

/**
 * Creates a scenario through the API whose declared phases are copied from the
 * seed but which carries no edits, then selects it in the UI.
 *
 * Editing specs need this: edits are append-only and immutable, so a test cannot
 * "undo" a closure another test committed. Working on their own scenario makes
 * each test independent of the order the suite runs in.
 */
export async function useIsolatedScenario(page: Page, id: string) {
  const created = await page.evaluate(async (scenarioId) => {
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
        note: 'Isolated working copy created by the end-to-end suite.',
      }),
    })
    return { status: response.status, body: await response.json() }
  }, id)

  if (created.status === 409 || created.status === 422) {
    // Already present from an earlier attempt in the same database: reuse it.
    await page.reload()
  } else if (created.status !== 201) {
    throw new Error(`Could not create the isolated scenario: ${created.status}`)
  }

  await page.reload()
  await page.getByTestId('nav-scenario').click()
  await expect(page.getByTestId('scenario-select')).toBeVisible({ timeout: 20_000 })
  await page.getByTestId('scenario-select').selectOption(id)
  await expect(page.getByTestId('scenario-revision')).toBeVisible({ timeout: 20_000 })
}