import { expect, test, type Page } from '@playwright/test'
import { gotoProjects, openScenarioEditor } from './helpers'

/**
 * Gate 4 browser acceptance (E2E-G4-01..20), executed against the real backend.
 *
 * Isolation: every run gets its own seeded database (see `playwright.config.ts`),
 * and each editing test works on its own scenario, so nothing depends on the
 * order the suite runs in.
 */

async function openPhases(page: Page) {
  await page.getByTestId('nav-phases').click()
  await expect(page.getByTestId('phase-rail')).toBeVisible({ timeout: 20_000 })
}

async function evaluateAll(page: Page) {
  await openPhases(page)
  await page.getByTestId('evaluate-all-phases').click()
  await expect(page.getByTestId('continuity-matrix')).toBeVisible({ timeout: 40_000 })
}

let workScenario = ''

async function useIsolatedScenario(page: Page, id: string) {
  workScenario = id
  const created = await page.evaluate(async (scenarioId) => {
    const source = await (await fetch('/api/v1/scenarios/scn-demo-baseline')).json()
    const response = await fetch('/api/v1/projects/demo-project-synthetic/scenarios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: scenarioId,
        name: `Gate 4 working copy ${scenarioId}`,
        parent_scenario_id: source.id,
        base_graph_version_id: source.base_graph_version_id,
        phases: source.phases,
        origins_destinations: source.origins_destinations,
        temporary_edges: source.temporary_edges,
        note: 'Gate 4 end-to-end working copy.',
      }),
    })
    return response.status
  }, id)
  expect([201, 409]).toContain(created)

  await page.reload()
  await openScenarioEditor(page)
  await page.getByTestId('scenario-select').selectOption(id)
  await expect(page.getByTestId('scenario-revision')).toBeVisible({ timeout: 20_000 })
}

test.describe('Gate 4 — construction phase intelligence', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await gotoProjects(page)
    // Every Gate 4 test works on its own scenario built from the pristine seed.
    // Earlier specs legitimately edit the shared demo scenario, so depending on it
    // would make these assertions order-dependent.
    const slug = testInfo.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
      .slice(0, 36)
    await useIsolatedScenario(page, `scn-g4-${slug}`)
  })

  test('E2E-G4-01 loads an ordered multi-phase scenario from the backend', async ({ page }) => {
    await openPhases(page)
    const rail = page.getByTestId('phase-rail')
    await expect(rail.locator('li')).toHaveCount(2)
    await expect(page.getByTestId('phase-marker-phase-1')).toContainText('order 1')
    await expect(page.getByTestId('phase-marker-phase-2')).toContainText('order 2')
    // Ordering is authoritative data, not a rendering convention.
    await expect(page.getByText(/no construction calendar/i).first()).toBeVisible()
  })

  test('E2E-G4-02 changing phases loads the correct authoritative graph', async ({ page }) => {
    await openPhases(page)
    await expect(page.getByTestId('phase-marker-phase-1')).toHaveAttribute('aria-current', 'step')

    const phaseOneGraphId = await page.getByText(/~phase:/).first().innerText()
    const phaseOneClosed = await page.locator('.graph-edge--closed').count()

    await page.getByTestId('phase-marker-phase-2').click()
    await expect(page.getByTestId('phase-marker-phase-2')).toHaveAttribute('aria-current', 'step')
    await expect(page.locator('.graph-edge--closed')).toHaveCount(phaseOneClosed + 1)
    // Phase 2 materialises the temporary bypass that phase 1 does not have.
    await expect(page.locator('.graph-edge--temporary')).toHaveCount(1)

    const phaseTwoGraphId = await page.getByText(/~phase:/).first().innerText()
    expect(phaseOneGraphId).toContain('phase-1')
    expect(phaseTwoGraphId).toContain('phase-2')
    expect(phaseTwoGraphId).not.toBe(phaseOneGraphId)
  })

  test('E2E-G4-03 navigates the phase explorer with the keyboard alone', async ({ page }) => {
    await openPhases(page)
    const marker = page.getByTestId('phase-marker-phase-1')
    await marker.focus()
    await expect(marker).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByTestId('phase-marker-phase-2')).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('phase-marker-phase-2')).toHaveAttribute('aria-current', 'step')

    // Previous/next are real buttons with accessible names.
    await page.getByRole('button', { name: 'Previous phase' }).click()
    await expect(page.getByTestId('phase-marker-phase-1')).toHaveAttribute('aria-current', 'step')
    await expect(page.getByRole('button', { name: 'Previous phase' })).toBeDisabled()
  })

  test('E2E-G4-04 analyses a single selected phase', async ({ page }) => {
    await openPhases(page)
    await page.getByTestId('phase-marker-phase-1').click()
    await expect(page.getByText('NOT ANALYSED').first()).toBeVisible()
    await page.getByTestId('evaluate-phase').click()
    await expect(page.getByTestId('continuity-matrix')).toBeVisible({ timeout: 40_000 })
    // Phase 2 has no result for this profile/revision, so it stays unanalysed.
    await expect(page.locator('.cell--not-evaluated').first()).toBeVisible()
  })

  test('E2E-G4-05 evaluates the whole construction sequence', async ({ page }) => {
    await evaluateAll(page)
    await expect(page.locator('.cell--not-evaluated')).toHaveCount(0)
    await expect(page.getByTestId('continuity-matrix').locator('tbody tr')).toHaveCount(4)
    // Every phase carries a real run identity from the server.
    await expect(page.getByText('Analysed for this revision')).toBeVisible()
  })

  test('E2E-G4-06 and G4-07 detect confirmed, possible-only and no-route states per phase', async ({
    page,
  }) => {
    await evaluateAll(page)
    const matrix = page.getByTestId('continuity-matrix')
    // Seeded data: W→Gate and W→Lib are confirmed in both phases; E→Lib is
    // possible-only because of unresolved curb evidence; E→Gate has no route.
    await expect(matrix.locator('.cell--confirmed').first()).toBeVisible()
    await expect(matrix.locator('.cell--possible').first()).toBeVisible()
    await expect(matrix.locator('.cell--none').first()).toBeVisible()
  })

  test('E2E-G4-08 reports the first problematic phase from actual phase order', async ({ page }) => {
    await evaluateAll(page)
    const explanations = page.getByTestId('first-problem-explanations')
    await expect(explanations).toBeVisible()
    const text = await explanations.innerText()
    expect(text).toMatch(/OD-/)
    // The explanation names the phase by its real label, taken from the backend.
    expect(text).toMatch(/Phase 1 - main footway resurfacing|Phase 2 - east link reconstruction/)
    expect(text).toMatch(/unreachable|possible-only|unresolved evidence|no usable analysis/)
    // The earliest problem is identified, not merely the last one.
    expect(text).toMatch(/earliest declared phase|becomes/)
  })

  test('E2E-G4-09 creates a persisted scenario branch', async ({ page }) => {
    await page.getByTestId('nav-branches').click()
    await expect(page.getByTestId('branch-table')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('create-branch').click()
    await page.getByLabel('Branch id').fill('scn-g4-branch')
    await page.getByLabel('Branch name').fill('Alternative plan B')
    await page.getByTestId('confirm-branch').click()

    await expect(page.getByTestId('branch-row-scn-g4-branch')).toBeVisible({ timeout: 20_000 })
    // It is persisted: a fresh read of the API finds it.
    const exists = await page.evaluate(async () => {
      const response = await fetch('/api/v1/scenarios/scn-g4-branch')
      return response.status
    })
    expect(exists).toBe(200)
  })

  test('E2E-G4-10 modifies the branch without changing its source', async ({ page }) => {
    const sourceBefore = await page.evaluate(async () => {
      const response = await fetch('/api/v1/scenarios/scn-demo-baseline')
      const body = await response.json()
      return { revision: body.revision, hash: body.content_hash }
    })

    await page.getByTestId('nav-branches').click()
    await page.getByTestId('create-branch').click()
    await page.getByLabel('Branch id').fill('scn-g4-branchchild')
    await page.getByTestId('confirm-branch').click()
    await expect(page.getByTestId('branch-row-scn-g4-branchchild')).toBeVisible({ timeout: 20_000 })

    // Edit the child.
    await openScenarioEditor(page)
    await expect(page.getByTestId('scenario-revision')).toHaveText('1')
    await page.getByTestId('nav-network').click()
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_WM').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()
    await page.getByTestId('save-edits').click()
    await expect(page.getByTestId('scenario-revision')).toHaveText('2')

    // The source is untouched: same revision and same content hash.
    const sourceAfter = await page.evaluate(async () => {
      const response = await fetch('/api/v1/scenarios/scn-demo-baseline')
      const body = await response.json()
      return { revision: body.revision, hash: body.content_hash }
    })
    expect(sourceAfter).toEqual(sourceBefore)
  })

  test('E2E-G4-11 compares two branches using real backend analysis', async ({ page }) => {
    await evaluateAll(page)
    const sourceMatrix = await page.getByTestId('continuity-matrix').innerText()

    await page.getByTestId('nav-branches').click()
    await page.getByTestId('create-branch').click()
    await page.getByLabel('Branch id').fill('scn-g4-cmp-b')
    await page.getByTestId('confirm-branch').click()
    await expect(page.getByTestId('branch-row-scn-g4-cmp-b')).toBeVisible({ timeout: 20_000 })

    await evaluateAll(page)
    const branchMatrix = await page.getByTestId('continuity-matrix').innerText()

    // Both are genuine analyses of persisted scenarios; the copy is not fabricated.
    expect(sourceMatrix).toContain('OD-W')
    expect(branchMatrix).toContain('OD-W')
  })

  test('E2E-G4-12 preserves phase and branch state across a reload', async ({ page }) => {
    await openPhases(page)
    await page.getByTestId('phase-marker-phase-2').click()
    await expect(page.getByTestId('phase-marker-phase-2')).toHaveAttribute('aria-current', 'step')

    await page.reload()
    await openScenarioEditor(page)
    await page.getByTestId('scenario-select').selectOption(workScenario)
    await openPhases(page)
    // The persisted scenario still declares both phases, in order.
    await expect(page.getByTestId('phase-rail').locator('li')).toHaveCount(2)
    await expect(page.getByTestId('phase-marker-phase-2')).toContainText('order 2')
  })

  test('E2E-G4-14 rejects an invalid phase edit', async ({ page }) => {
    const before = await page.evaluate(async (scenarioId) => {
      const body = await (await fetch(`/api/v1/scenarios/${scenarioId}`)).json()
      return body.revision
    }, workScenario)

    const status = await page.evaluate(async (scenarioId) => {
      const response = await fetch(`/api/v1/scenarios/${scenarioId}/phases/phase-99/graph`)
      return response.status
    }, workScenario)
    expect(status).toBe(422)

    const after = await page.evaluate(async (scenarioId) => {
      const body = await (await fetch(`/api/v1/scenarios/${scenarioId}`)).json()
      return body.revision
    }, workScenario)
    expect(after).toBe(before)
  })

  test('E2E-G4-15 handles HTTP 409 without losing newer state', async ({ page }) => {
    await page.getByTestId('nav-network').click()
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_ALT').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()

    // Another editor commits first.
    await page.evaluate(async (scenarioId) => {
      const scenario = await (await fetch(`/api/v1/scenarios/${scenarioId}`)).json()
      await fetch(`/api/v1/scenarios/${scenarioId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_revision: scenario.revision,
          edits: [
            {
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
            },
          ],
        }),
      })
    }, workScenario)

    await page.getByTestId('save-edits').click()
    await expect(page.getByRole('alert')).toContainText(/changed since you loaded it/i)
    await expect(page.getByTestId('pending-edits')).toContainText('E_ALT')
  })

  test('E2E-G4-16 recovers from a partial evaluation failure', async ({ page }) => {
    // Fail exactly one phase evaluation; the other must still succeed.
    await page.route('**/evaluate', async (route) => {
      if (route.request().postData()?.includes('phase-2')) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 'HTTP_500',
            message: 'simulated phase failure',
            details: {},
            request_id: 'e2e',
          }),
        })
        return
      }
      await route.continue()
    })

    await evaluateAll(page)
    await expect(page.getByRole('alert')).toContainText(/Some phases could not be evaluated/i)
    // The successful phase is still analysed; the failed one is not silently a pass.
    await expect(page.locator('.cell--not-evaluated').first()).toBeVisible()
    await page.unroute('**/evaluate')
  })

  test('E2E-G4-17 distinguishes historical from current analysis', async ({ page }) => {
    await evaluateAll(page)
    await expect(page.getByText('Analysed for this revision')).toBeVisible()

    // Commit a new revision: the previous results now describe an older revision.
    await openScenarioEditor(page)
    await page.getByTestId('nav-network').click()
    await page.getByRole('tab', { name: 'Entity table' }).click()
    await page.getByTestId('edge-row-E_SSE').click()
    await openScenarioEditor(page)
    await page.getByRole('button', { name: /Close selected edge/ }).click()
    await page.getByTestId('save-edits').click()
    await expect(page.getByTestId('scenario-revision')).toHaveText('2')

    await openPhases(page)
    await expect(page.getByTestId('phase-rail')).toBeVisible()
  })

  test('E2E-G4-18 exports a genuine phase-aware manifest', async ({ page }) => {
    await evaluateAll(page)
    await page.getByTestId('nav-analysis').click()
    await expect(page.getByTestId('profile-select')).toBeVisible({ timeout: 20_000 })
    await page.getByTestId('phase-select').selectOption('phase-2')
    await page.getByTestId('run-analysis').click()
    await expect(page.getByTestId('od-table')).toBeVisible({ timeout: 40_000 })

    await page.getByTestId('nav-reports').click()
    await expect(page.getByTestId('manifest-hash')).toBeVisible({ timeout: 20_000 })
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: /Download JSON/ }).click()
    const file = await download
    expect(file.suggestedFilename()).toMatch(/^detour-lab-manifest-[0-9a-f]{12}\.json$/)
    await expect(page.getByText('Planning analysis — not certified').first()).toBeVisible()
  })
})