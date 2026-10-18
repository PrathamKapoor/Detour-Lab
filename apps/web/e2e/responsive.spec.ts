import { expect, test } from '@playwright/test'
import { gotoProjects, openNetwork, runAnalysis } from './helpers'

/**
 * E2E-16 — the primary journey on a small viewport.
 *
 * Runs in the `mobile` Playwright project (Pixel 7) as well as on desktop, so the
 * layout is exercised at both ends.
 */
test('E2E-16 the primary journey works at a small viewport', async ({ page }) => {
  const overflow = () =>
    page.evaluate(() => {
      const docWidth = document.documentElement.clientWidth
      const offenders: string[] = []
      for (const element of Array.from(document.querySelectorAll('*'))) {
        const rect = element.getBoundingClientRect()
        if (rect.width > docWidth + 1) {
          offenders.push(
            `${element.tagName}.${(element.className || '').toString().split(' ')[0]}=${Math.round(rect.width)}`,
          )
        }
      }
      return { difference: document.documentElement.scrollWidth - docWidth, offenders: offenders.slice(0, 6) }
    })

  await gotoProjects(page)
  await expect(page.getByTestId('project-table')).toBeVisible()
  const projects = await overflow()
  expect(projects.difference, JSON.stringify(projects.offenders)).toBeLessThanOrEqual(1)

  await openNetwork(page)
  await expect(page.getByTestId('graph-canvas')).toBeVisible()
  const canvasBox = await page.getByTestId('graph-canvas').boundingBox()
  expect(canvasBox?.width ?? 0).toBeGreaterThan(150)
  const network = await overflow()
  expect(network.difference, JSON.stringify(network.offenders)).toBeLessThanOrEqual(1)

  await runAnalysis(page)
  await expect(page.getByTestId('od-table')).toBeVisible()
  const analysis = await overflow()
  expect(analysis.difference, JSON.stringify(analysis.offenders)).toBeLessThanOrEqual(1)
})

test('responsive: the entity table remains usable on a small viewport', async ({ page }) => {
  await gotoProjects(page)
  await openNetwork(page)
  await page.getByRole('tab', { name: 'Entity table' }).click()
  await expect(page.getByTestId('edge-row-E_WM')).toBeVisible()
  await page.getByTestId('edge-row-E_WM').click()
  await expect(page.getByTestId('graph-inspector')).toContainText('E_WM')
})