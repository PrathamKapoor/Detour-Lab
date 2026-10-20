import { expect, test, type Page } from '@playwright/test'

/**
 * P-35 regression guard: the navigation hint must meet the WCAG 2.x AA
 * contrast threshold for normal-size text (4.5:1) in every state the user can
 * see it in.
 *
 * This path used to hold a throwaway diagnostic that only printed axe findings
 * and overflow measurements to the console and asserted nothing. It now holds a
 * test that can fail, and the `testIgnore` entry that used to hide it has been
 * removed.
 *
 * The measurement is taken from the **rendered** document, not from the
 * stylesheet source. P-35 existed precisely because a token change in CSS is
 * not evidence that the rendered page passes, so the foreground colour and the
 * effective background are read from the live element in each nav state.
 *
 * The file keeps its original path because the environment that replaced the
 * diagnostic had no file-move capability. Rename it when convenient:
 *   Move-Item apps/web/e2e/gate6-a11y-probe.spec.ts apps/web/e2e/gate6-contrast.spec.ts
 * Use Move-Item, not `git mv`: this file is untracked, so `git mv` refuses it.
 */

/** WCAG 2.x relative luminance from an 8-bit sRGB triple. */
function relativeLuminance(rgb: readonly [number, number, number]): number {
  const channels = rgb.map((value) => {
    const c = value / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

/** WCAG 2.x contrast ratio between two sRGB triples. */
function contrastRatio(
  a: readonly [number, number, number],
  b: readonly [number, number, number],
): number {
  const la = relativeLuminance(a)
  const lb = relativeLuminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/** Parse a computed `rgb()`/`rgba()` string into a triple and an alpha value. */
function parseColor(value: string): { rgb: [number, number, number]; alpha: number } {
  const parts = (value.match(/[\d.]+/g) ?? []).map(Number)
  if (parts.length < 3) {
    throw new Error(`cannot parse colour ${JSON.stringify(value)}`)
  }
  return {
    rgb: [parts[0], parts[1], parts[2]],
    alpha: parts.length > 3 ? parts[3] : 1,
  }
}

/**
 * Read the rendered foreground of a nav item's hint, plus the first
 * non-transparent background behind it and the rendered font size.
 */
async function renderedHint(page: Page, testId: string) {
  return page.evaluate((id) => {
    const item = document.querySelector(`[data-testid="${id}"]`) as HTMLElement | null
    const hint = item?.querySelector('.app-nav__hint') as HTMLElement | null
    if (!item || !hint) return null

    const effectiveBackground = (start: HTMLElement): string => {
      let current: HTMLElement | null = start
      while (current) {
        const background = getComputedStyle(current).backgroundColor
        const numbers = (background.match(/[\d.]+/g) ?? []).map(Number)
        const alpha = numbers.length > 3 ? numbers[3] : 1
        if (background !== 'transparent' && alpha > 0) return background
        current = current.parentElement
      }
      return getComputedStyle(document.body).backgroundColor
    }

    const hintStyle = getComputedStyle(hint)
    return {
      foreground: hintStyle.color,
      background: effectiveBackground(item),
      fontSizePx: Number.parseFloat(hintStyle.fontSize),
    }
  }, testId)
}

test('the navigation hint meets WCAG AA contrast in the idle, hover and active states', async ({
  page,
}) => {
  await page.goto('/')

  // The initial view is the dashboard, so the evidence item starts idle.
  const idle = await renderedHint(page, 'nav-evidence')
  expect(idle).not.toBeNull()
  expect(idle!.fontSizePx).toBeLessThan(18.66)

  // The failing colour P-35 replaced: --text-muted (#7b8b9d).
  const muted: [number, number, number] = [123, 139, 157]
  const idleForeground = parseColor(idle!.foreground)
  expect(idleForeground.rgb).not.toEqual(muted)

  const idleRatio = contrastRatio(idleForeground.rgb, parseColor(idle!.background).rgb)
  expect(idleRatio, `idle state foreground ${idle!.foreground} on ${idle!.background}`).toBeGreaterThanOrEqual(4.5)

  await page.getByTestId('nav-evidence').hover()
  const hovered = await renderedHint(page, 'nav-evidence')
  expect(hovered).not.toBeNull()
  const hoverRatio = contrastRatio(
    parseColor(hovered!.foreground).rgb,
    parseColor(hovered!.background).rgb,
  )
  expect(hoverRatio, `hover state foreground ${hovered!.foreground} on ${hovered!.background}`).toBeGreaterThanOrEqual(4.5)

  await page.getByTestId('nav-evidence').click()
  await expect(page.getByTestId('nav-evidence')).toHaveAttribute('aria-current', 'page')
  // Move the pointer out of the sidebar first. A click leaves the mouse over the
  // item, and `.app-nav__item:hover` and `.app-nav__item--active` have equal
  // specificity, so the active background would win only by source order. The
  // sidebar is on the left, so the bottom-right corner is safely outside it.
  const viewport = page.viewportSize()
  if (viewport) await page.mouse.move(viewport.width - 5, viewport.height - 5)
  const active = await renderedHint(page, 'nav-evidence')
  expect(active).not.toBeNull()
  const activeRatio = contrastRatio(
    parseColor(active!.foreground).rgb,
    parseColor(active!.background).rgb,
  )
  expect(activeRatio, `active state foreground ${active!.foreground} on ${active!.background}`).toBeGreaterThanOrEqual(4.5)
})
