import { chromium, request } from '@playwright/test'
import { test as base, expect } from './failurePrivacy.mjs'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { HarnessError } from './guards.mjs'

export { expect }
const secrets = new Set(Object.entries(process.env).filter(([key]) => /PASSWORD|SECRET_KEY|ENCRYPTION_KEY/.test(key)).map(([, value]) => value).filter(value => value?.length > 8))

export function fixtureContract() {
  return JSON.parse(readFileSync(process.env.IZ_OM_FIXTURE_CONTRACT, 'utf8'))
}

export function credentials(role = 'office_manager') {
  const user = fixtureContract().users[role]
  if (!user) throw new HarnessError('UNKNOWN_FIXTURE_ROLE')
  return { username: user.username, password: process.env.IZ_OM_PASSWORD }
}

function evidencePath(name) {
  if (!/^[a-zA-Z0-9_.-]+$/.test(name) || name.startsWith('.')) throw new HarnessError('UNSAFE_ARTIFACT_NAME')
  return path.join(process.env.IZ_OM_EVIDENCE_DIR, name)
}

function assertSecretFree(text) {
  if ([...secrets].some(secret => text.includes(secret))) throw new HarnessError('SECRET_IN_EVIDENCE_REFUSED')
}

export function writeEvidence(name, payload) {
  const text = JSON.stringify(payload, null, 2)
  assertSecretFree(text)
  writeFileSync(evidencePath(name), text)
}

export async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready)
  assertSecretFree(await page.locator('body').innerText())
  await page.screenshot({ path: evidencePath(name), fullPage: true, animations: 'disabled', mask: [page.locator('input')] })
}

export async function login(page, role = 'office_manager') {
  const account = credentials(role)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill(account.username)
  await page.getByLabel('Password', { exact: true }).fill(account.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible()
  const token = await page.evaluate(() => sessionStorage.getItem('iz-cna-v2-access-token'))
  if (token) secrets.add(token)
}

export async function apiFor(role = 'office_manager') {
  const anonymous = await request.newContext({ baseURL: process.env.IZ_OM_BASE_URL, timeout: 15_000 })
  try {
    const response = await anonymous.post('/api/auth/login', { data: credentials(role), maxRedirects: 0 })
    if (!response.ok()) throw new HarnessError('SYNTHETIC_API_LOGIN_FAILED')
    const { access_token: token } = await response.json()
    if (typeof token !== 'string' || !token) throw new HarnessError('SYNTHETIC_TOKEN_MISSING')
    secrets.add(token)
    return request.newContext({ baseURL: process.env.IZ_OM_BASE_URL, timeout: 15_000, extraHTTPHeaders: { Authorization: `Bearer ${token}` } })
  } finally { await anonymous.dispose() }
}

export const test = base.extend({
  browser: [async ({}, use) => {
    const browser = await chromium.launch({ channel: process.env.IZ_OM_BROWSER_CHANNEL,
      executablePath: process.env.IZ_OM_BROWSER_EXECUTABLE, headless: process.env.IZ_OM_HEADED !== '1' })
    const cdp = await browser.newBrowserCDPSession()
    const version = await cdp.send('Browser.getVersion')
    const processInfo = await cdp.send('SystemInfo.getProcessInfo')
    const record = { executable: process.env.IZ_OM_BROWSER_EXECUTABLE, channel: process.env.IZ_OM_BROWSER_CHANNEL,
      version: browser.version(), product: version.product, userAgent: version.userAgent,
      pids: processInfo.processInfo.map(item => ({ pid: item.id, type: item.type })), contextsClosed: false, browserClosed: false }
    try { await use(browser) } finally {
      await cdp.detach()
      await browser.close()
      record.contextsClosed = true
      record.browserClosed = !browser.isConnected()
      writeEvidence(`browser-${process.pid}.json`, record)
    }
  }, { scope: 'worker' }],
  page: async ({ page, context, failurePrivacy }, use, testInfo) => {
    let pageErrorCount = 0
    let consoleErrorCount = 0
    let blockedExternalRequests = 0
    page.on('pageerror', () => { pageErrorCount += 1 })
    page.on('console', message => { if (message.type() === 'error') consoleErrorCount += 1 })
    await context.route('**/*', async route => {
      if (new URL(route.request().url()).origin !== process.env.IZ_OM_BASE_URL) {
        blockedExternalRequests += 1
        return route.abort('blockedbyclient')
      }
      return route.continue()
    })
    try { await use(page) } finally {
      writeEvidence(`surface-${testInfo.testId.replace(/[^a-zA-Z0-9-]/g, '-')}.json`, {
        title: testInfo.title, pageErrorCount, consoleErrorCount, blockedExternalRequests,
        rawConsoleAndErrorBodiesOmitted: true,
      })
      expect(pageErrorCount, 'No unhandled browser page errors').toBe(0)
    }
  },
})
