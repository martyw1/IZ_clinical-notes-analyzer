import { test, expect, login, credentials, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

const tokenKey = 'iz-cna-v2-access-token'
const navigation = page => page.getByRole('navigation', { name: 'Primary navigation' })

async function signInWithoutReload(page) {
  const account = credentials()
  await page.getByLabel('Username', { exact: true }).fill(account.username)
  await page.getByLabel('Password', { exact: true }).fill(account.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(navigation(page)).toBeVisible()
}

async function captureLoginWidths(page, stem) {
  const sizes = []
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    await page.getByRole('button', { name: 'Sign in', exact: true }).focus()
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
    expect(fits).toBe(true)
    await capture(page, `${stem}-${width}.png`)
    sizes.push({ width, documentFits: fits, keyboardFocus: true })
  }
  return sizes
}

test('revoked current session clears protected content and reauthenticates @happy', async ({ page }) => {
  // Given: a real office-manager session has a selected synthetic file.
  await login(page)
  await page.getByRole('button', { name: 'Manual Upload', exact: true }).click()
  await page.getByLabel('Treatment-plan binder files', { exact: true }).setInputFiles(fixtureContract().files.binder)
  const admin = await apiFor('admin')
  try {
    const reset = await admin.post(`/api/users/${fixtureContract().users.office_manager.id}/reset-password`, {
      data: { new_password: credentials().password, require_reset_on_login: false },
    })
    expect(reset.status()).toBe(200)
  } finally { await admin.dispose() }
  // When: the revoked bearer reaches the real protected endpoint.
  const rejected = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/patient-roster')
  await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
  expect((await rejected).status()).toBe(401)
  // Then: protected controls and selection disappear, and the same account can reauthenticate.
  await expect(navigation(page)).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(1)
  await expect(page.getByRole('alert')).toContainText('session has expired')
  expect(await page.evaluate(key => sessionStorage.getItem(key) === null, tokenKey)).toBe(true)
  const widths = await captureLoginWidths(page, 'task-6-session-expired')
  await signInWithoutReload(page)
  await page.getByRole('button', { name: 'Manual Upload', exact: true }).click()
  expect(await page.getByLabel('Treatment-plan binder files', { exact: true }).evaluate(input => input.files.length)).toBe(0)
  await expect(page.getByText('No binder files selected', { exact: true })).toBeVisible()
  await capture(page, 'task-6-session-restored.png')
  writeEvidence('task-6-session.json', { realBackendRevocation: true, protectedStatus: 401, expiryAlertCount: 1,
    protectedContentCleared: true, selectedFilesCleared: true, reauthenticatedWithoutReload: true, widths })
})

test('delayed old 401 cannot expire a new login on the same page @edge', async ({ page }) => {
  // Given: the old session has a pending protected request.
  await login(page)
  let release
  const held = new Promise(resolve => { release = resolve })
  let started
  const requested = new Promise(resolve => { started = resolve })
  await page.route('**/api/v2/patient-roster', async route => {
    started()
    await held
    await route.fulfill({ status: 401, json: { detail: 'Invalid token' } })
  })
  await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
  await requested
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await signInWithoutReload(page)
  // When: the old 401 is released without navigating or reloading the document.
  const failed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/patient-roster')
  release()
  expect((await failed).status()).toBe(401)
  // Then: the replacement session remains usable.
  await expect(navigation(page)).toBeVisible()
  await page.getByRole('button', { name: 'Manual Upload', exact: true }).click()
  await expect(page.getByLabel('Normalized V2 aggregate JSON', { exact: true })).toBeVisible()
  expect(await page.evaluate(key => Boolean(sessionStorage.getItem(key)), tokenKey)).toBe(true)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await capture(page, 'task-6-session-stale-401.png')
  writeEvidence('task-6-session-error.json', { delayedOld401: true, loginOnSameDocument: true, newSessionSurvives: true,
    protectedControlsUsable: true, authenticatedResponseFaultInjection: true })
})

test('non-401 failures keep authentication and validation inputs stay redacted @edge', async ({ page }) => {
  // Given: real authentication and synthetic fault payloads at the HTTP boundary.
  await login(page)
  const marker = 'SYNTHETIC-PRIVATE-UI-ERROR-MARKER'
  const observed = []
  let consoleLeak = false
  page.on('console', message => { consoleLeak ||= message.text().includes(marker) })
  for (const status of [403, 422, 500, 0]) {
    await page.getByRole('button', { name: 'Help', exact: true }).click()
    await page.route('**/api/v2/patient-roster', route => status === 0 ? route.abort('failed') : route.fulfill({ status,
      json: { detail: status === 422 ? [{ loc: ['body', 'password'], type: 'string_too_short', input: marker, ctx: { error: marker }, msg: marker }] : marker },
    }))
    // When: the protected roster receives a non-authentication failure.
    await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    // Then: authentication survives and private input never reaches UI or console.
    await expect(navigation(page)).toBeVisible()
    expect((await page.locator('body').innerText()).includes(marker)).toBe(false)
    expect(await page.evaluate(key => Boolean(sessionStorage.getItem(key)), tokenKey)).toBe(true)
    observed.push({ status, sessionRetained: true, privateInputVisible: false })
    await page.unroute('**/api/v2/patient-roster')
  }
  expect(consoleLeak).toBe(false)
  await capture(page, 'task-6-session-safe-error.png')
  writeEvidence('task-6-session-non401.json', { cases: observed, privateInputLogged: consoleLeak })
})

test('blank login stays local and failed login reports safe feedback @edge', async ({ page }) => {
  // Given: a fresh login page and a counter that records no request bodies.
  await page.goto('/')
  let attempts = 0
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/auth/login') attempts += 1 })
  await page.getByLabel('Username', { exact: true }).fill('')
  // When: the user submits blank credentials, then a synthetic nonexistent account.
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  expect(attempts).toBe(0)
  const widths = await captureLoginWidths(page, 'task-6-session-blank')
  await page.getByLabel('Username', { exact: true }).fill('synthetic-nonexistent-user')
  await page.getByLabel('Password', { exact: true }).fill('synthetic-invalid-123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  // Then: only the nonblank attempt reaches the real backend; it does not masquerade as expiry.
  await expect(page.getByRole('alert')).toContainText('Invalid credentials')
  expect(attempts).toBe(1)
  await signInWithoutReload(page)
  writeEvidence('task-6-session-login.json', { blankLoginRequests: 0, failedLoginRequests: 1, loginRecovered: true, widths })
})
