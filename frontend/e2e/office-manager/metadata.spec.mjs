import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'
import { assertQuery, detail, downloadBytes, exportList, fact, failureBoundary, hash, identity, importBinder, list, openPlan, openRoster, planRow, query, rosterSearchLabel, sourceSnapshot } from './task7TestUtils.mjs'

test('actual manual metadata remains optional and names stay on the exact authorized source row @happy', async ({ page }) => {
  // Given: a real manual binder with optional metadata and a colliding Alleva MRN.
  const fixture = fixtureContract(), api = await apiFor(), admin = await apiFor('admin')
  const fullName = 'Synthetic Task7 Metadata Person', reference = 'TASK7-PRIVATE-REFERENCE'
  const bytes = Buffer.from('MRN: ' + fixture.plans.primaryV2.patient_id + '\nPatient Name: ' + fullName
    + '\nOriginal Plan Reference: ' + reference + '\nService Date: 2026-08-17\nAdmission Date: 2026-08-01')
  let phase = 'login'
  try {
    await login(page)
    phase = 'binder-upload'
    await page.getByRole('button', { name: 'Manual Upload', exact: true }).click()
    const form = page.getByRole('form', { name: 'Treatment-plan binder import' })
    await page.getByLabel('Treatment-plan binder files', { exact: true }).setInputFiles({ name: 'synthetic-metadata.txt', mimeType: 'text/plain', buffer: bytes })
    const pending = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/manual-uploads/treatment-plan-file' && response.request().method() === 'POST')
    await form.getByRole('button', { name: 'Upload and securely process binder', exact: true }).click()
    const response = await pending
    expect(response.status()).toBe(201)
    const imported = await response.json()
    identity(imported)
    expect(imported.patient_record_id).toBe(fixture.plans.primaryV2.patient_record_id)
    await expect(form.getByRole('status')).toBeVisible()
    expect(await page.getByLabel('Treatment-plan binder files', { exact: true }).evaluate(input => input.files.length)).toBe(0)
    await expect(page.getByText('synthetic-metadata.txt', { exact: true })).toHaveCount(0)
    // When: the real imported version is opened, patient metadata and plan-local metadata are visible.
    phase = 'supplied-metadata'
    await openPlan(page, imported)
    await expect(page.locator('.patient-full-name')).toHaveText(fullName)
    await expect(fact(page, 'Original plan reference')).toHaveText(reference)
    await expect(fact(page, 'Service date')).toContainText('2026-08-17')
    await capture(page, 'task-7-metadata-supplied.png')
    const first = await detail(api, imported)
    expect(first.patient_full_name).toBe(fullName)
    expect(first.content_snapshot.original_plan_reference).toBe(reference)
    expect(first.content_snapshot.service_date).toBe('2026-08-17')
    phase = 'omitted-metadata'
    const omitted = await importBinder(api, [Buffer.from('MRN: ' + imported.patient_id + '\nAdmission Date: 2026-08-01\nGoal: Synthetic omitted metadata evidence')])
    expect(omitted.patient_record_id).toBe(imported.patient_record_id)
    await openPlan(page, omitted)
    await expect(page.locator('.patient-full-name')).toHaveText(fullName)
    await expect(fact(page, 'Original plan reference')).toHaveText('Not supplied')
    await expect(fact(page, 'Service date')).toHaveText('Not supplied')
    await capture(page, 'task-7-metadata-omitted.png')
    const omittedDetail = await detail(api, omitted)
    expect(omittedDetail.patient_full_name).toBe(fullName)
    expect(omittedDetail.content_snapshot.original_plan_reference).toBe('')
    expect(omittedDetail.content_snapshot.service_date).toBe('')
    phase = 'source-isolation'
    const alleva = await detail(api, fixture.plans.sourceCollision)
    expect(alleva.patient_full_name).toBe('')
    phase = 'name-filter'
    await openRoster(page)
    await expect(planRow(page, fixture.plans.sourceCollision).getByText('Name unavailable', { exact: true })).toBeVisible()
    const all = await list(api)
    const nameMatches = all.filter(plan => plan.patient_record_id === imported.patient_record_id)
    await page.getByLabel(rosterSearchLabel, { exact: true }).fill(fullName.toUpperCase())
    await expect(page.locator('tr[data-plan-version-id]')).toHaveCount(nameMatches.length)
    const exported = await exportList(page, nameMatches.map(plan => plan.plan_version_id))
    expect(exported.csv.text.includes(fullName)).toBe(false)
    expect(exported.csv.text.includes(reference)).toBe(false)
    await page.getByLabel(rosterSearchLabel, { exact: true }).fill(reference)
    await expect(page.locator('tr[data-plan-version-id]')).toHaveCount(1)
    phase = 'patient-record'
    const selectedPatient = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/patients/' + imported.patient_id)
    const started = Date.now()
    await planRow(page, imported).getByRole('button', { name: /Open patient record/ }).click()
    const patientResponse = await selectedPatient
    expect(patientResponse.status()).toBe(200)
    expect(new URL(patientResponse.url()).searchParams.get('patient_record_id')).toBe(String(imported.patient_record_id))
    await expect(page.locator('.patient-record-document h2').first()).toHaveText(fullName)
    await expect(page.locator('.patient-record-section')).not.toHaveCount(0)
    await expect(page.getByText('Loading patient record...', { exact: true })).toHaveCount(0)
    const settleMs = Date.now() - started
    phase = 'patient-search'
    await page.getByLabel('Search patient information', { exact: true }).fill(fullName.toLowerCase())
    await expect(page.locator('.patient-record-field-grid dd')).toContainText([fullName])
    await capture(page, 'task-7-patient-populated.png')
    await page.getByLabel('Search patient information', { exact: true }).fill('no-synthetic-patient-fields')
    await expect(page.getByText('No patient fields match the current search.', { exact: true })).toBeVisible()
    await capture(page, 'task-7-patient-no-match.png')
    phase = 'audit'
    const auditResponse = await admin.get('/api/audit/logs')
    expect(auditResponse.status()).toBe(200)
    const auditText = await auditResponse.text()
    expect(auditText.includes(fullName)).toBe(false)
    expect(auditText.includes(reference)).toBe(false)
    expect(auditText.includes('synthetic-metadata.txt')).toBe(false)
    // Then: only the exact manual row gains a name, omission preserves it, and exports/audit omit it.
    writeEvidence('task-7-metadata.json', { actualUiBinderImport: true, supplied: identity(imported), omitted: identity(omitted),
      sourceCollision: identity(fixture.plans.sourceCollision), originalIdsUnchanged: true, omissionPreservesName: true,
      optionalPlanFieldsClearedOnlyOnOmittedPlan: true, sourceCollisionNameAbsent: true, patientStatus: patientResponse.status(),
      patientSettleMs: settleMs, exported: exported.evidence, nameReferenceAndFilenameAbsentFromAudit: true })
  } catch (error) { failureBoundary(error, 'metadata-happy', phase); throw error } finally { await api.dispose(); await admin.dispose() }
})

test('A B C D reuse preserves exact source memberships and attached removal stays policy-gated @edge', async ({ page }) => {
  test.setTimeout(120_000)
  // Given: actual binder bytes reused across four imports, with all IDs captured from 201 responses.
  const api = await apiFor()
  const common = Buffer.from('MRN: IDENTITY-001\nAdmission Date: 2026-08-01')
  const extra1 = Buffer.from('MRN: IDENTITY-001\nIntervention: Synthetic additional evidence')
  const extra2 = Buffer.from('MRN: IDENTITY-001\nGoal: Synthetic second evidence')
  const recipes = [[common], [common, extra1], [extra1, extra2], [common, extra2]]
  let phase = 'source-import'
  try {
    const versions = [], fingerprints = []
    for (const [index, files] of recipes.entries()) {
      phase = 'source-import'
      versions.push(await importBinder(api, files))
      const sourceIds = [...new Set(versions.flatMap(plan => plan.source_file_ids))]
      phase = 'source-memberships'
      const snapshot = await sourceSnapshot(sourceIds, ['A', 'B', 'C', 'D'][index])
      const previous = fingerprints.at(-1)
      if (previous) {
        for (const source of previous.sources) expect(snapshot.sources.find(item => item.source_file_id === source.source_file_id)).toEqual(source)
        expect(snapshot.schema_history).toEqual(previous.schema_history)
        for (const membership of previous.memberships) expect(snapshot.memberships).toContainEqual(membership)
      }
      expect(snapshot.memberships).toHaveLength(recipes.slice(0, index + 1).reduce((count, items) => count + items.length, 0))
      const latest = versions.at(-1)
      const expectedRows = snapshot.sources.filter(source => latest.source_file_ids.includes(source.source_file_id)).map(source => source.source_document_id).sort()
      expect(snapshot.memberships.filter(item => item.plan_version_id === latest.plan_version_id).map(item => item.source_document_id).sort()).toEqual(expectedRows)
      fingerprints.push(snapshot)
    }
    phase = 'source-detail'
    const documents = []
    for (const [index, plan] of versions.entries()) {
      const saved = await detail(api, plan)
      expect(saved.source_documents.map(document => document.sha256).sort()).toEqual(recipes[index].map(hash).sort())
      expect(saved.source_documents.map(document => document.source_file_id).sort()).toEqual([...plan.source_file_ids].sort())
      for (const document of saved.source_documents) {
        const params = new URL(document.download_url, process.env.IZ_OM_BASE_URL).searchParams
        for (const key of ['patient_record_id', 'plan_version_id', 'source_mode']) expect(params.get(key)).toBe(String(plan[key]))
      }
      documents.push(saved.source_documents)
    }
    const commonRef = documents[0].find(document => document.sha256 === hash(common))
    expect(commonRef).toBeDefined()
    const downloadBase = '/api/v2/treatment-plans/IDENTITY-001/source-documents/' + commonRef.source_file_id + '/download'
    phase = 'source-download'
    const authorized = []
    for (const index of [0, 1, 3]) {
      const ref = documents[index].find(document => document.sha256 === commonRef.sha256)
      expect(ref.source_file_id).toBe(commonRef.source_file_id)
      const response = await api.get(downloadBase, { params: identity(versions[index]) })
      expect(response.status()).toBe(200)
      expect(hash(await response.body())).toBe(hash(common))
      authorized.push({ ...identity(versions[index]), status: response.status(), sourceFileId: ref.source_file_id, sha256: ref.sha256 })
    }
    const omitted = await api.get(downloadBase, { params: { patient_record_id: versions[0].patient_record_id, source_mode: 'manual_upload' } })
    expect(omitted.status()).toBe(409)
    const absent = await api.get(downloadBase, { params: identity(versions[2]) })
    expect(absent.status()).toBe(404)
    // When: the UI downloads the D membership, its request includes the exact selected identity.
    phase = 'source-ui'
    await login(page)
    await openPlan(page, versions[3])
    const source = page.locator('.source-document-list > li').filter({ has: page.getByText(commonRef.sha256, { exact: true }) })
    await expect(source).toHaveCount(1)
    const downloadRequest = page.waitForRequest(request => new URL(request.url()).pathname === downloadBase)
    const downloaded = await downloadBytes(page, () => source.getByRole('button', { name: 'Download archived source file', exact: true }).click())
    assertQuery((await downloadRequest).url(), versions[3])
    expect(hash(downloaded)).toBe(hash(common))
    await expect(page.getByRole('status')).toHaveText('Source file download started.')
    await capture(page, 'task-7-source-download.png')
    phase = 'source-removal'
    let uiDeleteRequests = 0, uiConfirmations = 0
    const observeDelete = request => { if (request.method() === 'DELETE') uiDeleteRequests += 1 }
    const observeConfirmation = async dialog => { uiConfirmations += 1; await dialog.dismiss() }
    page.on('request', observeDelete)
    page.on('dialog', observeConfirmation)
    const removal = source.getByRole('button', { name: 'Remove source file', exact: true })
    await expect(removal).toBeDisabled()
    await expect(page.getByText('Source removal is unavailable while the archive retention policy is pending.', { exact: true })).toBeVisible()
    await removal.evaluate(button => button.click())
    await expect(page.getByRole('button', { name: 'Delete archived source file', exact: true })).toHaveCount(0)
    await capture(page, 'task-7-source-removal-blocked.png')
    const deletion = await api.delete(downloadBase.replace(/\/download$/, ''), { params: identity(versions[3]) })
    assertQuery(deletion.url(), versions[3])
    expect(deletion.status()).toBe(409)
    expect(uiDeleteRequests).toBe(0)
    expect(uiConfirmations).toBe(0)
    page.off('request', observeDelete)
    page.off('dialog', observeConfirmation)
    await expect(page.getByText('Archived source file deleted.', { exact: true })).toHaveCount(0)
    await expect(page.locator('.source-document-list > li')).toHaveCount(2)
    // Then: all original memberships still list/download unchanged; no removal success is accepted.
    phase = 'source-post-delete'
    for (const [index, plan] of versions.entries()) {
      const after = await detail(api, plan)
      expect(after.source_documents.map(document => ({ id: document.source_file_id, sha256: document.sha256 })))
        .toEqual(documents[index].map(document => ({ id: document.source_file_id, sha256: document.sha256 })))
    }
    const after = await api.get(downloadBase + '?' + query(versions[0]))
    expect(after.status()).toBe(200)
    expect(hash(await after.body())).toBe(hash(common))
    const after409 = await sourceSnapshot(fingerprints.at(-1).sources.map(source => source.source_file_id), 'after409')
    expect(after409).toEqual(fingerprints.at(-1))
    writeEvidence('task-7-source-memberships.json', { actualBackend: true, versions: versions.map(identity),
      documents: documents.map(items => items.map(document => ({ sourceFileId: document.source_file_id, sha256: document.sha256 }))),
      authorized, omittedSelectorStatus: omitted.status(), absentMembershipStatus: absent.status(),
      uiDownloadSha256: hash(downloaded), uiRemovalBlocked: true, uiDeleteRequests, uiConfirmations,
      deletionRequestOrigin: 'explicit-api-test', deletionStatus: deletion.status(), allMembershipsPreserved: true,
      fingerprints, after409, firstForeignKeysPathsCreationAndCiphertextPreserved: true, schemaHistoryUnchanged: true,
      retentionDecisionPending: true, removalAcceptanceClaimed: false })
  } catch (error) { failureBoundary(error, 'metadata-edge', phase); throw error } finally { await api.dispose() }
})
