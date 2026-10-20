import { expect, test } from '@playwright/test'
import { gotoProjects, openNetwork, runAnalysis } from './helpers'

/**
 * Gate 7 Final Release Candidate E2E Verification Suite.
 *
 * Verifies:
 * 1. Multi-viewport responsiveness across 4 viewports (1440x900, 1280x800, 768x1024, 390x844).
 * 2. Complete absence of horizontal overflow across all major views.
 * 3. Offline self-containment (zero external third-party network requests).
 * 4. Keyboard navigation and accessibility landmark semantics.
 * 5. Safe escaping of script tags and malicious markup strings.
 */

const VIEWPORTS = [
  { name: 'Desktop (1440x900)', width: 1440, height: 900 },
  { name: 'Laptop (1280x800)', width: 1280, height: 800 },
  { name: 'Tablet (768x1024)', width: 768, height: 1024 },
  { name: 'Mobile (390x844)', width: 390, height: 844 },
]

for (const vp of VIEWPORTS) {
  test(`Gate 7 Viewport: ${vp.name} renders without layout breakage or overflow`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height })

    const checkOverflow = () =>
      page.evaluate(() => {
        const docWidth = document.documentElement.clientWidth
        return document.documentElement.scrollWidth - docWidth
      })

    // 1. Projects screen
    await gotoProjects(page)
    await expect(page.getByTestId('project-table')).toBeVisible()
    const projOverflow = await checkOverflow()
    expect(projOverflow, `Overflow on Projects at ${vp.name}`).toBeLessThanOrEqual(1)

    // 2. Network view
    await openNetwork(page)
    await expect(page.getByTestId('graph-canvas')).toBeVisible()
    const netOverflow = await checkOverflow()
    expect(netOverflow, `Overflow on Network at ${vp.name}`).toBeLessThanOrEqual(1)

    // 3. Analysis view
    await runAnalysis(page)
    await expect(page.getByTestId('od-table')).toBeVisible()
    const anaOverflow = await checkOverflow()
    expect(anaOverflow, `Overflow on Analysis at ${vp.name}`).toBeLessThanOrEqual(1)
  })
}

test('Gate 7 Security: Offline Self-Containment (B31)', async ({ page }) => {
  const externalRequests: string[] = []

  page.on('request', (request) => {
    const url = new URL(request.url())
    // Allow local origin requests
    if (url.hostname !== 'localhost' && url.hostname !== '127.0.0.1') {
      externalRequests.push(request.url())
    }
  })

  await gotoProjects(page)
  await openNetwork(page)
  await runAnalysis(page)

  expect(
    externalRequests,
    `Application must run 100% offline; detected external network calls: ${externalRequests.join(', ')}`,
  ).toEqual([])
})

test('Gate 7 Accessibility: Keyboard Navigation and Landmarks', async ({ page }) => {
  await page.goto('/')

  // Verify semantic landmarks and header
  await expect(page.getByRole('banner')).toBeVisible()
  await expect(page.getByRole('navigation')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'DETOUR LAB', level: 1 })).toBeVisible()

  // Verify Tab key navigates through top nav links
  await page.keyboard.press('Tab')
  const activeTag = await page.evaluate(() => document.activeElement?.tagName)
  expect(['A', 'BUTTON']).toContain(activeTag)

  // Verify Branding / Purpose tag is clearly visible
  await expect(page.getByText('Pedestrian detour planning & model verification')).toBeVisible()
})

test('Gate 7 Security: Escapes Malicious Markup and Script Tags (B30)', async ({ page }) => {
  await page.goto('/')

  const maliciousName = '<script>window.__xss_flag = true</script>MaliciousProject'

  // Submit via API
  const res = await page.evaluate(async (name) => {
    const r = await fetch('/api/v1/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: 'prj-xss-test',
        name: name,
        description: '<img src=x onerror=window.__xss_flag=true>',
      }),
    })
    return r.status
  }, maliciousName)
  expect(res).toBe(201)

  // Navigate to projects table and verify safe rendering
  await gotoProjects(page)
  await expect(page.getByText(maliciousName)).toBeVisible()

  // Confirm script tag was NOT executed in DOM
  const executed = await page.evaluate(() => (window as unknown as { __xss_flag?: boolean }).__xss_flag)
  expect(executed).toBeUndefined()
})
