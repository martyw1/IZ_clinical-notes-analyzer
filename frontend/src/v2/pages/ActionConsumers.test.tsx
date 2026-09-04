import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { CorrectionsPage } from './CorrectionsPage'
import { UsersPage } from './UsersPage'
import { TreatmentPlansPage } from './TreatmentPlansPage'

const exact = { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'shared-plan' }
const user = { id: 2, username: 'manager', fullName: 'Synthetic Manager', role: 'office_manager' as const, isActive: true, isLocked: false, mustResetPassword: false, authState: 'active' as const, lockedUntil: '', facilityIds: [1] }
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

test('correction producer submits the exact row, version, source and work item', async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => json(init?.method === 'POST' ? {} : { items: [{ ...exact, patient_id: 'MRN-SHARED', work_item_id: 71, criterion_id: 'criterion', criterion_title: 'Synthetic criterion' }] }))
  vi.stubGlobal('fetch', fetchMock)
  render(<CorrectionsPage token='token' />)
  fireEvent.change(await screen.findByRole('textbox', { name: 'Resolution note' }), { target: { value: 'Synthetic resolution' } })
  fireEvent.click(screen.getByRole('button', { name: 'Submit correction' }))
  await screen.findByText('Correction submitted for manager review.')
  expect(JSON.parse(String(fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')?.[1]?.body))).toEqual({ ...exact, work_item_id: 71, criterion_id: 'criterion', comment: 'Synthetic resolution' })
})

test('patient assignment selects exact authorized row and never grants facility membership', async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/patient-roster')) return json({ items: [{ ...exact, mrn: 'MRN-SHARED', full_name: 'Synthetic Manual', treatment_plans: [] }, { patient_record_id: 32, source_mode: 'alleva_rest_api', mrn: 'MRN-SHARED', full_name: 'Synthetic Alleva', treatment_plans: [] }] })
    if (url === '/api/users') return json([{ id: 3, username: 'counselor', role: 'counselor', full_name: 'Synthetic Counselor', facility_ids: [1] }])
    return json([])
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<UsersPage token='token' />)
  const selector = await screen.findByRole('combobox', { name: 'Patient record assignment' })
  await waitFor(() => expect(screen.getByRole('option', { name: /Synthetic Manual/ })).toBeInTheDocument())
  fireEvent.change(selector, { target: { value: '31:manual_upload' } })
  fireEvent.click(screen.getByRole('button', { name: 'Assign patient' }))
  await screen.findByText('Patient assigned to counselor.')
  expect(fetchMock.mock.calls.some(([url, init]) => String(url) === '/api/patient-assignments/MRN-SHARED/counselor?patient_record_id=31&source_mode=manual_upload' && init?.method === 'PUT')).toBe(true)
  expect(fetchMock.mock.calls.some(([url, init]) => String(url).includes('/facilities/') && init?.method === 'PUT')).toBe(false)
})

test('queue refresh after a new version keeps the explicitly selected older version', async () => {
  let version = 91
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith('/treatment-plans')) return json({ items: [{ ...exact, plan_version_id: version, patient_id: 'MRN-SHARED', full_name: 'Synthetic Manual', status: 'Needs Review', is_current: true, version_ordinal: version - 90 }] })
    return json({ ...exact, patient_id: 'MRN-SHARED', patient_full_name: 'Synthetic Manual', content_snapshot: { plan_id: 'shared-plan' } })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<TreatmentPlansPage token='token' user={user} onNavigate={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: /^shared-plan/ }))
  await screen.findByRole('heading', { name: 'Treatment Plan ID shared-plan' })
  version = 92
  fireEvent.click(screen.getByRole('button', { name: 'Refresh queue' }))
  await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => String(url) === '/api/v2/treatment-plans')).toHaveLength(2))
  expect(screen.getByText('Saved version ID').nextElementSibling).toHaveTextContent('91')
  const detailRequests = fetchMock.mock.calls.filter(([url]) => new URL(String(url), 'http://localhost').pathname.startsWith('/api/v2/treatment-plans/'))
  expect(detailRequests.length).toBeGreaterThan(0)
  expect(detailRequests.every(([url]) => String(url).includes('plan_version_id=91'))).toBe(true)
})
