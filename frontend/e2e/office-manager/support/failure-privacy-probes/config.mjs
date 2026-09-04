import { defineConfig } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: import.meta.dirname,
  testMatch: 'cases.mjs',
  outputDir: path.join(process.env.IZ_OM_PRIVACY_ROOT, 'output'),
  preserveOutput: 'always',
  timeout: 5_000,
  workers: 1,
  retries: 0,
  fullyParallel: false,
  quiet: true,
  reporter: './reporter.mjs',
  use: {
    trace: 'off', video: 'off', screenshot: 'off', headless: true,
    channel: process.env.IZ_OM_PRIVACY_BROWSER || undefined,
    launchOptions: { executablePath: process.env.IZ_OM_PRIVACY_BROWSER_EXECUTABLE || undefined, args: ['--enable-automation'] },
  },
})
