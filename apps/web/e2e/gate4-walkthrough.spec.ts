import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page } from '@playwright/test'
import { gotoProjects, openScenarioEditor } from './helpers'

/**
 * Gate 4 browser walkthrough with screenshots and a clean-console assertion.
 *
 * This is the manual-review evidence: the phase explorer, the continuity matrix
 * and the branch explorer are inspected as rendered, not only as source.
 */
const SHOTS = fileURLToPath(new URL('../../../var/screenshots/', import.meta.url))

async function openPhases(page: Page) {
  await page.getByTestId('nav-phases').click()
  await expect(page.getByTestId('phase-rail')).toBeVisible({ timeout: 20_000 })
}

test('Gate 4 walkthrough: timeline, phase graph, continuity, findings, branching', async ({ page }) => {
  mkdirSync(SHOTS, { recursive: true })
  const problems: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console.error: ${message.text()}`)
  })
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))

  await gotoProjects(page)
  await openPhases(page)
  await page.screenshot({ path: `${SHOTS}10-phase-timeline.png`, fullPage: true })

  // Select the second phase and confirm the graph really changed.
  await page.getByTestId('phase-marker-phase-2').click()
  await expect(page.locator('.graph-edge--temporary')).toHaveCount(1)
  await page.screenshot({ path: `${SHOTS}11-phase-2-graph.png`, fullPage: true })

  // Evaluate the whole sequence.
  await page.getByTestId('evaluate-all-phases').click()
  await expect(page.getByTestId('continuity-matrix')).toBeVisible({ timeout: 40_000 })
  // The shell scrolls internally, so capture the matrix itself, not just the viewport.
  await page.getByTestId('continuity-matrix').scrollIntoViewIfNeeded()
  await page.getByTestId('continuity-matrix').screenshot({ path: `${SHOTS}12-continuity-matrix.png` })
  await page.screenshot({ path: `${SHOTS}12b-phases-top.png`, fullPage: true })

  await expect(page.getByTestId('impact-table')).toBeVisible()
  await page.getByTestId('impact-table').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}13-temporal-findings.png` })

  // Branching.
  await page.getByTestId('nav-branches').click();
  await expect(page.getByTestId('branch-table')).toBeVisible({ timeout: 20_000 })
  await page.getByTestId('create-branch').click()
  await page.getByLabel('Branch id').fill('scn-demo-alt')
  await page.getByLabel('Branch name').fill('Alternative plan B')
  await page.getByTestId('confirm-branch').click()
  await expect(page.getByTestId('branch-row-scn-demo-alt')).toBeVisible({ timeout: 20_000 })
  await page.screenshot({ path: `${SHOTS}14-branches.png`, fullPage: true })

  // The branch is a real scenario with its own phases.
  await openScenarioEditor(page)
  await expect(page.getByTestId('scenario-revision')).toHaveText('1')
  await openPhases(page)
  await expect(page.getByTestId('phase-rail').locator('li')).toHaveCount(2)

  expect(problems, 'browser reported problems during the Gate 4 walkthrough').toEqual([])
})