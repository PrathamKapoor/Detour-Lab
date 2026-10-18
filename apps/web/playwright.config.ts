import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'

/**
 * E2E runs against the real backend and the real Vite dev server.
 * Nothing is mocked: the browser talks to FastAPI, which evaluates the seeded
 * synthetic dataset and persists every change to SQLite.
 *
 * Isolation: each run gets its own database file, and the backend server is
 * always started fresh so it cannot inherit an open handle on a previous run's
 * database. Specs must still be order-independent within a run.
 */
const API_PORT = Number(process.env.DETOUR_LAB_E2E_API_PORT ?? 8078)
const WEB_PORT = Number(process.env.DETOUR_LAB_E2E_WEB_PORT ?? 5174)

/** Absolute interpreter path, so a relative path in a shell command still works. */
const PYTHON = process.env.DETOUR_LAB_PYTHON ?? fileURLToPath(new URL('../../.venv/Scripts/python.exe', import.meta.url))

/**
 * Every run gets its own database file. The backend seeds a pristine synthetic
 * dataset on first start, so this guarantees the suite never inherits edits from
 * a previous run - and on Windows, where a running server keeps a handle to an
 * open SQLite file, deleting the old database is not a reliable reset.
 */
const DB_FILE = `var/e2e-${Date.now()}-${process.pid}.sqlite3`

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testMatch: /responsive\.spec\.ts/ },
  ],
  webServer: [
    {
      // Uses the repository virtualenv so E2E runs the same interpreter and the
      // same pinned dependencies as the backend test-suite.
      command: `"${PYTHON}" -m uvicorn detour_lab.api.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: fileURLToPath(new URL('../api', import.meta.url)),
      url: `http://127.0.0.1:${API_PORT}/api/v1/health`,
      // Never reuse a backend: a surviving server would hold this run's database
      // open but serve another run's state, silently invalidating the results.
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DETOUR_LAB_DB_PATH: fileURLToPath(new URL(`../../${DB_FILE}`, import.meta.url)),
        PYTHONPATH: fileURLToPath(new URL('../api', import.meta.url)),
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      cwd: '.',
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: { DETOUR_LAB_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
})