import { defineConfig } from '@playwright/test'
import { HarnessError } from './e2e/office-manager/support/guards.mjs'

const baseURL = process.env.IZ_OM_BASE_URL
if (!baseURL || !/^http:\/\/127\.0\.0\.1:\d+$/.test(baseURL) || !process.env.IZ_OM_RUN_ID) {
  throw new HarnessError('RUN_THROUGH_ISOLATED_SMOKE_RUNNER')
}
const scenario = process.env.IZ_OM_SCENARIO ?? 'harness'
const selectedCase = process.env.IZ_OM_CASE ?? 'all'

export default defineConfig({
  testDir: './e2e/office-manager',
  testMatch: scenario === 'all' ? '*.spec.mjs' : `${scenario}.spec.mjs`,
  grep: selectedCase === 'all' ? undefined : new RegExp(`@${selectedCase}\\b`),
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  fullyParallel: false,
  forbidOnly: true,
  outputDir: process.env.IZ_OM_OUTPUT_DIR,
  reporter: './e2e/office-manager/support/reporter.mjs',
  use: {
    baseURL,
    browserName: 'chromium',
    channel: process.env.IZ_OM_BROWSER_CHANNEL,
    launchOptions: { executablePath: process.env.IZ_OM_BROWSER_EXECUTABLE },
    headless: process.env.IZ_OM_HEADED !== '1',
    viewport: { width: 1280, height: 900 },
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    serviceWorkers: 'block',
  },
})
