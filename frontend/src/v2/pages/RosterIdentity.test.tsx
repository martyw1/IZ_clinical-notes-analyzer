import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UserProfile } from '../api/types'
import { TreatmentPlansRosterPage } from './TreatmentPlansRosterPage'

const user: UserProfile = { id: 1, username: 'manager', fullName: 'Synthetic Manager', role: 'office_manager', isActive: true, isLocked: false, mustResetPassword: false, authState: 'active', lockedUntil: '', facilityIds: [1] }
const records = [
  { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'shared-external', mrn: 'MRN-SHARED', patient_key: 'MRN-SHARED', linked_to_mrn: true, full_name: 'Synthetic Manual', original_plan_reference: 'MANUAL-REF', version_ordinal: 2 },
  { patient_record_id: 32, plan_version_id: 92, source_mode: 'alleva_rest_api', treatment_plan_id: 'shared-external', mrn: 'MRN-SHARED', patient_key: 'MRN-SHARED', linked_to_mrn: true, full_name: 'Synthetic Alleva', original_plan_reference: 'ALLEVA-REF', version_ordinal: 3 },
  ...Array.from({ length: 36 }, (_, index) => ({ patient_record_id: 100 + index, plan_version_id: 200 + index, source_mode: 'manual_upload', treatment_plan_id: `offscreen-${index}`, mrn: `MRN-SCOPE-${index}`, patient_key: `MRN-SCOPE-${index}`, linked_to_mrn: true, full_name: 'Synthetic Scope', original_plan_reference: 'SCOPE-REF', version_ordinal: 1 })),
]

function setup() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return new Response('plan_version_id\n', { headers: { 'content-type': 'text/csv' } })
    const source = new URL(String(input), 'http://localhost').searchParams.get('source_mode')
    return new Response(JSON.stringify({ items: records.filter((item) => !source || item.source_mode === source) }), { headers: { 'content-type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:test'); static revokeObjectURL = vi.fn() })
  const onSelectTreatmentPlan = vi.fn()
  const onSelectPatient = vi.fn()
  render(<TreatmentPlansRosterPage token='token' user={user} onNavigate={vi.fn()} onSelectPatient={onSelectPatient} onSelectTreatmentPlan={onSelectTreatmentPlan} />)
  return { fetchMock, onSelectTreatmentPlan, onSelectPatient }
}

describe('source-aware roster and complete export scope', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('selects the manual row and immutable version when source and external IDs collide', async () => {
    const { onSelectTreatmentPlan, onSelectPatient } = setup()
    const row = (await screen.findByText('Synthetic Manual')).closest('tr')
    if (!row) throw new Error('Synthetic row missing')

    fireEvent.click(within(row).getByRole('button', { name: /Open treatment plan/ }))
    fireEvent.click(within(row).getByRole('button', { name: /Open patient record/ }))

    expect(onSelectTreatmentPlan).toHaveBeenCalledWith(expect.objectContaining({ patientRecordId: 31, planVersionId: 91, treatmentPlanId: 'shared-external', sourceMode: 'manual_upload' }))
    expect(onSelectPatient).toHaveBeenCalledWith(expect.objectContaining({ patientRecordId: 31, sourceMode: 'manual_upload' }))
  })

  it.each([
    ['all', 'MRN-SHARED', [91, 92]], ['manual_upload', 'MRN-SHARED', [91]], ['alleva_rest_api', 'MRN-SHARED', [92]],
    ['all', 'Synthetic Manual', [91]], ['manual_upload', 'Synthetic Manual', [91]], ['alleva_rest_api', 'Synthetic Manual', []],
    ['all', 'ALLEVA-REF', [92]], ['manual_upload', 'ALLEVA-REF', []], ['alleva_rest_api', 'ALLEVA-REF', [92]],
  ])('exports exact source %s and local query %s identities only', async (source, query, ids) => {
    const { fetchMock } = setup()
    await screen.findByRole('table')
    fireEvent.change(screen.getByRole('combobox', { name: 'Source filter' }), { target: { value: source } })
    await screen.findByRole('table')
    fireEvent.change(screen.getByRole('textbox', { name: /Search MRN/ }), { target: { value: query } })

    fireEvent.click(screen.getByRole('button', { name: 'Export treatment plans and statuses' }))

    await waitFor(() => expect(fetchMock.mock.calls.some((call) => call[1]?.method === 'POST')).toBe(true))
    const exported = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(JSON.parse(String(exported?.[1]?.body))).toEqual({ plan_version_ids: ids, ...(source === 'all' ? {} : { source_mode: source }) })
    expect(String(exported?.[1]?.body)).not.toContain(query)
  })

  it('exports every filtered result beyond one viewport and excludes nonmatches', async () => {
    const { fetchMock } = setup()
    await screen.findByRole('table')
    fireEvent.change(screen.getByRole('textbox', { name: /Search MRN/ }), { target: { value: 'SCOPE-REF' } })

    fireEvent.click(screen.getByRole('button', { name: 'Export treatment plans and statuses' }))

    await waitFor(() => expect(fetchMock.mock.calls.some((call) => call[1]?.method === 'POST')).toBe(true))
    expect(JSON.parse(String(fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')?.[1]?.body))).toEqual({ plan_version_ids: Array.from({ length: 36 }, (_, index) => 200 + index) })
    expect(screen.getAllByRole('row')).toHaveLength(37)
  })
})
