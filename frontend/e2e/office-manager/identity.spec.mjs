import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { test, expect, login, capture, fixtureContract, apiFor, writeEvidence } from './support/fixtures.mjs'

function selector(plan) {
  return { plan_version_id: plan.plan_version_id, patient_record_id: plan.patient_record_id, source_mode: plan.source_mode }
}

function ledger() {
  const fixture = fixtureContract()
  const probe = spawnSync(path.join(process.env.IZ_OM_REPO_ROOT, 'backend/.venv/Scripts/python.exe'), ['-c',
    'import sqlite3,json,sys,pathlib; c=sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+"?mode=ro",uri=True); c.row_factory=sqlite3.Row; rows=c.execute("SELECT v.id AS plan_version_id,(SELECT COUNT(*) FROM manager_action_plan_links l WHERE l.plan_version_id=v.id) AS actions,(SELECT COUNT(*) FROM manager_dispositions d WHERE d.plan_version_id=v.id) AS dispositions,(SELECT COUNT(*) FROM evaluation_runs e WHERE e.plan_version_id=v.id) AS evaluations,(SELECT MAX(e.id) FROM evaluation_runs e WHERE e.plan_version_id=v.id) AS evaluation_id,(SELECT COUNT(*) FROM correction_work_items w WHERE w.plan_version_id=v.id AND w.status IN (\'open\',\'returned\')) AS open_items FROM treatment_plan_versions v ORDER BY v.id").fetchall(); print(json.dumps([dict(r) for r in rows])); c.close()',
    path.join(fixture.physical_data_dir, 'clinical-notes-analyzer-v2.sqlite3')], { encoding: 'utf8', windowsHide: true, timeout: 15_000 })
  expect(probe.status, 'Read-only ledger probe exits successfully').toBe(0)
  return JSON.parse(probe.stdout)
}

function seedUnassignedCorrection(fixture) {
  const source = fixture.plans.primaryV2
  const probe = spawnSync(path.join(process.env.IZ_OM_REPO_ROOT, 'backend/.venv/Scripts/python.exe'), ['-c',
    'import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); c.execute("PRAGMA foreign_keys=ON"); p=json.loads(sys.argv[2]); a=c.execute("INSERT INTO treatment_plan_manager_actions(patient_id,criterion_id,action,comment,override_reason,actor_user_id,actor_username,actor_role,created_at) VALUES(?,\'confirm_current_loc\',\'return_for_correction\',\'Synthetic legacy unassigned\',\'\',?,\'synthetic-legacy-manager\',\'office_manager\',\'2026-09-03 00:00:00\')",(p["patient_id"],str(p["manager"]))).lastrowid; c.execute("INSERT INTO manager_action_plan_links(action_id,plan_version_id) VALUES(?,NULL)",(a,)); d=c.execute("INSERT INTO manager_dispositions(plan_version_id,criterion_id,status,comment,actor_user_id,created_at) VALUES(?,\'confirm_current_loc\',\'return_for_correction\',\'Synthetic legacy unassigned\',?,\'2026-09-03T00:00:00+00:00\')",(p["version"],p["manager"])).lastrowid; w=c.execute("INSERT INTO correction_work_items(plan_version_id,criterion_id,disposition_id,assigned_counselor_user_id,status,opened_at,idempotency_key) VALUES(?,\'confirm_current_loc\',?,?,\'open\',\'2026-09-03T00:00:00+00:00\',?)",(p["version"],d,p["counselor"],"synthetic-legacy-"+str(a))).lastrowid; c.commit(); print(json.dumps({"actionId":a,"workItemId":w,"planVersionId":p["version"]})); c.close()',
    path.join(fixture.physical_data_dir, 'clinical-notes-analyzer-v2.sqlite3'),
    JSON.stringify({ patient_id: source.patient_id, version: source.plan_version_id, manager: fixture.users.office_manager.id, counselor: fixture.users.counselor.id })],
  { encoding: 'utf8', windowsHide: true, timeout: 15_000 })
  expect(probe.status, 'Synthetic legacy fixture creation exits successfully').toBe(0)
  return JSON.parse(probe.stdout)
}

async function detail(api, plan) {
  const response = await api.get(`/api/v2/treatment-plans/${plan.patient_id}/${plan.plan_id}`, { params: selector(plan) })
  expect(response.status()).toBe(200)
  const result = await response.json()
  expect(result.plan_version_id).toBe(plan.plan_version_id)
  expect(result.patient_record_id).toBe(plan.patient_record_id)
  return result
}

test('old selection remains bound through new import, all actions, correction and export @happy', async ({ page }) => {
  const fixture = fixtureContract()
  const selected = fixture.plans.primaryV1
  const manager = await apiFor()
  const counselor = await apiFor('counselor')
  try {
    await login(page)
    const original = await detail(manager, selected)
    const { plan_version_id, patient_record_id, unassigned_manager_reviews, ...aggregate } = original
    const imported = await manager.post('/api/v2/manual-uploads/treatment-plan-aggregate', {
      data: { ...aggregate, source_last_updated: '2026-09-03T23:59:01Z' },
    })
    expect(imported.status()).toBe(201)
    const fresh = await imported.json()
    expect(fresh.plan_version_id).not.toBe(selected.plan_version_id)
    const before = ledger()
    const actions = ['approve', 'comment', 'override', 'return_for_correction']
    for (const action of actions) {
      const saved = await manager.post(`/api/v2/treatment-plans/${selected.patient_id}/manager-actions`, {
        data: { ...selector(selected), criterion_id: 'confirm_current_loc', action,
          comment: 'Synthetic exact-version review', override_reason: 'Synthetic verification reason',
          assigned_counselor_username: fixture.users.counselor.username },
      })
      expect(saved.status()).toBe(200)
      expect((await saved.json()).plan_version_id).toBe(selected.plan_version_id)
    }
    const queue = await counselor.get('/api/v2/corrections')
    expect(queue.status()).toBe(200)
    const item = (await queue.json()).items.find(row => row.plan_version_id === selected.plan_version_id)
    expect(item.patient_record_id).toBe(selected.patient_record_id)
    const submitted = await counselor.post(`/api/v2/treatment-plans/${selected.patient_id}/correction-submissions`, {
      data: { ...selector(selected), work_item_id: item.work_item_id, criterion_id: item.criterion_id, comment: 'Synthetic correction submitted' },
    })
    expect(submitted.status()).toBe(200)
    expect((await submitted.json()).plan_version_id).toBe(selected.plan_version_id)
    const exported = await manager.get(`/api/v2/exports/${selected.patient_id}/checklist-evidence.csv`, { params: selector(selected) })
    expect(exported.status()).toBe(200)
    const csvRows = (await exported.text()).trim().split(/\r?\n/)
    expect(csvRows).toHaveLength(43)
    expect(csvRows.slice(1).every(row => row.startsWith(`${selected.plan_version_id},${selected.patient_record_id},${selected.source_mode},`))).toBe(true)
    const selectedAfter = await detail(manager, selected)
    expect(selectedAfter.source_last_updated).toBe(original.source_last_updated)
    expect(selectedAfter.manager_reviews.slice(-5).map(row => row.action)).toEqual([...actions, 'correction_submitted'])
    const after = ledger()
    const oldBefore = before.find(row => row.plan_version_id === selected.plan_version_id)
    const oldAfter = after.find(row => row.plan_version_id === selected.plan_version_id)
    expect(oldAfter.actions - oldBefore.actions).toBe(5)
    expect(oldAfter.evaluations - oldBefore.evaluations).toBe(1)
    expect(after.filter(row => row.plan_version_id !== selected.plan_version_id)).toEqual(before.filter(row => row.plan_version_id !== selected.plan_version_id))
    await capture(page, 'task-3-api-session.png')
    writeEvidence('task-3-identity.json', { apiSurfaceOnly: true, selected: selector(selected), importedVersionId: fresh.plan_version_id,
      actionKinds: actions, correctionStatus: submitted.status(), csvRows: csvRows.length - 1, selectedContentPreserved: true,
      selectedLedgerBefore: oldBefore, selectedLedgerAfter: oldAfter, otherVersionLedgersUnchanged: true })
  } finally { await manager.dispose(); await counselor.dispose() }
})

test('ambiguous and incompatible selectors, wrong facility and replay fail closed @edge', async ({ page }) => {
  const fixture = fixtureContract()
  const selected = fixture.plans.primaryV1
  const manager = await apiFor()
  const counselor = await apiFor('counselor')
  const viewer = await apiFor('viewer')
  const admin = await apiFor('admin')
  try {
    await login(page)
    const legacy = seedUnassignedCorrection(fixture)
    const legacyQueue = await counselor.get('/api/v2/corrections')
    expect((await legacyQueue.json()).items.some(row => row.work_item_id === legacy.workItemId)).toBe(false)
    const legacyDetail = await detail(admin, fixture.plans.primaryV2)
    expect(legacyDetail.manager_reviews.some(row => row.action_id === legacy.actionId)).toBe(false)
    expect(legacyDetail.unassigned_manager_reviews.find(row => row.action_id === legacy.actionId).plan_version_id).toBe(null)
    const legacySubmission = await counselor.post(`/api/v2/treatment-plans/${selected.patient_id}/correction-submissions`, {
      data: { ...selector(fixture.plans.primaryV2), work_item_id: legacy.workItemId, criterion_id: 'confirm_current_loc', comment: 'Synthetic unassigned attempt' },
    })
    expect(legacySubmission.status()).toBe(404)
    const before = ledger()
    const outcomes = []
    for (const endpoint of [`/api/v2/treatment-plans/${selected.patient_id}`, `/api/v2/exports/${selected.patient_id}/checklist-evidence.csv`]) {
      const response = await manager.get(endpoint)
      expect(response.status()).toBe(409)
      outcomes.push(response.status())
    }
    const omitted = await manager.post(`/api/v2/treatment-plans/${selected.patient_id}/manager-actions`, {
      data: { criterion_id: 'confirm_current_loc', action: 'approve' },
    })
    expect(omitted.status()).toBe(409)
    const mismatch = await manager.get(`/api/v2/treatment-plans/${selected.patient_id}`, {
      params: { ...selector(selected), source_mode: 'alleva_rest_api' },
    })
    expect(mismatch.status()).toBe(404)
    const wrongFacility = await manager.post(`/api/v2/treatment-plans/${fixture.plans.facilityCollision.patient_id}/manager-actions`, {
      data: { ...selector(fixture.plans.facilityCollision), criterion_id: 'confirm_current_loc', action: 'approve' },
    })
    expect(wrongFacility.status()).toBe(403)
    const wrongRole = await viewer.post(`/api/v2/treatment-plans/${selected.patient_id}/manager-actions`, {
      data: { ...selector(selected), criterion_id: 'confirm_current_loc', action: 'approve' },
    })
    expect(wrongRole.status()).toBe(403)
    expect(ledger()).toEqual(before)
    const returned = await manager.post(`/api/v2/treatment-plans/${selected.patient_id}/manager-actions`, {
      data: { ...selector(selected), criterion_id: 'confirm_current_loc', action: 'return_for_correction',
        assigned_counselor_username: fixture.users.counselor.username, comment: 'Synthetic replay scenario' },
    })
    expect(returned.status()).toBe(200)
    const queue = await counselor.get('/api/v2/corrections')
    const item = (await queue.json()).items.find(row => row.plan_version_id === selected.plan_version_id)
    const submission = { ...selector(selected), work_item_id: item.work_item_id, criterion_id: item.criterion_id, comment: 'Synthetic submission' }
    expect((await counselor.post(`/api/v2/treatment-plans/${selected.patient_id}/correction-submissions`, { data: submission })).status()).toBe(200)
    const submittedState = ledger()
    const replay = await counselor.post(`/api/v2/treatment-plans/${selected.patient_id}/correction-submissions`, { data: submission })
    expect(replay.status()).toBe(409)
    expect(ledger()).toEqual(submittedState)
    writeEvidence('task-3-identity-error.json', { apiSurfaceOnly: true, ambiguityStatuses: [...outcomes, omitted.status()],
      selectorMismatch: mismatch.status(), wrongFacility: wrongFacility.status(), wrongRole: wrongRole.status(), replay: replay.status(),
      deniedLedgersUnchanged: true, replayLedgerUnchanged: true, legacyHistoryUnassigned: true,
      legacyWorkItemExcluded: true, legacySubmissionStatus: legacySubmission.status() })
  } finally { await manager.dispose(); await counselor.dispose(); await viewer.dispose(); await admin.dispose() }
})
