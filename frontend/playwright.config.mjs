import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  globalSetup: process.env.IZ_CNA_E2E_DESKTOP === '1' ? './e2e/desktop-global-setup.mjs' : undefined,
  timeout: 30_000,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: process.env.IZ_CNA_E2E_BASE_URL ?? 'http://127.0.0.1:8765',
    browserName: 'chromium',
    channel: process.env.IZ_CNA_E2E_BROWSER_CHANNEL ?? 'chrome',
    screenshot: 'on',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 900 },
  },
})
