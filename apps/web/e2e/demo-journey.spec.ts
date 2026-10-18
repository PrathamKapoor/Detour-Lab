import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type ConsoleMessage, type Page } from '@playwright/test'
import { gotoProjects, openNetwork, openScenarioEditor, runAnalysis } from './helpers'

/**
 * The documented offline demo journey (Gate 3, section 8), executed end to end
 * against the real backend, with screenshots kept as review evidence.
 *
 * It also fails on any console error, page error or failed request that the
 * journey itself did not cause, so "the screen rendered" cannot hide a broken
 * client.
 */
const SHOTS = fileURLToPath(new URL('../../../var/screenshots/', import.meta.url))

function watchConsole(page: Page): { problems: string[]; assertClean: () => void } {
  const problems: string[] = []
  page.on('console', (message: ConsoleMessage) => {
    if (message.type() === 'error') problems.push(`console.error: ${message.text()}`)
    if (message.type() === 'warning' && /React|act\(|key|validateDOMNesting/i.test(message.text())) {
      problems.push(`console.warn: ${message.text()}`)
    }
  })
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
  page.on('requestfailed', (request) => {
    const failure = request.failure()?.errorText ?? 'unknown'
    if (failure.includes('ERR_ABORTED')) return // deliberate cancellation
    problems.push(`requestfailed: ${request.url()} (${failure})`)
  })
  return {
    problems,
    assertClean: () => expect(problems, 'browser reported problems during the journey').toEqual([]),
  }
}

test('demo journey: seed, inspect, close, analyse, compare, save, reload, export', async ({ page }) => {
  mkdirSync(SHOTS, { recursive: true })
  const console_ = watchConsole(page)

  // 3-4. Open the seeded project and show the local-planar network.
  await gotoProjects(page)
  await page.screenshot({ path: `${SHOTS}01-projects.png`, fullPage: true })
  await openNetwork(page)
  await page.screenshot({ path: `${SHOTS}02-network.png`, fullPage: true })

  // 5. Inspect an edge and its evidence.
  await page.getByRole('tab', { name: 'Entity table' }).click()
  await page.getByTestId('edge-row-E_K1').click()
  await expect(page.getByTestId('graph-inspector')).toContainText('E_K1')
  await page.screenshot({ path: `${SHOTS}03-inspector.png`, fullPage: true })

  // 6. Baseline analysis.
  await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
  await page.screenshot({ path: `${SHOTS}04-baseline-analysis.png`, fullPage: true })
  await page.getByTestId('set-baseline').click()

  // 7. Add a supported closure and save it through the backend.
  await openNetwork(page)
  await page.getByRole('tab', { name: 'Entity table' }).click()
  await page.getByTestId('edge-row-E_WM').click()
  await openScenarioEditor(page)
  await page.getByRole('button', { name: /Close selected edge/ }).click()
  await expect(page.getByTestId('pending-edits')).toContainText('close_edge')
  await page.getByTestId('save-edits').click()
  await expect(page.getByTestId('scenario-revision')).toHaveText('2')
  await page.screenshot({ path: `${SHOTS}05-closure-saved.png`, fullPage: true })

  // 8-9. Re-analyse and show the changed reachability.
  await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
  await page.screenshot({ path: `${SHOTS}06-reanalysis.png`, fullPage: true })

  // 10. Inspect a failure and an unknown condition.
  await page.getByTestId('filter-unknown').click()
  await expect(page.getByTestId('findings-table')).toBeVisible()
  await page.getByTestId('nav-evidence').click()
  await page.screenshot({ path: `${SHOTS}07-evidence.png`, fullPage: true })

  // 11. Compare before and after.
  await page.getByTestId('nav-compare').click()
  await expect(page.getByTestId('comparison-table')).toContainText('lost')
  await page.screenshot({ path: `${SHOTS}08-comparison.png`, fullPage: true })

  // 12-13. Reload and confirm the saved change is still there.
  await page.reload()
  await openScenarioEditor(page)
  await expect(page.getByTestId('scenario-revision')).toHaveText('2')
  await expect(page.getByText('E_WM')).toBeVisible()

  // 14. Export the canonical manifest.
  await runAnalysis(page, 'DEMO_PROFILE_MANUAL_WHEELCHAIR', 'phase-1')
  await page.getByTestId('nav-reports').click()
  await expect(page.getByTestId('manifest-hash')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /Download JSON/ }).click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/^detour-lab-manifest-[0-9a-f]{12}\.json$/)
  await page.screenshot({ path: `${SHOTS}09-manifest.png`, fullPage: true })

  console_.assertClean()
})