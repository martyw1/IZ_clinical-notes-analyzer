import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/installer',
  testMatch: 'maintenance.spec.mjs',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.IZ_CNA_E2E_BASE_URL,
    browserName: 'chromium',
    channel: process.env.IZ_CNA_E2E_BROWSER_CHANNEL,
    screenshot: 'off',
    trace: 'off',
    video: 'off',
    serviceWorkers: 'block',
    viewport: { width: 1280, height: 900 },
  },
})
