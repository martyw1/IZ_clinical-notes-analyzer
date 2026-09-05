import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'
import { assertQuery, detail, downloadBytes, expectSelected, failureBoundary, hash, identity, importAggregate, openPlan, openRoster, parseCsv, planRow } from './task7TestUtils.mjs'

async function paintSettled(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
}

async function currentVersion(api, seeded) {
  const response = await api.get('/api/v2/treatment-plans')
  expect(response.status()).toBe(200)
  const plan = (await response.json()).items.find(row => row.patient_record_id === seeded.patient_record_id
    && row.source_mode === seeded.source_mode && row.treatment_plan_id === seeded.plan_id)
  expect(plan).toBeDefined()
  return { ...plan, plan_id: plan.treatment_plan_id }
}

async function holdActualResponse(page, matches) {
  let release, finish, started = 0, status = 0
  const gate = new Promise(resolve => { release = resolve })
  const finished = new Promise(resolve => { finish = resolve })
  const handler = async route => {
    const response = await route.fetch()
    status = response.status()
    started += 1
    await gate
    try { await route.fulfill({ response }) } finally { finish() }
  }
  await page.route(matches, handler)
  return { release, finished, get started() { return started }, get status() { return status }, remove: () => page.unroute(matches, handler) }
}

test('explicit old version survives new import and binds UI actions correction and selected CSV @happy', async ({ page }) => {
  test.setTimeout(120_000)
  // Given: historical and current versions with the same patient, external ID and source.
  const fixture = fixtureContract(), api = await apiFor(), counselor = await apiFor('counselor')
  const old = fixture.plans.primaryV1
  let phase = 'initial-read'
  try {
    const current = await currentVersion(api, fixture.plans.primaryV2)
    const oldBefore = await detail(api, old), seededCurrentBefore = await detail(api, fixture.plans.primaryV2)
    const currentBefore = await detail(api, current)
    phase = 'login'
    await login(page)
    const historyRequest = page.waitForRequest(request => {
      const url = new URL(request.url())
      return url.pathname === '/api/v2/treatment-plans' && url.searchParams.get('include_history') === 'true'
    })
    phase = 'history'
    await openPlan(page, current)
    const historyUrl = new URL((await historyRequest).url())
    expect(historyUrl.searchParams.get('patient_record_id')).toBe(String(old.patient_record_id))
    expect(historyUrl.searchParams.get('source_mode')).toBe(old.source_mode)
    expect(historyUrl.searchParams.get('treatment_plan_id')).toBe(old.plan_id)
    const selector = page.getByLabel('Saved treatment-plan version', { exact: true })
    await expect(selector.locator('option[value="' + old.plan_version_id + '"]')).toContainText('historical')
    await selector.selectOption(String(old.plan_version_id))
    await expectSelected(page, old)
    phase = 'new-import'
    const fresh = await importAggregate(api, { patientId: old.patient_id, planId: old.plan_id, stamp: '2026-09-04T13:00:00Z' })
    expect(fresh.plan_version_id).not.toBe(old.plan_version_id)
    await page.getByRole('button', { name: 'Refresh saved versions', exact: true }).click()
    await expect(selector.locator('option[value="' + fresh.plan_version_id + '"]')).toContainText('current')
    await expect(selector).toHaveValue(String(old.plan_version_id))
    await expectSelected(page, old)
    await capture(page, 'task-7-history-selected-old.png')
    const freshBefore = await detail(api, fresh)
    phase = 'manager-action'
    const criterion = oldBefore.criteria_results.find(item => item.criterion_id === 'confirm_current_loc')
    expect(criterion).toBeDefined()
    await page.locator('.criterion-row').filter({ has: page.getByText(criterion.criterion_title, { exact: true }) }).click()
    await page.getByLabel('Manager comment', { exact: true }).fill('Synthetic exact saved-version action.')
    await page.getByLabel('Override reason', { exact: true }).fill('Synthetic exact saved-version override reason.')
    const actions = [
      ['Approve criterion', 'approve', 'Approval saved as a manager disposition.'],
      ['Save comment', 'comment', 'Manager comment saved without changing deterministic results.'],
      ['Save override', 'override', 'Override saved with required reason and audit event.'],
      ['Return for correction', 'return_for_correction', 'Criterion returned for correction with manager comment.'],
    ]
    const observed = []
    // When: every manager action is made through the selected historical detail.
    for (const [button, action, message] of actions) {
      const response = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/manager-actions') && response.request().method() === 'POST')
      await page.getByRole('button', { name: button, exact: true }).click()
      const saved = await response
      expect(saved.status()).toBe(200)
      const body = saved.request().postDataJSON()
      expect(body).toMatchObject({ ...identity(old), criterion_id: criterion.criterion_id, action })
      await expect(page.locator('.manager-actions [role="status"]')).toHaveText(message)
      await expectSelected(page, old)
      observed.push({ ...identity(old), action, criterionId: body.criterion_id, status: saved.status() })
    }
    const oldAfter = await detail(api, old)
    expect(oldAfter.source_last_updated).toBe(oldBefore.source_last_updated)
    expect(oldAfter.manager_reviews.slice(-4).map(item => item.action)).toEqual(actions.map(item => item[1]))
    expect((await detail(api, fixture.plans.primaryV2)).manager_reviews).toEqual(seededCurrentBefore.manager_reviews)
    expect((await detail(api, current)).manager_reviews).toEqual(currentBefore.manager_reviews)
    expect((await detail(api, fresh)).manager_reviews).toEqual(freshBefore.manager_reviews)
    phase = 'selected-csv'
    const csvRequest = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/checklist-evidence.csv'))
    const bytes = await downloadBytes(page, () => page.getByRole('button', { name: 'Export minimum-necessary checklist evidence', exact: true }).click())
    assertQuery((await csvRequest).url(), old)
    const csv = parseCsv(bytes)
    expect(csv.rows).toHaveLength(42)
    for (const row of csv.rows) {
      expect(row.plan_version_id).toBe(String(old.plan_version_id))
      expect(row.patient_record_id).toBe(String(old.patient_record_id))
      expect(row.source_mode).toBe(old.source_mode)
      expect(row.treatment_plan_id).toBe(old.plan_id)
    }
    await capture(page, 'task-7-selected-actions.png')
    phase = 'correction'
    const queueResponse = await counselor.get('/api/v2/corrections')
    expect(queueResponse.status()).toBe(200)
    const work = (await queueResponse.json()).items.find(item => item.plan_version_id === old.plan_version_id && item.criterion_id === criterion.criterion_id)
    expect(work).toMatchObject(identity(old))
    expect(Number.isSafeInteger(work.work_item_id) && work.work_item_id > 0).toBe(true)
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await login(page, 'counselor')
    await page.getByRole('button', { name: 'Corrections', exact: true }).click()
    const item = page.locator('li[data-plan-version-id="' + old.plan_version_id + '"]')
    await expect(item).toHaveCount(1)
    await expect(item).toHaveAttribute('data-patient-record-id', String(old.patient_record_id))
    const correctionViewport = page.viewportSize()
    const correctionLayouts = []
    try {
      for (const width of [375, 768]) {
        await page.setViewportSize({ width, height: 900 })
        await expect(item.getByLabel('Resolution note', { exact: true })).toBeVisible()
        const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
        await capture(page, `task-10-corrections-${width}.png`)
        correctionLayouts.push({ width, fits })
        expect(fits, `Corrections fits at ${width}`).toBe(true)
      }
    } finally { await page.setViewportSize(correctionViewport) }
    writeEvidence('task-10-corrections-responsive.json', { interaction: 'SCRIPTED Playwright', states: correctionLayouts })
    await item.getByLabel('Resolution note', { exact: true }).fill('Synthetic exact-work-item correction.')
    await capture(page, 'task-7-correction-selected.png')
    const submissionResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/correction-submissions') && response.request().method() === 'POST')
    await item.getByRole('button', { name: 'Submit correction', exact: true }).click()
    const submitted = await submissionResponse
    expect(submitted.status()).toBe(200)
    expect(submitted.request().postDataJSON()).toMatchObject({ ...identity(old), work_item_id: work.work_item_id, criterion_id: work.criterion_id })
    await expect(page.getByRole('status')).toHaveText('Correction submitted for manager review.')
    await expect(item).toHaveCount(0)
    await capture(page, 'task-7-correction-submitted.png')
    // Then: the persisted correction is on the selected old version only.
    expect((await detail(api, old)).manager_reviews.at(-1).action).toBe('correction_submitted')
    expect((await detail(api, current)).manager_reviews).toEqual(currentBefore.manager_reviews)
    expect((await detail(api, fresh)).manager_reviews).toEqual(freshBefore.manager_reviews)
    writeEvidence('task-7-selection.json', { actualUiActions: true, old: identity(old), fresh: identity(fresh),
      explicitHistoryQuery: Object.fromEntries(historyUrl.searchParams), oldSelectionPreserved: true, observed,
      selectedCsvRows: csv.rows.length, selectedCsvSha256: hash(bytes), workItemId: work.work_item_id,
      correctionStatus: submitted.status(), seededAndCurrentOtherVersionsUnchanged: true, oldSourceTimestampPreserved: true })
  } catch (error) { failureBoundary(error, 'selection-happy', phase); throw error } finally { await api.dispose(); await counselor.dispose() }
})

test('late actual fetch and save cannot repaint another selection and expired sessions clear it @edge', async ({ page }) => {
  test.setTimeout(120_000)
  const fixture = fixtureContract(), alleva = fixture.plans.sourceCollision
  const api = await apiFor()
  const holds = []
  let phase = 'initial-read'
  try {
    const manual = await currentVersion(api, fixture.plans.primaryV2)
    const manualBefore = await detail(api, manual), allevaBefore = await detail(api, alleva)
    phase = 'login'
    await login(page)
    await page.getByRole('button', { name: 'Treatment Plan Detail', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Select a treatment plan', exact: true })).toBeVisible()
    await openRoster(page)
    phase = 'late-read'
    const matchingManualGet = url => url.pathname.startsWith('/api/v2/treatment-plans/') && url.searchParams.get('plan_version_id') === String(manual.plan_version_id)
    const oldRead = await holdActualResponse(page, matchingManualGet)
    holds.push(oldRead)
    await planRow(page, manual).getByRole('button', { name: /Open treatment plan/ }).click()
    await expect.poll(() => oldRead.started).toBe(1)
    expect(oldRead.status).toBe(200)
    await openRoster(page)
    await planRow(page, alleva).getByRole('button', { name: /Open treatment plan/ }).click()
    await expectSelected(page, alleva)
    oldRead.release()
    await oldRead.finished
    await paintSettled(page)
    await expectSelected(page, alleva)
    await oldRead.remove()
    await capture(page, 'task-7-detail-late-read.png')
    // Given: an actual committed old-version POST whose response is still held at the HTTP boundary.
    phase = 'late-save'
    await openPlan(page, manual)
    await page.getByLabel('Manager comment', { exact: true }).fill('Synthetic late response must not repaint.')
    await page.getByLabel('Override reason', { exact: true }).fill('Synthetic old draft.')
    let manualGets = 0
    const observe = request => { if (request.method() === 'GET' && matchingManualGet(new URL(request.url()))) manualGets += 1 }
    page.on('request', observe)
    const oldSave = await holdActualResponse(page, url => url.pathname.endsWith('/manager-actions'))
    holds.push(oldSave)
    await page.getByRole('button', { name: 'Save comment', exact: true }).click()
    await expect.poll(() => oldSave.started).toBe(1)
    expect(oldSave.status).toBe(200)
    await openRoster(page)
    await planRow(page, alleva).getByRole('button', { name: /Open treatment plan/ }).click()
    await expectSelected(page, alleva)
    await expect(page.getByLabel('Manager comment', { exact: true })).toHaveValue('')
    await expect(page.getByLabel('Override reason', { exact: true })).toHaveValue('')
    oldSave.release()
    await oldSave.finished
    await paintSettled(page)
    await expectSelected(page, alleva)
    await expect(page.locator('.manager-actions [role="status"]')).toHaveCount(0)
    expect(manualGets, 'Late old save must not refresh its abandoned selection').toBe(0)
    page.off('request', observe)
    await oldSave.remove()
    const manualAfter = await detail(api, manual)
    expect(manualAfter.manager_reviews.length).toBe(manualBefore.manager_reviews.length + 1)
    expect((await detail(api, alleva)).manager_reviews).toEqual(allevaBefore.manager_reviews)
    await capture(page, 'task-7-detail-late-save.png')
    // When: authentication expires while an actual old-session detail response is held.
    phase = 'session-expiry'
    const sessionRead = await holdActualResponse(page, matchingManualGet)
    holds.push(sessionRead)
    await openRoster(page)
    await planRow(page, manual).getByRole('button', { name: /Open treatment plan/ }).click()
    await expect.poll(() => sessionRead.started).toBe(1)
    expect(sessionRead.status).toBe(200)
    const expiryRoute = url => url.pathname === '/api/v2/dashboard'
    await page.route(expiryRoute, route => route.fulfill({ status: 401, json: { detail: 'Authentication required' } }))
    await page.getByRole('button', { name: 'Status Dashboard', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible()
    await page.unroute(expiryRoute)
    await login(page)
    await page.getByRole('button', { name: 'Treatment Plan Detail', exact: true }).click()
    sessionRead.release()
    await sessionRead.finished
    await paintSettled(page)
    await sessionRead.remove()
    await expect(page.getByRole('heading', { name: 'Select a treatment plan', exact: true })).toBeVisible()
    await expect(page.locator('.treatment-plan-document')).toHaveCount(0)
    await capture(page, 'task-7-expired-selection-cleared.png')
    // Then: a mismatched exact patient response also settles explicitly instead of spinning forever.
    phase = 'mismatched-record'
    const wrongPatient = url => url.pathname === '/api/v2/patients/' + manual.patient_id
    await page.route(wrongPatient, async route => {
      const response = await route.fetch()
      const body = await response.json()
      await route.fulfill({ response, json: { ...body, patient_record_id: alleva.patient_record_id } })
    })
    await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
    await page.locator('tr[data-patient-record-id="' + manual.patient_record_id + '"]').getByRole('button', { name: /Open patient record/ }).click()
    await expect(page.getByRole('alert')).toHaveText('The returned record does not match the selected patient record. Refresh the roster.')
    await expect(page.getByText('Loading patient record...', { exact: true })).toHaveCount(0)
    await capture(page, 'task-7-patient-identity-error.png')
    await page.unroute(wrongPatient)
    writeEvidence('task-7-selection-error.json', { actualDelayedReadsAndSaves: true, selectedAfterLateRead: identity(alleva),
      selectedAfterLateSave: identity(alleva), abandonedSelectionRefreshes: manualGets, oldDraftsCleared: true,
      simulated401ClearedSelection: true, reloginStartsWithoutSelection: true, mismatchedResponseSimulationSettled: true,
      oldSessionReadStatus: sessionRead.status, lateOldSessionReadIgnoredAfterLogin: true,
      mockOnlyAuthAndMismatchBoundaries: true, persistedOldVersionActionDelta: manualAfter.manager_reviews.length - manualBefore.manager_reviews.length,
      otherVersionHistoryUnchanged: true })
  } catch (error) { failureBoundary(error, 'selection-edge', phase); throw error } finally {
    for (const hold of holds) { hold.release(); await hold.remove() }
    await api.dispose()
  }
})
