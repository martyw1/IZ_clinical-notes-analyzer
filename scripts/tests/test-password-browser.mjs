import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Standalone, finite smoke: node scripts/tests/test-password-browser.mjs [--runtime EXE] [--evidence DIR].
// Runtime data stays in a unique Windows-local directory; evidence never contains credentials.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const require = createRequire(path.join(root, 'frontend', 'package.json'))
const { chromium } = require('@playwright/test')
const option = name => { const index = process.argv.indexOf(name); return index < 0 ? undefined : process.argv[index + 1] }
const runtime = option('--runtime')
const evidence = path.resolve(root, option('--evidence') ?? '.omo/evidence/beta4-password-browser')
const localRoot = process.env.LOCALAPPDATA
assert(localRoot, 'Windows LOCALAPPDATA is required for isolated runtime data')
const data = await mkdtemp(path.join(localRoot, 'IZ-beta4-password-smoke-'))
await mkdir(evidence, { recursive: true })
const port = await new Promise(resolve => { const server = net.createServer(); server.listen(0, '127.0.0.1', () => { const address = server.address(); server.close(() => resolve(address.port)) }) })
const base = `http://127.0.0.1:${port}`
const env = { ...process.env, IZ_CNA_LOCAL_APP_DATA_DIR: data, IZ_CNA_LOCAL_SQLITE_DB_PATH: 'synthetic.sqlite3', IZ_CNA_PORT: String(port), PYTHONPATH: path.join(root, 'backend'), ENVIRONMENT: 'local-client', IZ_CNA_DATA_ENCRYPTION_KEY: randomBytes(32).toString('base64url'), IZ_CNA_SECRET_KEY: randomBytes(32).toString('hex'), IZ_CNA_BOOTSTRAP_ADMIN_USERNAME: 'admin', IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD: 'r3mar123ABC' }
delete env.IZ_CNA_ENV_FILE
const child = spawn(runtime ?? path.join(root, 'backend/.venv/Scripts/python.exe'), runtime ? [] : ['-m', 'app.desktop_runtime'], { cwd: root, env, windowsHide: true, stdio: 'ignore' })
const checks = {}
const captures = []
let browser
let activePage
let phase = 'startup'
let failed = false
const password = () => `Synthetic!9${randomBytes(12).toString('hex')}`
const first = password(), second = password(), third = password(), staffPassword = password(), staffReset = password()
async function api(route, body, token) { return fetch(base + route, { method: body ? 'POST' : 'GET', headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) }) }
async function loginApi(secret, username = 'admin') { return api('/api/auth/login', { username, password: secret }) }
try {
  for (let attempt = 0; attempt < 120; attempt++) {
    if (child.exitCode !== null) throw new Error('Runtime exited before readiness')
    try { if ((await fetch(base + '/api/version')).ok) break } catch {}
    if (attempt === 119) throw new Error('Runtime readiness timeout')
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  activePage = page
  checks.browserPageErrors = 0
  page.on('pageerror', () => { checks.browserPageErrors++ })
  page.setDefaultTimeout(15000)
  async function capture(state) {
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 })
      await page.screenshot({ path: path.join(evidence, `${state}-${width}.png`), fullPage: true, mask: [page.locator('input[type="password"], textarea')] })
      const layout = await page.evaluate(() => ({ documentWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth }))
      captures.push({ state, width, ...layout, horizontalOverflow: layout.documentWidth > layout.viewportWidth })
    }
  }
  async function login(secret, username = 'admin') {
    await page.getByLabel('Username', { exact: true }).fill(username)
    await page.getByLabel('Password', { exact: true }).fill(secret)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  }
  async function change(current, next) {
    await page.getByLabel('Current password', { exact: true }).fill(current)
    await page.getByLabel('New password', { exact: true }).fill(next)
    await page.getByLabel('Confirm new password', { exact: true }).fill(next)
    await page.getByRole('button', { name: 'Update password', exact: true }).click()
  }
  async function recovery(secret, capturePrefix) {
    await page.getByLabel('Current password for recovery setup', { exact: true }).fill(secret)
    const responseReady = page.waitForResponse(response => response.url().endsWith('/api/users/me/recovery-code') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Create recovery code', exact: true }).click()
    const response = await responseReady
    assert(response.ok(), `Recovery generation HTTP ${response.status()}`)
    const field = page.locator('textarea[readonly]')
    phase = 'recovery-code-visible'
    await field.waitFor()
    const code = await field.inputValue()
    assert(code.length > 20)
    assert(await page.getByRole('button', { name: 'Continue', exact: true }).isDisabled())
    if (capturePrefix) await capture(capturePrefix)
    await page.getByRole('checkbox').check()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    await page.getByRole('button', { name: 'Account', exact: true }).waitFor()
    return code
  }
  phase = 'initial-login'
  await page.goto(base)
  await capture('login')
  await login('r3mar123ABC')
  await page.getByRole('heading', { name: 'Set a new password', exact: true }).waitFor()
  await capture('mandatory-change')
  await change('r3mar123ABC', first)
  await page.getByRole('heading', { name: 'Protect your account', exact: true }).waitFor()
  await capture('recovery-setup')
  const code = await recovery(first, 'recovery-save')
  checks.initialPasswordChangeAndSavedRecovery = true
  phase = 'account-change'
  const oldLogin = await (await loginApi(first)).json()
  await page.getByRole('button', { name: 'Account', exact: true }).click()
  await capture('account')
  await change(first, second)
  await page.getByText('Password updated.', { exact: false }).waitFor()
  checks.oldPasswordRejectedAfterChange = !(await loginApi(first)).ok
  checks.oldSessionRejectedAfterChange = !(await api('/api/users/me', undefined, oldLogin.access_token)).ok
  assert(checks.oldPasswordRejectedAfterChange && checks.oldSessionRejectedAfterChange)
  phase = 'staff-reset'
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  await page.getByLabel('Username', { exact: true }).fill('syntheticstaff')
  await page.getByLabel('Full name', { exact: true }).fill('Synthetic QA Staff')
  await page.getByLabel('Temporary password', { exact: true }).fill(staffPassword)
  await page.getByRole('button', { name: 'Create user', exact: true }).click()
  const row = page.getByRole('row').filter({ hasText: 'Synthetic QA Staff' })
  await row.waitFor()
  await capture('users')
  await row.getByRole('button', { name: 'Reset password', exact: true }).click()
  await page.getByLabel('New password', { exact: true }).fill(staffReset)
  await page.getByLabel('Confirm new password', { exact: true }).fill(staffReset)
  await capture('staff-reset')
  await page.getByRole('button', { name: 'Confirm password reset', exact: true }).click()
  await page.getByText('Password reset for syntheticstaff;', { exact: false }).waitFor()
  checks.staffOldPasswordRejected = !(await loginApi(staffPassword, 'syntheticstaff')).ok
  const staff = await (await loginApi(staffReset, 'syntheticstaff')).json()
  checks.staffTemporaryPasswordRequiresChange = staff.must_reset_password === true
  assert(checks.staffOldPasswordRejected && checks.staffTemporaryPasswordRequiresChange)
  phase = 'forgot-password'
  const beforeRecovery = await (await loginApi(second)).json()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await page.getByRole('button', { name: 'Forgot password?', exact: true }).click()
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Recovery code', { exact: true }).fill(code)
  await page.getByLabel('New password', { exact: true }).fill(third)
  await page.getByLabel('Confirm new password', { exact: true }).fill(third)
  await capture('forgot-password')
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor()
  checks.oldPasswordRejectedAfterRecovery = !(await loginApi(second)).ok
  checks.oldSessionRejectedAfterRecovery = !(await api('/api/users/me', undefined, beforeRecovery.access_token)).ok
  checks.recoveryCodeCannotBeReused = !(await api('/api/auth/recover-password', { username: 'admin', recovery_code: code, new_password: password() })).ok
  assert(checks.oldPasswordRejectedAfterRecovery && checks.oldSessionRejectedAfterRecovery && checks.recoveryCodeCannotBeReused)
  await login(third)
  await page.getByRole('heading', { name: 'Protect your account', exact: true }).waitFor()
  const replacement = await recovery(third)
  checks.replacementRecoveryCodeIssued = replacement !== code
  checks.allAffectedScreensWithinViewport = captures.every(capture => !capture.horizontalOverflow)
  assert(checks.allAffectedScreensWithinViewport)
  phase = 'complete'
} catch (error) {
  failed = true
  console.log(JSON.stringify({ failureType: error?.name ?? 'Error', safeReason: String(error?.message ?? '').split('\n')[0].replace(/Synthetic[^\s"']+/g, '[masked]') }))
  if (activePage) await activePage.screenshot({ path: path.join(evidence, 'failure.png'), fullPage: true, mask: [activePage.locator('input[type="password"], textarea')] })
} finally {
  if (browser) await browser.close()
  await new Promise(resolve => { const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); killer.once('exit', resolve) })
  await new Promise(resolve => { if (child.exitCode !== null) resolve(); else { child.once('exit', resolve); setTimeout(resolve, 5000).unref() } })
  checks.ownedRuntimeStopped = child.exitCode !== null || child.signalCode !== null
  checks.runtimePortClosed = await new Promise(resolve => { const socket = net.createConnection({ host: '127.0.0.1', port }); socket.once('connect', () => { socket.destroy(); resolve(false) }); socket.once('error', () => resolve(true)) })
  if (!checks.runtimePortClosed) failed = true
  const result = { passed: !failed, phase, checks, captures, runtime: runtime ? 'prepared-executable' : 'source-desktop', syntheticDataOutsideRepository: true, credentialsRecorded: false, captureCount: captures.length }
  await writeFile(path.join(evidence, 'result.json'), JSON.stringify(result, null, 2) + '\n')
  console.log(JSON.stringify({ passed: result.passed, phase, captureCount: captures.length, checks }))
  process.exitCode = failed ? 1 : 0
}
