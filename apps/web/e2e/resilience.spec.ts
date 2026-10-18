import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { gotoProjects, openNetwork, runAnalysis } from './helpers'

/**
 * E2E-13, 15, 16 — API failure handling, accessibility smoke and responsive smoke.
 *
 * The accessibility test reports automated findings only; a clean axe run is
 * necessary but not sufficient for WCAG conformance, and is never described as
 * such.
 */

test.describe('resilience and accessibility', () => {
  test('E2E-13 an unavailable backend produces a recoverable error, not a blank screen', async ({
    page,
  }) => {
    await gotoProjects(page)
    // Fail every subsequent API call, simulating an unreachable service.
    await page.route('**/api/v1/projects', (route) => route.abort('failed'))
    await page.reload()

    const alerts = page.getByRole('alert')
    await expect(alerts.first()).toBeVisible({ timeout: 20_000 })
    await expect(alerts.first()).toContainText(/Cannot reach the analysis service|Cannot load/i)
    await expect(page.getByRole('button', { name: /Retry/ }).first()).toBeVisible()
    await expect(page.getByText('API unreachable')).toBeVisible()
  })

  test('E2E-15 core pages have no critical automated accessibility violations', async ({ page }) => {
    await gotoProjects(page)
    const projectFindings = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(projectFindings.violations.filter((v) => (v.impact ?? 'none') === 'critical')).toEqual([])

    await openNetwork(page)
    const networkFindings = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(networkFindings.violations.filter((v) => (v.impact ?? 'none') === 'critical')).toEqual([])

    await runAnalysis(page)
    const analysisFindings = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
    expect(analysisFindings.violations.filter((v) => (v.impact ?? 'none') === 'critical')).toEqual([])
  })

  test('E2E-15b the primary journey is operable by keyboard alone', async ({ page }) => {
    await gotoProjects(page)
    // Tab through the header/nav and reach the project workspace without a mouse.
    let reachedNetwork = false
    for (let index = 0; index < 40 && !reachedNetwork; index += 1) {
      await page.keyboard.press('Tab')
      const label = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? '')
      if (label.startsWith('Network')) reachedNetwork = true
    }
    expect(reachedNetwork).toBe(true)
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('graph-canvas')).toBeVisible()

    // The skip link is the first tab stop and targets the main region.
    await page.goto('/')
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: /Skip to main content/ })).toBeFocused()
  })

  test('E2E-15c results are distinguishable without relying on colour', async ({ page }) => {
    await gotoProjects(page)
    await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
    // Every reachability cell states its status in words, so the meaning survives
    // without colour. This holds whatever the current scenario state is, which is
    // why the assertion is per-row rather than about one specific pair.
    const statuses = ['Model-confirmed', 'Possible only', 'No route']
    const rows = await page.getByTestId('od-table').locator('tbody tr').allInnerTexts()
    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      expect(statuses.some((status) => row.includes(status))).toBe(true)
    }

    // The legend names every non-colour encoding used on the canvas.
    await openNetwork(page)
    await page.getByRole('tab', { name: 'Legend' }).click()
    for (const label of [
      'Confirmed route',
      'Possible-only route',
      'Closed for construction',
      'Temporary connection',
      'Geometric crossing, not a connection',
    ]) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }
  })
})