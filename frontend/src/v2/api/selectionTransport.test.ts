import { afterEach, describe, expect, it, vi } from 'vitest'
import { assignPatient, getPatientRecordDetail, getTreatmentPlanDetail, getTreatmentPlans, saveManagerAction } from './client'
import { submitCorrection } from './correctionsClient'
import { downloadChecklistEvidenceExport, downloadTreatmentPlanListExport, downloadTreatmentPlanSourceDocument } from './downloads'
import { readPlanIdentity } from './identity'

const wireIdentity = { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'external-shared' }
const selection = { ...readPlanIdentity(wireIdentity), mrn: 'MRN-SHARED', patientKey: 'MRN-SHARED' }
const action = { criterionId: 'criterion-1', action: 'comment', comment: 'Synthetic correction', overrideReason: '' } as const
function setup() {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify({ ...wireIdentity, patient_id: 'MRN-SHARED', content_snapshot: { plan_id: 'external-shared' }, items: [] }), { headers: { 'content-type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:test'); static revokeObjectURL = vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  return fetchMock
}

describe('exact selection request consistency', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('sends the immutable selected detail and exact patient row', async () => {
    const fetchMock = setup()

    await getTreatmentPlanDetail('token', selection)
    await getPatientRecordDetail('token', selection)

    const urls = fetchMock.mock.calls.map((call) => new URL(String(call[0]), 'http://localhost'))
    expect(urls[0]?.searchParams.get('plan_version_id')).toBe('91')
    expect(urls.every((url) => url.searchParams.get('patient_record_id') === '31' && url.searchParams.get('source_mode') === 'manual_upload')).toBe(true)
  })

  it('loads explicit history scoped to row source and external plan only when requested', async () => {
    const fetchMock = setup()

    await getTreatmentPlans('token', { ...selection, includeHistory: true })

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), 'http://localhost')
    expect(Object.fromEntries(url.searchParams)).toEqual({ patient_record_id: '31', source_mode: 'manual_upload', treatment_plan_id: 'external-shared', include_history: 'true' })
  })

  it('sends exact action and correction identities without latest lookup', async () => {
    const fetchMock = setup()

    await saveManagerAction('token', selection, action)
    await submitCorrection('token', selection.patientKey, { ...selection, workItemId: 17, criterionId: action.criterionId, comment: action.comment })

    const bodies = fetchMock.mock.calls.map((call) => JSON.parse(String(call[1]?.body)))
    expect(bodies).toEqual([expect.objectContaining(wireIdentity), expect.objectContaining({ ...wireIdentity, work_item_id: 17 })])
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('sends exact source and selected CSV selectors', async () => {
    const fetchMock = setup()

    await downloadTreatmentPlanSourceDocument('token', selection, 'source-1')
    await downloadChecklistEvidenceExport('token', selection)

    const urls = fetchMock.mock.calls.map((call) => new URL(String(call[0]), 'http://localhost'))
    expect(urls.every((url) => url.searchParams.get('plan_version_id') === '91' && url.searchParams.get('patient_record_id') === '31' && url.searchParams.get('source_mode') === 'manual_upload' && url.searchParams.get('treatment_plan_id') === 'external-shared')).toBe(true)
  })

  it('posts explicit empty filtered CSV identity scope instead of exporting all', async () => {
    const fetchMock = setup()

    await downloadTreatmentPlanListExport('token', { planVersionIds: [], sourceMode: 'manual_upload' })

    expect(fetchMock).toHaveBeenCalledWith('/api/v2/exports/treatment-plans.csv', expect.objectContaining({ method: 'POST', body: JSON.stringify({ plan_version_ids: [], source_mode: 'manual_upload' }) }))
  })

  it('assigns only the selected numeric patient record and source', async () => {
    const fetchMock = setup()

    await assignPatient('token', selection, 'synthetic-counselor')

    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), 'http://localhost')
    expect(url.pathname).toBe('/api/patient-assignments/MRN-SHARED/synthetic-counselor')
    expect(Object.fromEntries(url.searchParams)).toEqual({ patient_record_id: '31', source_mode: 'manual_upload' })
  })
})
