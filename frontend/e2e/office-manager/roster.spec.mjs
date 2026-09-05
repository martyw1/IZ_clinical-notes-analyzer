import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'
import { csvHeaders, detail, exportList, fact, failureBoundary, identity, importAggregate, list, openRoster, planRow, rosterSearchLabel, sortedIds } from './task7TestUtils.mjs'

test('full filtered exports include off-screen authorized matches for All Manual and Alleva @happy', async ({ page }) => {
  test.setTimeout(120_000)
  // Given: actual authorized current plans plus a bounded population larger than one viewport.
  const api = await apiFor()
  const fixture = fixtureContract()
  const patientId = 'TASK7-EXPORT-001', fullName = 'Synthetic Task7 Export Person', reference = 'TASK7-EXPORT-REF'
  let phase = 'initial-read'
  try {
    const initial = await list(api)
    const imported = []
    phase = 'population-import'
    for (let index = 0; index < 18; index += 1) imported.push(await importAggregate(api, {
      patientId, planId: 'task7-export-' + String(index).padStart(2, '0'), fullName, reference, serviceDate: '2026-08-17',
    }))
    phase = 'population-check'
    const all = await list(api)
    expect(sortedIds(all.map(item => item.plan_version_id))).toEqual(sortedIds([...initial, ...imported].map(item => item.plan_version_id)))
    expect(all.some(item => item.plan_version_id === fixture.plans.facilityCollision.plan_version_id)).toBe(false)
    phase = 'login'
    await login(page)
    phase = 'roster'
    await openRoster(page)
    const observations = []
    let viewportBoundary
    for (const source of ['all', 'manual_upload', 'alleva_rest_api']) {
      phase = 'source-filter'
      await page.getByRole('combobox', { name: 'Source filter', exact: true }).selectOption(source)
      await expect(page.getByLabel(rosterSearchLabel, { exact: true })).toBeVisible()
      for (const [kind, term] of [['none', ''], ['mrn', fixture.plans.primaryV2.patient_id], ['name', fullName.toUpperCase()], ['reference', reference.toLowerCase()]]) {
        phase = 'local-filter'
        await page.getByLabel(rosterSearchLabel, { exact: true }).fill(term)
        const expected = all.filter(item => (source === 'all' || item.source_mode === source)
          && (kind === 'none' || (kind === 'mrn' ? item.patient_id === term : imported.some(plan => plan.plan_version_id === item.plan_version_id))))
        await expect(page.locator('tr[data-plan-version-id]')).toHaveCount(expected.length)
        if (source === 'all' && kind === 'name') {
          phase = 'viewport-boundary'
          await page.evaluate(() => window.scrollTo(0, 0))
          const row = page.locator('tr[data-plan-version-id]').last()
          const bounds = await row.boundingBox()
          expect(bounds).not.toBeNull()
          const height = page.viewportSize().height
          expect(bounds.y, 'Last matching row is below the viewport before export').toBeGreaterThan(height)
          viewportBoundary = { matchingCount: expected.length, viewportHeight: height, lastRowY: bounds.y,
            offscreenVersionId: Number(await row.getAttribute('data-plan-version-id')), paginationControlsPresent: false }
          await capture(page, 'task-7-roster-offscreen.png')
        }
        // When: the shipped UI exports the complete filter, not only visible rows.
        phase = 'filtered-export'
        const result = await exportList(page, expected.map(item => item.plan_version_id), source)
        expect(result.csv.text.includes(fullName)).toBe(false)
        expect(result.csv.text.includes(reference)).toBe(false)
        observations.push({ filterKind: kind, ...result.evidence })
        if (kind === 'none') await capture(page, 'task-7-roster-' + source + '.png')
      }
    }
    phase = 'empty-export'
    await page.getByRole('combobox', { name: 'Source filter', exact: true }).selectOption('all')
    await page.getByLabel(rosterSearchLabel, { exact: true }).fill('no-synthetic-plan-matches-this')
    await expect(page.locator('tr[data-plan-version-id]')).toHaveCount(0)
    const empty = await exportList(page, [])
    expect(empty.csv.rows).toHaveLength(0)
    // Then: header-only empty export and all exact populations have real downloaded-byte proof.
    expect(viewportBoundary).toBeDefined()
    writeEvidence('task-7-roster.json', { actualBackend: true, initialIds: initial.map(item => item.plan_version_id),
      importedIds: imported.map(item => item.plan_version_id), observations, viewportBoundary, empty: empty.evidence,
      csvHeaders, nameAndReferenceExcluded: true, searchTextNeverSubmitted: true, noPaginationFeature: true })
  } catch (error) { failureBoundary(error, 'roster-happy', phase); throw error } finally { await api.dispose() }
})

test('same MRN source and facility rows stay distinct and assignment never grants membership @edge', async ({ page }) => {
  const fixture = fixtureContract(), manager = await apiFor(), counselor = await apiFor('counselor')
  const alleva = fixture.plans.sourceCollision, forbidden = fixture.plans.facilityCollision
  let phase = 'login'
  try {
    const rowsResponse = await manager.get('/api/v2/treatment-plans')
    expect(rowsResponse.status()).toBe(200)
    const currentManual = (await rowsResponse.json()).items.find(row => row.patient_record_id === fixture.plans.primaryV2.patient_record_id
      && row.source_mode === fixture.plans.primaryV2.source_mode && row.treatment_plan_id === fixture.plans.primaryV2.plan_id)
    expect(currentManual).toBeDefined()
    const manual = { ...currentManual, plan_id: currentManual.treatment_plan_id }
    await login(page)
    phase = 'roster'
    await openRoster(page)
    await expect(planRow(page, manual)).toBeVisible()
    await expect(planRow(page, alleva)).toBeVisible()
    await expect(planRow(page, forbidden)).toHaveCount(0)
    phase = 'denied-exports'
    const denied = []
    for (const [ids, source, status] of [[[manual.plan_version_id, forbidden.plan_version_id], undefined, 403],
      [[manual.plan_version_id, 2147483647], undefined, 404], [[manual.plan_version_id], 'alleva_rest_api', 404]]) {
      const response = await manager.post('/api/v2/exports/treatment-plans.csv', { data: { plan_version_ids: ids, ...(source ? { source_mode: source } : {}) } })
      expect(response.status()).toBe(status)
      expect(response.headers()['content-type']).not.toContain('text/csv')
      denied.push({ ids, source, status })
    }
    phase = 'patient-record'
    await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
    await expect(page.getByRole('combobox', { name: 'Source filter', exact: true })).toHaveValue('all')
    const patientRow = page.locator('tr[data-patient-record-id="' + alleva.patient_record_id + '"]')
    const nested = patientRow.getByLabel('Treatment plans for MRN ' + alleva.patient_id, { exact: true })
    await expect(nested.locator('option[value="' + alleva.plan_version_id + '"]')).toContainText('Alleva')
    const received = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/patients/' + alleva.patient_id)
    const started = Date.now()
    await patientRow.getByRole('button', { name: /Open patient record/ }).click()
    const response = await received
    expect(response.status()).toBe(200)
    expect(new URL(response.url()).searchParams.get('patient_record_id')).toBe(String(alleva.patient_record_id))
    await expect(fact(page, 'Patient record')).toHaveText(String(alleva.patient_record_id))
    await expect(page.getByText('No patient snapshot is available for this record.', { exact: true })).toBeVisible()
    await expect(page.getByText('Loading patient record...', { exact: true })).toHaveCount(0)
    const settleMs = Date.now() - started
    await capture(page, 'task-7-patient-no-snapshot.png')
    phase = 'assignment'
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await login(page, 'admin')
    await page.getByRole('button', { name: 'Users', exact: true }).click()
    const selector = page.getByRole('combobox', { name: 'Patient record assignment', exact: true })
    await expect(selector.locator('option[value="' + forbidden.patient_record_id + ':manual_upload"]')).toContainText('record ' + forbidden.patient_record_id)
    await selector.selectOption(forbidden.patient_record_id + ':manual_upload')
    await page.getByRole('combobox', { name: 'Counselor assignment', exact: true }).selectOption(fixture.users.counselor.username)
    let facilityGrants = 0
    const observe = request => { if (request.method() === 'PUT' && new URL(request.url()).pathname.includes('/facilities/')) facilityGrants += 1 }
    page.on('request', observe)
    const assignmentResponse = page.waitForResponse(response => new URL(response.url()).pathname.startsWith('/api/patient-assignments/') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Assign patient', exact: true }).click()
    const assignment = await assignmentResponse
    expect(assignment.status()).toBe(409)
    expect(new URL(assignment.url()).searchParams.get('patient_record_id')).toBe(String(forbidden.patient_record_id))
    expect(new URL(assignment.url()).searchParams.get('source_mode')).toBe('manual_upload')
    await expect(page.getByRole('alert')).toContainText('conflicts with the current record')
    expect((await counselor.get('/api/v2/treatment-plans/' + forbidden.patient_id, { params: identity(forbidden) })).status()).toBe(403)
    expect(facilityGrants).toBe(0)
    await capture(page, 'task-7-assignment-membership-denied.png')
    await selector.selectOption(manual.patient_record_id + ':manual_upload')
    const allowed = page.waitForResponse(response => new URL(response.url()).pathname.startsWith('/api/patient-assignments/') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Assign patient', exact: true }).click()
    expect((await allowed).status()).toBe(200)
    await expect(page.getByRole('status')).toHaveText('Patient assigned to counselor.')
    page.off('request', observe)
    await capture(page, 'task-7-assignment-exact.png')
    phase = 'help'
    await page.getByRole('button', { name: 'Help', exact: true }).click()
    await expect(page.getByText(/a new import never silently replaces your selection/)).toBeVisible()
    const helpViewport = page.viewportSize()
    const helpLayouts = []
    try {
      for (const width of [375, 768]) {
        await page.setViewportSize({ width, height: 900 })
        await expect(page.getByText(/a new import never silently replaces your selection/)).toBeVisible()
        const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
        await capture(page, `task-10-help-${width}.png`)
        helpLayouts.push({ width, fits })
        expect(fits, `Help fits at ${width}`).toBe(true)
      }
    } finally { await page.setViewportSize(helpViewport) }
    writeEvidence('task-10-help-responsive.json', { interaction: 'SCRIPTED Playwright', states: helpLayouts })
    await capture(page, 'task-7-help.png')
    writeEvidence('task-7-roster-error.json', { actualBackend: true, manual: identity(manual), alleva: identity(alleva),
      forbidden: identity(forbidden), denied, emptySnapshotStatus: response.status(), emptySnapshotSettleMs: settleMs,
      assignmentBlockedStatus: assignment.status(), permittedAssignmentStatus: 200, facilityGrants,
      forbiddenCounselorReadStillDenied: true, nestedOptionsCarryExactVersion: true })
  } catch (error) { failureBoundary(error, 'roster-edge', phase); throw error } finally { await manager.dispose(); await counselor.dispose() }
})
