import { chromium } from '@playwright/test'
import { setTimeout as delay } from 'node:timers/promises'
import { login, capture, writeEvidence } from './fixtures.mjs'

const browser = await chromium.launch({ channel: process.env.IZ_OM_BROWSER_CHANNEL,
  executablePath: process.env.IZ_OM_BROWSER_EXECUTABLE, headless: false })
const context = await browser.newContext({ baseURL: process.env.IZ_OM_BASE_URL, viewport: null, serviceWorkers: 'block' })
const cdp = await browser.newBrowserCDPSession()
const info = await cdp.send('SystemInfo.getProcessInfo')
const receipt = { channel: process.env.IZ_OM_BROWSER_CHANNEL, executable: process.env.IZ_OM_BROWSER_EXECUTABLE,
  version: browser.version(), pids: info.processInfo.map(item => ({ pid: item.id, type: item.type })),
  baseUrl: process.env.IZ_OM_BASE_URL, role: process.env.IZ_OM_INTERACTIVE_ROLE,
  boundedSeconds: Number(process.env.IZ_OM_INTERACTIVE_SECONDS), ownedContext: true,
  browserClosed: false, handsOnActionsClaimed: false }
try {
  await context.route('**/*', route => new URL(route.request().url()).origin === process.env.IZ_OM_BASE_URL
    ? route.continue() : route.abort('blockedbyclient'))
  const page = await context.newPage()
  await login(page, process.env.IZ_OM_INTERACTIVE_ROLE)
  receipt.windowTitle = await page.title()
  receipt.startedAt = new Date().toISOString()
  writeEvidence('interactive-ready.json', receipt)
  await capture(page, 'interactive-ready.png')
  await delay(receipt.boundedSeconds * 1_000)
  await capture(page, 'interactive-finished.png')
} finally {
  await cdp.detach()
  await context.close()
  await browser.close()
  receipt.browserClosed = !browser.isConnected()
  receipt.completedAt = new Date().toISOString()
  writeEvidence('interactive-teardown.json', receipt)
}
