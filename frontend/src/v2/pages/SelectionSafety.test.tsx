import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { readPlanIdentity } from '../api/identity'
import { mapTreatmentPlanAggregate } from '../api/treatmentPlanMapper'
import { downloadChecklistEvidenceExport } from '../api/downloads'
import { beginRequestSession, endRequestSession } from '../api/request'
import { SourceFileArchiveControls } from '../components/SourceFileArchiveControls'
import { PatientRecordDetailPage } from './PatientRecordDetailPage'
import { TreatmentPlanDetailPage } from './TreatmentPlanDetailPage'

const wire = { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'same-plan' }
const selection = { ...readPlanIdentity(wire), mrn: 'MRN-SHARED', patientKey: 'MRN-SHARED' }
const user = { id: 1, username: 'manager', fullName: 'Synthetic Manager', role: 'office_manager' as const, isActive: true, isLocked: false, mustResetPassword: false, authState: 'active' as const, lockedUntil: '', facilityIds: [1] }
const payload = { ...wire, patient_id: 'MRN-SHARED', content_snapshot: { plan_id: 'same-plan' }, criteria_results: [{ criterion_id: 'criterion', criterion_title: 'Synthetic criterion', result_status: 'Needs Review' }], source_documents: [{ source_file_id: 'shared-source', source_kind: 'manual_treatment_plan_file', source_format: 'text' }] }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } })
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error('Not initialized') }
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
afterEach(() => { endRequestSession(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

test('invalidated session cannot start a manager write from a still-mounted selection', async () => {
  const isCurrent = beginRequestSession('token', vi.fn())
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => json(new URL(String(input), 'http://localhost').pathname === '/api/v2/treatment-plans' ? { items: [] } : payload))
  vi.stubGlobal('fetch', fetchMock)
  render(<TreatmentPlanDetailPage token='token' user={user} selection={selection} onNavigate={vi.fn()} isSessionCurrent={isCurrent} />)
  await screen.findByRole('button', { name: 'Approve criterion' })
  beginRequestSession('token', vi.fn())
  fireEvent.click(screen.getByRole('button', { name: 'Approve criterion' }))
  await act(async () => undefined)
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)
})

test('selected CSV failure settles visibly without an unhandled rejection', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), 'http://localhost').pathname
    return path.includes('/exports/') ? json({ detail: 'Access denied' }, 403) : json(path === '/api/v2/treatment-plans' ? { items: [] } : payload)
  }))
  render(<TreatmentPlanDetailPage token='token' user={user} selection={selection} onNavigate={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Export minimum-necessary checklist evidence' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Access denied')
})

test('mismatched patient response settles as an error instead of perpetual loading', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ patient_record_id: 32, source_mode: 'manual_upload', mrn: 'MRN-SHARED', patient_record: {} })))
  render(<PatientRecordDetailPage token='token' selection={selection} onNavigate={vi.fn()} onSelectTreatmentPlan={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match the selected')
  expect(screen.queryByText('Loading patient record...')).not.toBeInTheDocument()
})

test('mismatched saved-plan response settles as an error without showing another version', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => json(new URL(String(input), 'http://localhost').pathname === '/api/v2/treatment-plans' ? { items: [] } : { ...payload, plan_version_id: 92 })))
  render(<TreatmentPlanDetailPage token='token' user={user} selection={selection} onNavigate={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match the selected')
  expect(screen.queryByRole('heading', { name: 'Treatment Plan ID same-plan' })).not.toBeInTheDocument()
})

test('same-token session replacement suppresses an old save refresh and success message', async () => {
  const pending = deferred<Response>()
  const isCurrent = beginRequestSession('token', vi.fn())
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => init?.method === 'POST' ? pending.promise : json(new URL(String(input), 'http://localhost').pathname === '/api/v2/treatment-plans' ? { items: [] } : payload))
  vi.stubGlobal('fetch', fetchMock)
  render(<TreatmentPlanDetailPage token='token' user={user} selection={selection} onNavigate={vi.fn()} isSessionCurrent={isCurrent} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Approve criterion' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
  const before = fetchMock.mock.calls.length
  beginRequestSession('token', vi.fn())
  await act(async () => pending.resolve(json({ status: 'saved' })))
  expect(fetchMock).toHaveBeenCalledTimes(before)
  expect(screen.queryByText('Approval saved as a manager disposition.')).not.toBeInTheDocument()
})

test('attached archive removal is policy-blocked without confirmation or a DELETE request', async () => {
  const confirmDelete = vi.spyOn(window, 'confirm').mockReturnValue(true)
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => init?.method === 'DELETE' ? json({ detail: 'Retention policy is not approved.' }, 409) : json(new URL(String(input), 'http://localhost').pathname === '/api/v2/treatment-plans' ? { items: [] } : payload))
  vi.stubGlobal('fetch', fetchMock)
  render(<TreatmentPlanDetailPage token='token' user={user} selection={selection} onNavigate={vi.fn()} />)
  const removal = await screen.findByRole('button', { name: 'Remove source file' })
  expect(removal).toBeDisabled()
  expect(screen.getByText('Source removal is unavailable while the archive retention policy is pending.')).toBeVisible()
  fireEvent.click(removal)
  await act(async () => undefined)
  expect(confirmDelete).not.toHaveBeenCalled()
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(0)
  expect(screen.getByText('1 archived')).toBeInTheDocument()
  expect(screen.queryByText('Archived source file deleted.')).not.toBeInTheDocument()
})

test('reused source ID does not let an old completion clear the new versions busy state', async () => {
  const oldDownload = deferred<void>()
  const newDownload = deferred<void>()
  const download = vi.fn().mockImplementationOnce(() => oldDownload.promise).mockImplementationOnce(() => newDownload.promise)
  const plan = mapTreatmentPlanAggregate(payload)
  const props = { sourceDocuments: plan.sourceDocuments, onDownloadSourceDocument: download, onDeleteSourceDocument: vi.fn() }
  const view = render(<SourceFileArchiveControls identity={plan} {...props} />)
  fireEvent.click(screen.getByRole('button', { name: /Download archived source file/ }))
  view.rerender(<SourceFileArchiveControls identity={readPlanIdentity({ ...wire, plan_version_id: 92 })} {...props} />)
  fireEvent.click(screen.getByRole('button', { name: /Download archived source file/ }))
  await act(async () => oldDownload.resolve())
  expect(screen.queryByText('Source file download started.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Download archived source file/ })).toBeDisabled()
  await act(async () => newDownload.resolve())
  expect(screen.getByText('Source file download started.')).toBeInTheDocument()
})

test('late CSV bytes do not trigger a browser download after selection changes', async () => {
  const bytes = deferred<Blob>()
  const response = new Response()
  vi.spyOn(response, 'blob').mockImplementation(() => bytes.promise)
  vi.stubGlobal('fetch', vi.fn(async () => response))
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:test'); static revokeObjectURL = vi.fn() })
  let current = true
  const download = downloadChecklistEvidenceExport('token', { ...selection, isCurrent: () => current })
  await waitFor(() => expect(response.blob).toHaveBeenCalled())
  current = false
  bytes.resolve(new Blob(['synthetic']))
  await download
  expect(click).not.toHaveBeenCalled()
})
