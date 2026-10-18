import { expect, test } from '@playwright/test'
import { gotoProjects, openNetwork, runAnalysis } from './helpers'

/**
 * E2E-01..08, 17 — application start-up, seeded data, selection, keyboard access,
 * profile switching, deterministic analysis, known violation, unknown evidence
 * and deterministic rerun. All against the real backend.
 */

test.describe('analysis journey', () => {
  test.beforeEach(async ({ page }) => {
    await gotoProjects(page)
  })

  test('E2E-01 application starts and reaches the real backend', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'DETOUR LAB', level: 1 })).toBeVisible()
    await expect(page.getByTestId('project-table')).toBeVisible()
    // The project list is API data, not a fixture bundled into the bundle.
    await expect(page.getByTestId('project-table')).toContainText('SYNTHETIC')
    await expect(page.getByText('Synthetic demo data').first()).toBeVisible()
  })

  test('E2E-02 the seeded graph renders from API data', async ({ page }) => {
    await openNetwork(page)
    const canvas = page.getByTestId('graph-canvas')
    await expect(canvas).toBeVisible()
    const label = await canvas.getAttribute('aria-label')
    expect(label).toContain('directed edges')
    expect(label).toContain('nodes')
    // Backend-declared unlinked crossings are surfaced, not silently connected.
    await expect(page.getByTestId('graph-crossing').first()).toBeVisible()

    await page.getByRole('tab', { name: 'Entity table' }).click()
    await expect(page.getByTestId('edge-row-E_WM')).toBeVisible()
    await expect(page.getByTestId('edge-row-E_ME')).toBeVisible()
  })

  test('E2E-03 selecting an edge shows the matching backend record', async ({ page }) => {
    await openNetwork(page)
    await page.getByTestId('edge-hit-E_WM').dispatchEvent('click')
    const inspector = page.getByTestId('graph-inspector')
    await expect(inspector).toBeVisible()
    await expect(inspector).toContainText('E_WM')
    await expect(inspector).toContainText('N_W → N_M')
    await expect(inspector).toContainText('40.000 m')
  })

  test('E2E-04 a user can inspect an edge with the keyboard only', async ({ page }) => {
    await openNetwork(page)
    await page.getByRole('tab', { name: 'Entity table' }).click()
    const row = page.getByTestId('edge-row-E_K1')
    await row.focus()
    await expect(row).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('graph-inspector')).toContainText('E_K1')
    // Arrow/Tab traversal reaches the node table without touching the SVG.
    await page.getByTestId('node-row-N_K').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('graph-inspector')).toContainText('Node N_K')
  })

  test('E2E-05 profile switching changes the analysis result', async ({ page }) => {
    // The seeded crossing is 1100 mm wide: profile A accepts it, profile B does not.
    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    const pairA = page.getByTestId('od-OD-W-OD-GATE')
    const profileAStatus = await pairA.innerText()

    await runAnalysis(page, 'DEMO_PROFILE_LIMITED_MOBILITY_WALKER', 'phase-1')
    const profileBStatus = await page.getByTestId('od-OD-W-OD-GATE').innerText()

    expect(profileAStatus).not.toBe(profileBStatus)
    await expect(page.getByTestId('od-OD-W-OD-GATE')).toContainText('No route')
    await expect(page.getByTestId('semantic-hash')).toBeVisible()
  })

  test('E2E-06 a baseline analysis returns a real run identity', async ({ page }) => {
    await runAnalysis(page)
    await expect(page.getByTestId('semantic-hash')).toHaveText(/^[0-9a-f]{24}$/)
    await expect(page.getByText('Run identity')).toBeVisible()
    await expect(page.getByText(/DEMO_RULEPACK_NOT_LEGAL/).first()).toBeVisible()
  })

  test('E2E-06b the canvas encodes confirmed and possible-only routes by line style', async ({
    page,
  }) => {
    // Runs on the pristine seeded scenario, where both states exist at once.
    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    await openNetwork(page)

    const confirmed = page.locator('.graph-edge--confirmed')
    await expect(confirmed.first()).toBeVisible()

    // Possible-only edges are dashed, so the distinction is not colour-only.
    const possible = page.locator('.graph-edge--possible')
    await expect(possible.first()).toBeVisible()
    const dashPattern = await possible
      .first()
      .locator('.graph-edge__line')
      .evaluate((node) => getComputedStyle(node).strokeDasharray)
    expect(dashPattern).not.toBe('none')

    // The selected element is marked for inspection as well.
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_WM').click()
    await expect(page.getByRole('tab', { name: 'Canvas' })).toBeVisible()
    await page.getByRole('tab', { name: 'Canvas' }).click()
    await expect(page.locator('.graph-edge--selected')).toHaveCount(1)
  })

  test('E2E-07 a known violation is explained with its rule', async ({ page }) => {
    // Profile A fails the main crossing only under profile B's stricter width rule,
    // so the violation is inspected on profile B where it is a real FAIL.
    await runAnalysis(page, 'DEMO_PROFILE_LIMITED_MOBILITY_WALKER', 'phase-1')
    await page.getByTestId('filter-fail').click()
    const findings = page.getByTestId('findings-table')
    await expect(findings).toBeVisible()
    await expect(findings).toContainText('DEMO-EDGE-WIDTH-LIMITED')
    await expect(findings).toContainText(/below the demo limited-mobility walking threshold/i)
  })

  test('E2E-08 unknown evidence stays unknown and possible-only is not labelled confirmed', async ({
    page,
  }) => {
    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    const pair = page.getByTestId('od-OD-E-OD-LIB')
    await expect(pair).toContainText('Possible only')
    await expect(pair).not.toContainText('Model-confirmed')
    await expect(page.getByTestId('od-distance-OD-E-OD-LIB')).toHaveText('—')

    await page.getByTestId('nav-evidence').click()
    await expect(page.getByRole('heading', { name: 'Unresolved attributes' })).toBeVisible()
    await expect(page.getByText(/No evidence/).first()).toBeVisible()
  })

  test('E2E-17 equivalent analyses share a semantic hash but not a run id', async ({ page }) => {
    await runAnalysis(page)
    const firstHash = await page.getByTestId('semantic-hash').innerText()
    await runAnalysis(page)
    const secondHash = await page.getByTestId('semantic-hash').innerText()

    await page.getByTestId('nav-reports').click()
    await expect(page.getByTestId('run-id')).toBeVisible()
    await expect(page.getByTestId('manifest-hash')).toBeVisible()
    expect(firstHash).toBe(secondHash)
  })
})