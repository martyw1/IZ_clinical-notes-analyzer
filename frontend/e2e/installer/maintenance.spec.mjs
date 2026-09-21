import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, openSync, closeSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { loadMaintenanceAttachment } from './support/maintenanceAttachment.mjs'

const enabled = Boolean(process.env.IZ_CNA_MAINTENANCE_ATTACHMENT)
const observations = []
let context

function sha256Text(value) {
  return createHash('sha256').update(value, 'utf8').digest('hex')
}

function requiredCredential(name) {
  const value = process.env[name]
  if (!value || value.length < 12) throw new Error(`Maintenance browser credential unavailable: ${name}`)
  return value
}

async function signIn(page, username, password) {
  await page.goto('/')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  const recoverySetup = page.getByRole('heading', { name: 'Protect your account', exact: true })
  const navigation = page.getByRole('navigation', { name: 'Primary navigation', exact: true })
  await expect(recoverySetup.or(navigation)).toBeVisible()
  if (await recoverySetup.isVisible()) {
    await page.getByLabel('Current password for recovery setup', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Create recovery code', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Save your recovery code', exact: true })).toBeVisible()
    await page.getByRole('checkbox', { name: 'I have saved my recovery code in a secure place.', exact: true }).check()
    await page.getByRole('button', { name: 'Continue', exact: true }).click()
    observations.push({ scenario: 'recovery-setup', status: 'passed', observable: { completed: true } })
  }
  await expect(navigation).toBeVisible()
  await expect(page.getByRole('heading', { name: 'IZ Clinical Notes Analyzer' })).toBeVisible()
}

test.describe('marker-owned packaged maintenance runtime', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(!enabled, 'Runs only through scripts/test-cmd-maintenance.ps1 with a verified candidate attachment.')

  test.beforeAll(async () => {
    context = loadMaintenanceAttachment()
    const healthResponse = await fetch(`${context.attachment.base_url}/api/health`)
    const versionResponse = await fetch(`${context.attachment.base_url}/api/version`)
    expect(healthResponse.status).toBe(200)
    expect(versionResponse.status).toBe(200)
    const health = await healthResponse.json()
    const version = await versionResponse.json()
    expect(health.status).toBe('ok')
    expect(version.version).toBe(context.runtime.version)
    expect(version.build).toBe(context.runtime.build)
    observations.push({
      scenario: 'candidate-runtime-identity', status: 'passed',
      observable: {
        health_status: health.status, version: version.version, build: version.build,
        executable_sha256: context.runtime.executable_sha256,
        candidate_zip_sha256: context.attachment.candidate_zip_sha256,
      },
    })
  })

  test.afterEach(async ({}, testInfo) => {
    observations.push({
      scenario: sha256Text(testInfo.title).slice(0, 16),
      status: testInfo.status === testInfo.expectedStatus ? 'passed' : 'failed',
      observable: { expected_status: testInfo.expectedStatus, actual_status: testInfo.status },
    })
  })

  test.afterAll(async () => {
    if (!context) return
    const browserRoot = path.dirname(context.evidencePath)
    if (!existsSync(browserRoot)) mkdirSync(browserRoot)
    const receipt = {
      schema: 'iz-cna-maintenance-browser-evidence-v1',
      qualification_mode: context.attachment.qualification_mode,
      release_qualification: context.attachment.qualification_mode === 'release',
      run_id: context.attachment.run_id,
      case_id: context.attachment.case_id,
      tier: context.attachment.tier,
      status: observations.every((item) => item.status === 'passed') ? 'passed' : 'failed',
      source_revision: context.attachment.expected_source_revision,
      runtime: {
        version: context.runtime.version,
        build: context.runtime.build,
        installer_revision: context.runtime.installer_revision,
        executable_sha256: context.runtime.executable_sha256,
        data_identity: context.runtime.data_identity,
        instance_id: context.runtime.instance_id,
      },
      candidate_zip_sha256: context.attachment.candidate_zip_sha256,
      observations,
      screenshots_written: 0,
      trace_written: false,
      synthetic_data_only: true,
      completed_utc: new Date().toISOString(),
    }
    const descriptor = openSync(context.evidencePath, 'wx')
    try { writeFileSync(descriptor, `${JSON.stringify(receipt, null, 2)}\n`, { encoding: 'utf8' }) } finally { closeSync(descriptor) }
  })

  test('admin login loads bundled operational and clinical views', async ({ page }) => {
    await signIn(
      page,
      requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_USERNAME'),
      requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_PASSWORD'),
    )
    const views = [
      ['Status Dashboard', 'Status dashboard'],
      ['Patient Roster', 'Patient roster'],
      ['Manual Upload', 'Point-in-time treatment-plan evidence'],
      ['Treatment Plans Roster', 'Treatment Plans Roster'],
      ['Help', 'Production 1.0 workflow'],
    ]
    for (const [button, heading] of views) {
      await page.getByRole('button', { name: button, exact: true }).click()
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    }
    await expect(page.locator('footer')).toContainText(context.runtime.version)
    await expect(page.locator('footer')).toContainText(context.runtime.build)
  })

  test('existing treatment plans remain readable with their checklist evidence', async ({ page }) => {
    await signIn(
      page,
      requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_USERNAME'),
      requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_PASSWORD'),
    )
    await page.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
    await expect(page.getByRole('button', { name: /^Open treatment plan / }).first()).toBeVisible()
    const rows = page.getByRole('row').filter({ has: page.getByRole('button', { name: /^Open treatment plan / }) })
    expect(await rows.count()).toBeGreaterThanOrEqual(3)
    await page.getByRole('button', { name: /^Open treatment plan / }).first().click()
    await expect(page.getByRole('heading', { name: /^Treatment Plan ID / })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Checklist Evidence', exact: true })).toBeVisible()
    await expect(page.getByLabel('Checklist criteria').getByRole('button')).toHaveCount(42)
  })

  test('supported APIs preserve accounts, settings, encryption flags, workflow and audit semantics', async ({ request }) => {
    const login = await request.post('/api/auth/login', {
      data: {
        username: requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_USERNAME'),
        password: requiredCredential('IZ_CNA_MAINTENANCE_ADMIN_PASSWORD'),
      },
    })
    expect(login.status()).toBe(200)
    const loginBody = await login.json()
    const headers = { authorization: `Bearer ${loginBody.access_token}` }
    const responses = await Promise.all([
      request.get('/api/users', { headers }),
      request.get('/api/settings', { headers }),
      request.get('/api/api-configuration', { headers }),
      request.get('/api/workflow-definitions', { headers }),
      request.get('/api/v2/treatment-plans', { headers }),
      request.get('/api/audit/verify', { headers }),
    ])
    for (const response of responses) expect(response.status()).toBe(200)
    const [users, settings, apiConfiguration, workflows, plans, audit] = await Promise.all(responses.map((response) => response.json()))
    expect(users).toHaveLength(4)
    expect(new Set(users.map((user) => user.role))).toEqual(new Set(['admin', 'office_manager', 'counselor', 'viewer']))
    expect(settings.facility_timezone).toBe('America/New_York')
    expect(settings.treatment_plan_loc_change_window_validated).toBe(false)
    expect(apiConfiguration.client_id_configured).toBe(true)
    expect(apiConfiguration.client_secret_configured).toBe(true)
    expect(apiConfiguration.api_enabled).toBe(false)
    expect(apiConfiguration.treatment_plan_sync_enabled).toBe(false)
    expect(apiConfiguration.treatment_plan_sync_approved).toBe(false)
    expect(apiConfiguration).not.toHaveProperty('client_secret')
    expect(apiConfiguration).not.toHaveProperty('access_token')
    expect(workflows.some((workflow) => workflow.workflow_key === 'qa-beta3-upgrade')).toBe(true)
    expect(plans.items).toHaveLength(3)
    expect(new Set(plans.items.map((plan) => plan.patient_id)).size).toBe(2)
    expect(audit.valid).toBe(true)
  })

  test('counselor login retains the correction queue and denied management boundary', async ({ page, request }) => {
    const username = requiredCredential('IZ_CNA_MAINTENANCE_COUNSELOR_USERNAME')
    const password = requiredCredential('IZ_CNA_MAINTENANCE_COUNSELOR_PASSWORD')
    await signIn(page, username, password)
    await page.getByRole('button', { name: 'Corrections', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Corrections', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Open Returns', exact: true })).toBeVisible()
    const login = await request.post('/api/auth/login', { data: { username, password } })
    expect(login.status()).toBe(200)
    const token = (await login.json()).access_token
    const plans = await request.get('/api/v2/treatment-plans', { headers: { authorization: `Bearer ${token}` } })
    expect(plans.status()).toBe(200)
    const first = (await plans.json()).items[0]
    const denied = await request.post(`/api/v2/treatment-plans/${encodeURIComponent(first.patient_id)}/manager-actions`, {
      headers: { authorization: `Bearer ${token}` },
      data: {
        plan_version_id: first.plan_version_id,
        patient_record_id: first.patient_record_id,
        source_mode: first.source_mode,
        treatment_plan_id: first.treatment_plan_id,
        criterion_id: 'confirm_current_loc',
        action: 'approve',
        comment: 'Synthetic maintenance denial probe.',
        override_reason: '',
        assigned_counselor_username: '',
      },
    })
    expect(denied.status()).toBe(403)
  })
})
