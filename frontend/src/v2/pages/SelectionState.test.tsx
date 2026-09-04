import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { readPlanIdentity } from '../api/identity'
import { mapTreatmentPlanAggregate } from '../api/treatmentPlanMapper'
import type { UserProfile } from '../api/types'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import { TreatmentPlanDetailPage } from './TreatmentPlanDetailPage'

const user: UserProfile = { id: 1, username: 'manager', fullName: 'Synthetic Manager', role: 'office_manager', isActive: true, isLocked: false, mustResetPassword: false, authState: 'active', lockedUntil: '', facilityIds: [1] }
const firstIdentity = { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'same-external' }
const secondIdentity = { ...firstIdentity, patient_record_id: 32, plan_version_id: 92, source_mode: 'alleva_rest_api' }
const firstSelection = { ...readPlanIdentity(firstIdentity), mrn: 'MRN-SHARED', patientKey: 'MRN-SHARED' }
const secondSelection = { ...readPlanIdentity(secondIdentity), mrn: 'MRN-SHARED', patientKey: 'MRN-SHARED' }
function payload(identity = firstIdentity) {
  return { ...identity, patient_id: 'MRN-SHARED', patient_display_label: 'MRN MRN-SHARED', patient_full_name: identity.plan_version_id === 91 ? 'Synthetic First' : 'Synthetic Second', content_snapshot: { plan_id: 'same-external' }, criteria_results: [{ criterion_id: 'criterion-1', criterion_title: 'Shared criterion', result_status: 'Needs Review', source_json_paths: [] }] }
}
function response(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }) }
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error('Deferred not initialized') }
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
const callbacks = { onExportChecklistEvidence: vi.fn(), onDownloadSourceDocument: vi.fn(), onDeleteSourceDocument: vi.fn() }

describe('exact selection state generations', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('clears local drafts and ignores old save feedback when version changes with the same external ID', async () => {
    const pending = deferred<void>()
    const onManagerAction = vi.fn(() => pending.promise)
    const view = render(<TreatmentPlanDetailViewer plan={mapTreatmentPlanAggregate(payload())} canManage onManagerAction={onManagerAction} {...callbacks} />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Manager comment' }), { target: { value: 'First version draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save comment' }))

    view.rerender(<TreatmentPlanDetailViewer plan={mapTreatmentPlanAggregate(payload(secondIdentity))} canManage onManagerAction={onManagerAction} {...callbacks} />)
    await act(async () => pending.resolve())

    expect(screen.getByRole('textbox', { name: 'Manager comment' })).toHaveValue('')
    expect(screen.queryByText('Manager comment saved without changing deterministic results.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save comment' })).toBeEnabled()
  })

  it('does not refresh or overwrite a new selected record after an old save completes', async () => {
    const pending = deferred<Response>()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') return pending.promise
      const url = new URL(String(input), 'http://localhost')
      return response(url.pathname.endsWith('/treatment-plans') ? { items: [] } : payload(url.searchParams.get('plan_version_id') === '92' ? secondIdentity : firstIdentity))
    })
    vi.stubGlobal('fetch', fetchMock)
    const view = render(<TreatmentPlanDetailPage token='token' user={user} selection={firstSelection} onNavigate={vi.fn()} />)
    await screen.findByText('Synthetic First')
    fireEvent.click(screen.getByRole('button', { name: 'Approve criterion' }))
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => call[1]?.method === 'POST')).toBe(true))
    view.rerender(<TreatmentPlanDetailPage token='token' user={user} selection={secondSelection} onNavigate={vi.fn()} />)
    await screen.findByText('Synthetic Second')
    const countBefore = fetchMock.mock.calls.length

    await act(async () => pending.resolve(response({ status: 'saved' })))

    expect(screen.getByText('Synthetic Second')).toBeInTheDocument()
    expect(screen.queryByText('Synthetic First')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(countBefore)
  })

  it('keeps the current view when a delayed read for the former selection resolves', async () => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/treatment-plans')) return response({ items: [] })
      return url.searchParams.get('plan_version_id') === '91' ? pending.promise : response(payload(secondIdentity))
    }))
    const view = render(<TreatmentPlanDetailPage token='token' user={user} selection={firstSelection} onNavigate={vi.fn()} />)
    view.rerender(<TreatmentPlanDetailPage token='token' user={user} selection={secondSelection} onNavigate={vi.fn()} />)
    await screen.findByText('Synthetic Second')

    await act(async () => pending.resolve(response(payload())))

    expect(screen.getByText('Synthetic Second')).toBeInTheDocument()
    expect(screen.queryByText('Synthetic First')).not.toBeInTheDocument()
  })
})
