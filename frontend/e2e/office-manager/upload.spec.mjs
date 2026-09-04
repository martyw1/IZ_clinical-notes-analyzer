import { readFileSync } from 'node:fs'
import { test, expect, login, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

const forms = [
  { kind: 'json', label: 'Normalized V2 aggregate JSON', form: 'Normalized aggregate import', submit: 'Import treatment-plan aggregate', endpoint: '/api/v2/manual-uploads/treatment-plan-aggregate' },
  { kind: 'binder', label: 'Treatment-plan binder files', form: 'Treatment-plan binder import', submit: 'Upload and securely process binder', endpoint: '/api/v2/manual-uploads/treatment-plan-file' },
]

async function openUpload(page) {
  await login(page)
  await page.getByRole('button', { name: 'Manual Upload', exact: true }).click()
}

async function selectedCount(page, label) {
  return page.getByLabel(label, { exact: true }).evaluate(input => input.files.length)
}

test('real JSON and binder success reset native and selected state @happy', async ({ page }) => {
  // Given: real authentication and owned synthetic aggregate/binder fixtures.
  await openUpload(page)
  const observed = []
  const fixture = fixtureContract()
  for (const entry of forms) {
    const form = page.getByRole('form', { name: entry.form })
    await page.getByLabel(entry.label, { exact: true }).setInputFiles(entry.kind === 'json' ? fixture.files.aggregate : fixture.files.binder)
    let requests = 0
    const count = request => { if (new URL(request.url()).pathname === entry.endpoint) requests += 1 }
    page.on('request', count)
    // When: the file is imported through the actual backend.
    const response = page.waitForResponse(response => new URL(response.url()).pathname === entry.endpoint)
    await form.getByRole('button', { name: entry.submit, exact: true }).click()
    const status = (await response).status()
    expect(status).toBe(201)
    await expect(form.getByRole('status')).toBeVisible()
    // Then: native input is empty and submitting again cannot reuse an old object.
    expect(await selectedCount(page, entry.label)).toBe(0)
    await form.getByRole('button', { name: entry.submit, exact: true }).click()
    await expect(form.getByRole('alert')).toBeVisible()
    expect(requests).toBe(1)
    page.off('request', count)
    observed.push({ kind: entry.kind, status, requestCount: requests, nativeCount: 0, staleObjectResubmitted: false })
  }
  const widths = []
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 1000 })
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
    expect(fits).toBe(true)
    await page.getByRole('button', { name: forms[0].submit, exact: true }).focus()
    await capture(page, `task-6-upload-${width}.png`)
    widths.push({ width, documentFits: fits, keyboardFocus: true })
  }
  writeEvidence('task-6-upload.json', { cases: observed, widths, realBackendImports: true })
})

test('remove clear same-file retry and duplicate submit preserve native state @edge', async ({ page }) => {
  // Given: synthetic files and recoverable first-request failures for each import form.
  await openUpload(page)
  const fixture = fixtureContract()
  const observed = []
  for (const entry of forms) {
    const input = page.getByLabel(entry.label, { exact: true })
    const form = page.getByRole('form', { name: entry.form })
    const file = entry.kind === 'json' ? fixture.files.aggregate : { name: 'synthetic-binder.txt', mimeType: 'text/plain', buffer: readFileSync(fixture.files.binder) }
    await input.setInputFiles(file)
    if (entry.kind === 'binder') {
      await input.setInputFiles([{ ...file, name: 'synthetic-extra.txt' }, file])
      await form.getByRole('button', { name: 'Remove synthetic-extra.txt', exact: true }).click()
      expect(await selectedCount(page, entry.label)).toBe(1)
      await form.getByRole('button', { name: 'Remove synthetic-binder.txt', exact: true }).click()
      expect(await selectedCount(page, entry.label)).toBe(0)
      await input.setInputFiles(file)
    }
    await form.getByRole('button', { name: entry.kind === 'json' ? 'Clear JSON selection' : 'Clear selection', exact: true }).click()
    expect(await selectedCount(page, entry.label)).toBe(0)
    await input.setInputFiles(file)
    let requests = 0
    let release
    const held = new Promise(resolve => { release = resolve })
    await page.route(`**${entry.endpoint}`, async route => {
      requests += 1
      if (requests === 1) return route.fulfill({ status: 500, json: { detail: 'SYNTHETIC-PRIVATE-UPLOAD-ERROR' } })
      await held
      return route.continue()
    })
    // When: the first import fails and retry gets duplicate native submit events.
    await form.getByRole('button', { name: entry.submit, exact: true }).click()
    await expect(form.getByRole('alert')).toBeVisible()
    expect((await form.innerText()).includes('SYNTHETIC-PRIVATE-UPLOAD-ERROR')).toBe(false)
    expect(await selectedCount(page, entry.label)).toBe(1)
    const response = page.waitForResponse(response => new URL(response.url()).pathname === entry.endpoint && response.status() === 201)
    await form.evaluate(element => { element.requestSubmit(); element.requestSubmit() })
    await expect.poll(() => requests).toBe(2)
    await expect(input).toBeDisabled()
    release()
    expect((await response).status()).toBe(201)
    // Then: one retry succeeds; both representations clear, with no duplicate import.
    await expect(form.getByRole('status')).toBeVisible()
    expect(requests).toBe(2)
    expect(await selectedCount(page, entry.label)).toBe(0)
    await page.unroute(`**${entry.endpoint}`)
    observed.push({ kind: entry.kind, failedSelectionKept: true, clearRechoose: true,
      removedNativeFiles: entry.kind === 'binder', requestsIncludingFailedAttempt: requests, successCount: 1, nativeCountAfterSuccess: 0 })
  }
  await capture(page, 'task-6-upload-retry.png')
  writeEvidence('task-6-upload-error.json', { cases: observed, faultInjectionAtHttpBoundary: true, successfulRetriesUseRealBackend: true })
})
