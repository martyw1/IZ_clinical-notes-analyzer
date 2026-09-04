import { readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { test, expect, login, capture, fixtureContract, apiFor, writeEvidence } from './support/fixtures.mjs'

test('real office-manager login and beta version agree @happy', async ({ page, request }) => {
  // Given: an owned fresh runtime with two facilities and four synthetic roles.
  const fixture = fixtureContract()
  const health = await request.get('/api/health')
  expect(health.status()).toBe(200)
  expect((await health.json()).runtime).toBe('v2')
  expect(Object.keys(fixture.users)).toHaveLength(4)
  expect(new Set(Object.values(fixture.facilities)).size).toBe(2)
  expect(new Set(Object.values(fixture.patients)).size).toBe(4)
  expect(fixture.plans.primaryV1.plan_version_id).not.toBe(fixture.plans.primaryV2.plan_version_id)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
  await capture(page, 'task-1-login.png')
  // When: the office manager signs in through the real DOM and backend.
  await login(page)
  // Then: the settled authenticated surface and version endpoint agree.
  await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible()
  const response = await request.get('/api/version')
  expect(response.status()).toBe(200)
  const version = await response.json()
  const expected = JSON.parse(readFileSync(path.join(process.env.IZ_OM_REPO_ROOT, 'VERSION.json'), 'utf8'))
  expect(version.version).toBe(expected.version)
  expect(version.build).toBe(expected.build)
  expect(version.release_channel).toBe('beta-local-desktop-v2')
  expect(version.stability).toBe('beta')
  await expect(page.locator('.v2-footer')).toContainText(version.version)
  await expect(page.getByText('Active runtime: V2 | office_manager', { exact: true })).toBeVisible()
  await capture(page, 'task-1-authenticated.png')
  writeEvidence('task-1-login-version.json', { healthStatus: 200, loginViaRealUi: true, version,
    fixtureRoles: Object.keys(fixture.users), facilities: fixture.facilities, planVersions: fixture.plans,
    databaseIntegrityOk: fixture.integrity_ok, foreignKeysOk: fixture.foreign_keys_ok })
})

test('each seeded role authenticates against the real backend @happy', async () => {
  // Given: four isolated synthetic role accounts.
  const roles = Object.keys(fixtureContract().users)
  const observed = []
  // When: each account logs in against the actual API.
  for (const role of roles) {
    const api = await apiFor(role)
    try {
      const response = await api.get('/api/users/me')
      expect(response.status()).toBe(200)
      const profile = await response.json()
      // Then: the stored role and active state match the intended account.
      expect(profile.role).toBe(role)
      expect(profile.must_reset_password).toBe(false)
      observed.push({ role, status: response.status(), userId: profile.id })
    } finally { await api.dispose() }
  }
  writeEvidence('task-1-roles.json', { setupIsNotUiAccountCreationCoverage: true, roles: observed })
})

test('unsafe runner targets fail before runtime or evidence mutation @edge', async () => {
  // Given: the real command-line runner and both in-memory and subprocess guard scenarios.
  // When: the self-tests invoke external URL, non-owned path, and missing executable cases.
  const result = spawnSync(process.execPath, ['--test', 'frontend/e2e/office-manager/support/guards.test.mjs',
    'frontend/e2e/office-manager/support/runner-guards.test.mjs'], {
    cwd: process.env.IZ_OM_REPO_ROOT, encoding: 'utf8', windowsHide: true, timeout: 60_000,
  })
  // Then: every real refusal preserved the existing targets and created no run artifacts.
  writeEvidence('task-1-harness-error.json', { selfTestExitCode: result.status, signal: result.signal,
    output: result.stdout, stderrOmitted: true, scenarios: ['external-url', 'unowned-data-path', 'existing-data-path', 'missing-prepared-executable'] })
  expect(result.status).toBe(0)
})
