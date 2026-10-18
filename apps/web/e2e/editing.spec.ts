import { expect, test, type Page } from '@playwright/test'
import { gotoProjects, openNetwork, openScenarioEditor, runAnalysis, useIsolatedScenario } from './helpers'

/**
 * E2E-09..12, 14, 18 — closure edits, persistence, before/after comparison,
 * concurrency conflicts, manifest export and invalid edits.
 *
 * Each test works on its own scenario, created through the API from the seeded
 * declared phases with no edits. Scenarios are immutable and append-only, so a
 * shared scenario would make these tests order-dependent; an isolated copy keeps
 * every assertion about real backend state without depending on what ran before.
 */

/** Each test gets its own working scenario so no test can inherit another's edits. */
let workScenario = ''

async function currentRevision(page: Page): Promise<number> {
  return page.evaluate(async (scenarioId) => {
    const response = await fetch(`/api/v1/scenarios/${scenarioId}`)
    const body = await response.json()
    return body.revision as number
  }, workScenario)
}

async function patchViaApi(page: Page, edit: object) {
  return page.evaluate(
    async ({ payload, scenarioId }) => {
      const response = await fetch(`/api/v1/scenarios/${scenarioId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      return { status: response.status, body: await response.json() }
    },
    {
      payload: { expected_revision: await currentRevision(page), edits: [edit], note: 'e2e concurrent editor' },
      scenarioId: workScenario,
    },
  )
}

test.describe('scenario editing', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    const slug = testInfo.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
      .slice(0, 40)
    workScenario = `scn-e2e-${slug}`
    await gotoProjects(page)
    await useIsolatedScenario(page, workScenario)
  })

  test('E2E-09 applying a closure changes the analysis result', async ({ page }) => {
    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    await page.getByTestId('set-baseline').click()
    await expect(page.getByTestId('od-OD-W-OD-LIB')).toContainText('Model-confirmed')

    const revisionBefore = await currentRevision(page)

    await openNetwork(page)
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_WM').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()

    await expect(page.getByTestId('pending-edits')).toContainText('close_edge')
    await expect(page.getByRole('status').first()).toContainText(/Unsaved edits/)

    await page.getByTestId('save-edits').click()
    await expect(page.getByTestId('scenario-revision')).toHaveText(String(revisionBefore + 1))
    await expect(page.getByTestId('pending-edits')).toBeHidden()

    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    await page.getByTestId('nav-compare').click()
    const comparison = page.getByTestId('comparison-table')
    await expect(comparison).toBeVisible()
    await expect(comparison).toContainText('lost')
  })

  test('E2E-10 a saved change survives a reload', async ({ page }) => {
    const revisionBefore = await currentRevision(page)

    await openNetwork(page)
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_LINK').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()
    await page.getByTestId('save-edits').click()
    await expect(page.getByTestId('scenario-revision')).toHaveText(String(revisionBefore + 1))

    await page.reload()
    await openScenarioEditor(page)
    await page.getByTestId('scenario-select').selectOption(workScenario)
    await expect(page.getByTestId('scenario-revision')).toHaveText(String(revisionBefore + 1))
    await expect(page.getByText(/Committed edits/)).toBeVisible()
    await expect(page.getByText('E_LINK')).toBeVisible()
  })

  test('E2E-11 before/after comparison uses two real runs', async ({ page }) => {
    await runAnalysis(page)
    await page.getByTestId('set-baseline').click()
    await openNetwork(page)
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_SSE').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()
    await page.getByTestId('save-edits').click()
    await expect(page.getByTestId('scenario-revision')).toBeVisible()
    await runAnalysis(page)

    await page.getByTestId('nav-compare').click()
    await expect(page.getByText('Comparison context')).toBeVisible()
    await expect(page.getByTestId('comparison-table')).toContainText('OD-W')
    await expect(page.getByText(/Base graph hash/)).toBeVisible()
    await expect(page.getByTestId('edge-diff-table')).toBeVisible()
  })

  test('E2E-12 a stale revision conflict never overwrites newer work', async ({ page }) => {
    // Another editor commits first, advancing the revision.
    const first = await patchViaApi(page, {
      op: 'update_attribute',
      target_id: 'E_WB',
      params: {
        field: 'surface',
        value: 'asphalt',
        unit: null,
        method: 'concurrent_editor',
        source: 'another planner',
        provenance_class: 'assumed',
        synthetic: false,
        observed_at: '2026-02-01T10:00:00Z',
      },
    })
    expect(first.status).toBe(200)

    // A write carrying the now-stale revision is refused, not applied.
    const stale = await page.evaluate(
      async ({ revision, scenarioId }) => {
        const response = await fetch(`/api/v1/scenarios/${scenarioId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_revision: revision,
            edits: [{ op: 'close_edge', target_id: 'E_ES1', params: { phases: ['phase-1'] } }],
          }),
        })
        return { status: response.status, body: await response.json() }
      },
      { revision: first.body.revision - 1, scenarioId: workScenario },
    )

    expect(stale.status).toBe(409)
    expect(stale.body.code).toBe('REVISION_CONFLICT')
    expect(stale.body.details.actual_revision).toBe(first.body.revision)
    // The newer work survived: the revision did not move again.
    expect(await currentRevision(page)).toBe(first.body.revision)
  })

  test('E2E-12b the editor surfaces a conflict instead of overwriting', async ({ page }) => {
    // Reproduce the 409 through the UI's own save path.
    await openNetwork(page)
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_ALT').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()

    // Another editor commits while the draft is open.
    await patchViaApi(page, {
      op: 'update_attribute',
      target_id: 'E_BS1',
      params: {
        field: 'surface',
        value: 'asphalt',
        unit: null,
        method: 'concurrent_editor',
        source: 'another planner',
        provenance_class: 'assumed',
        synthetic: false,
        observed_at: '2026-02-01T10:00:00Z',
      },
    })

    await page.getByTestId('save-edits').click()
    await expect(page.getByRole('alert')).toContainText(/changed since you loaded it/i)
    await expect(page.getByRole('button', { name: /Reload server state/ })).toBeVisible()
    // The draft edit is still listed, so nothing is silently discarded.
    await expect(page.getByTestId('pending-edits')).toContainText('E_ALT')
  })

  test('E2E-14 the canonical manifest is retrieved from the backend and downloadable', async ({ page }) => {
    await runAnalysis(page)
    await page.getByTestId('nav-reports').click()

    await expect(page.getByTestId('manifest-hash')).toBeVisible()
    await expect(page.getByText('Planning analysis — not certified').first()).toBeVisible()
    await expect(page.getByText('DEMO_RULEPACK_NOT_LEGAL').first()).toBeVisible()
    await expect(page.getByText('unverified').first()).toBeVisible()

    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: /Download JSON/ }).click()
    const file = await download
    expect(file.suggestedFilename()).toMatch(/^detour-lab-manifest-[0-9a-f]{12}\.json$/)
    await expect(page.getByTestId('download-notice')).toBeVisible()
  })

  test('E2E-18 an invalid edit is rejected and does not become a saved revision', async ({ page }) => {
    const before = await currentRevision(page)

    const result = await page.evaluate(
      async ({ revision, scenarioId }) => {
        const response = await fetch(`/api/v1/scenarios/${scenarioId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_revision: revision,
            edits: [{ op: 'add_edge', target_id: 'E_BAD', params: { id: 'E_BAD', u: 'N_W', v: 'N_GHOST' } }],
          }),
        })
        return response.status
      },
      { revision: before, scenarioId: workScenario },
    )

    expect(result).toBe(422)
    expect(await currentRevision(page)).toBe(before)
  })
})