import { readdirSync, rmSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * E2E isolation, part 1 of 2.
 *
 * Each run gets its own database file (see `playwright.config.ts`), which is what
 * actually guarantees a pristine synthetic baseline: the backend seeds the
 * synthetic dataset on first start, so a new file is a new seed.
 *
 * This step only prunes databases left behind by *earlier* runs. It deliberately
 * filters by age rather than deleting every `e2e-*` file: Playwright may launch
 * the web servers before running global setup, and deleting the current run's
 * database would leave the server reading an unlinked file.
 */
const STALE_AFTER_MS = 12 * 60 * 60 * 1000

export default function globalSetup(): void {
  const varDirectory = fileURLToPath(new URL('../../var/', import.meta.url))
  let entries: string[] = []
  try {
    entries = readdirSync(varDirectory)
  } catch {
    return // the backend creates the directory on first start
  }

  const now = Date.now()
  for (const entry of entries) {
    if (!entry.startsWith('e2e-')) continue
    const path = join(varDirectory, entry)
    try {
      if (now - statSync(path).mtimeMs > STALE_AFTER_MS) {
        rmSync(path, { force: true })
      }
    } catch {
      // A file another process still holds; it will be pruned by a later run.
    }
  }
}