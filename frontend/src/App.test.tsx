import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { adminNavigation, setupFetch } from './test/v2ApiMock'

async function signIn(password = 'StrongLocalPass1') {
  render(<App />)
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
  await screen.findByRole('navigation', { name: /primary navigation/i })
}

beforeEach(() => {
  sessionStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('V2 active app shell', () => {
  it('requires first-run password change before rendering the workspace', async () => {
    const fetchMock = setupFetch({ role: 'admin', mustResetPassword: true })
    render(<App />)
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'SyntheticBootstrapPass123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('heading', { name: 'Set a new password' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: /primary navigation/i })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'SyntheticBootstrapPass123' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'SyntheticActivePass456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Update password' }))

    await screen.findByRole('navigation', { name: /primary navigation/i })
    expect(fetchMock).toHaveBeenCalledWith('/api/users/me/change-password', expect.objectContaining({ method: 'POST' }))
  })

  it('rejects invalid credentials without entering the app shell', async () => {
    setupFetch({ role: 'admin', failLogin: true })
    render(<App />)

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials')
    expect(screen.queryByRole('navigation', { name: /primary navigation/i })).not.toBeInTheDocument()
  })

  it('signs in through the backend and loads admin navigation', async () => {
    const fetchMock = setupFetch()
    await signIn()

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/users/me', expect.objectContaining({ headers: expect.any(Headers) }))
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/navigation', expect.objectContaining({ headers: expect.any(Headers) }))

    const nav = screen.getByRole('navigation', { name: /primary navigation/i })
    const labels = within(nav).getAllByRole('button').map((button) => button.textContent)
    expect(labels).toEqual([...adminNavigation])
  })

  it('hides admin-only navigation for counselor role sessions', async () => {
    setupFetch({ role: 'counselor' })
    await signIn()

    const nav = screen.getByRole('navigation', { name: /primary navigation/i })
    expect(within(nav).queryByRole('button', { name: 'Users' })).not.toBeInTheDocument()
    expect(within(nav).queryByRole('button', { name: 'Settings' })).not.toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Treatment Plans' })).toBeInTheDocument()
    expect(within(nav).getByRole('button', { name: 'Corrections' })).toBeInTheDocument()
  })

  it('gives counselors an actionable correction queue without manager controls', async () => {
    const fetchMock = setupFetch({ role: 'counselor' })
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))
    expect(await screen.findByText('Patient ID 812')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /return for correction/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save override/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Corrections' }))
    expect(await screen.findByText('Open Returns')).toBeInTheDocument()
    expect(screen.getByText(/Manager note: Confirm the current LOC source\./i)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Resolution note'), { target: { value: 'Updated synthetic source record.' } })
    fireEvent.click(screen.getByRole('button', { name: /submit correction/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('Correction submitted for manager review.')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/treatment-plans/812/correction-submissions',
      expect.objectContaining({ method: 'POST', headers: expect.any(Headers) }),
    )
    const submission = fetchMock.mock.calls.find(([path]) => path === '/api/v2/treatment-plans/812/correction-submissions')
    expect(submission?.[1]?.body).toContain('"work_item_id":71')
  })

  it('renders dashboard and treatment-plan detail from V2 APIs', async () => {
    setupFetch()
    await signIn()

    expect(await screen.findByText('Active patient IDs')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText(/LOC-change update window is unvalidated/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))

    expect(await screen.findByText('Patient ID 812')).toBeInTheDocument()
    expect(screen.getByText(/LOC-change clock:/)).toHaveClass('summary-grid__item--wrappable')
    expect(screen.getByText('Diagnoses')).toBeInTheDocument()
    expect(screen.getByText('Behavioral Definitions')).toBeInTheDocument()
    expect(screen.getByText('Goals')).toBeInTheDocument()
    expect(screen.getByText(/Objective 1:/)).toBeInTheDocument()
    expect(screen.getByText('Interventions')).toBeInTheDocument()
    expect(screen.getByText(/signature image\/base64 never returned/i)).toBeInTheDocument()
    expect(screen.getByText('Persisted manager actions')).toBeInTheDocument()
    expect(screen.getByText(/Signed plan and LOC evidence match imported record/i)).toBeInTheDocument()
    expect(screen.getByText('Source File Archive')).toBeInTheDocument()
    expect(screen.getByText('manual_treatment_plan_file')).toBeInTheDocument()
    expect(screen.getByText('encrypted_original_file')).toBeInTheDocument()
    expect(screen.getByText('Data Quality Warnings')).toBeInTheDocument()
    expect(screen.queryByText(/client name|Marleigh|Johnson/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /save override/i }))
    expect(screen.getByRole('status')).toHaveTextContent('Override reason is required.')

    fireEvent.change(screen.getByLabelText(/override reason/i), { target: { value: 'Accepted after source review.' } })
    fireEvent.click(screen.getByRole('button', { name: /save override/i }))
    expect(await screen.findByRole('status')).toHaveTextContent('Override saved with required reason and audit event.')
  })

  it('downloads archived source files through an authenticated backend request', async () => {
    const createObjectUrl = vi.fn(() => 'blob:source-download')
    const revokeObjectUrl = vi.fn()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
    const fetchMock = setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))
    fireEvent.click(await screen.findByRole('button', { name: /download archived source file/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v2/treatment-plans/812/source-documents/source-file-812/download',
        expect.objectContaining({ headers: expect.any(Headers) }),
      )
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Source file download started.')
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob))
    expect(anchorClick).toHaveBeenCalled()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:source-download')
  })

  it('deletes archived source files through an authenticated backend request and refreshes detail', async () => {
    const confirmDelete = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fetchMock = setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))
    expect(await screen.findByText('1 archived')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /delete archived source file/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v2/treatment-plans/812/source-documents/source-file-812',
        expect.objectContaining({ method: 'DELETE', headers: expect.any(Headers) }),
      )
    })
    expect(confirmDelete).toHaveBeenCalledWith(expect.stringContaining('Delete archived source file'))
    await waitFor(() => expect(screen.getByText('0 archived')).toBeInTheDocument())
    expect(await screen.findByRole('status')).toHaveTextContent('Archived source file deleted.')
    expect(screen.getByText(/No archived source files are linked/i)).toBeInTheDocument()
  })

  it('loads admin settings, API configuration, users, and audit logs from protected endpoints', async () => {
    setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(await screen.findByDisplayValue('R3 Recovery Services')).toBeInTheDocument()
    expect(screen.getByText(/unvalidated by R3\/Marleigh/i)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/client secret/i), { target: { value: 'new-secret-value' } })
    fireEvent.click(screen.getByRole('button', { name: /save api configuration/i }))
    expect(await screen.findByText(/client secret configured/i)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('new-secret-value')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /pull openapi definition/i }))
    expect(await screen.findByText('Mock Treatment Plan API: 3 operations available.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /test saved oauth connectivity/i }))
    expect(await screen.findByText(/token obtained and discarded after verification/i)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Enable API testing'))
    fireEvent.click(screen.getByLabelText('Enable treatment-plan sync'))
    fireEvent.click(screen.getByLabelText('Sync intent recorded (does not authorize execution)'))
    fireEvent.click(screen.getByLabelText('Mapping intent recorded (does not authorize execution)'))
    fireEvent.click(screen.getByRole('button', { name: /save api configuration/i }))
    fireEvent.click(await screen.findByRole('button', { name: /run approved treatment-plan sync/i }))
    expect(await screen.findByText('Treatment-plan sync completed: 1 imported, 0 skipped.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Users' }))
    expect(await screen.findByText('Local Administrator')).toBeInTheDocument()
    expect(screen.getByText('Counselor User')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'newcounselor' } })
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'New Counselor' } })
    fireEvent.change(screen.getByLabelText('Temporary password'), { target: { value: 'TemporaryPass1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create user' }))
    expect(await screen.findByRole('status')).toHaveTextContent('User created; password change is required')
    fireEvent.change(screen.getByLabelText('Facility assignment user'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Facility'), { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign facility' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Facility assigned.')
    fireEvent.change(screen.getByLabelText('Patient ID assignment'), { target: { value: '812' } })
    fireEvent.change(screen.getByLabelText('Counselor assignment'), { target: { value: 'counselor' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign patient' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Patient assigned to counselor.')

    fireEvent.click(screen.getByRole('button', { name: 'Forensic Logs' }))
    expect(await screen.findByText('settings.api_profile.saved')).toBeInTheDocument()
    expect(screen.queryByText('new-secret-value')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /verify hash chain/i }))
    expect(await screen.findByRole('status')).toHaveTextContent('Hash chain verified across 3 events.')
  })

  it('hides workflow profiles from the operational navigation', async () => {
    setupFetch()
    await signIn()

    expect(screen.queryByRole('button', { name: 'Workflow Profiles' })).not.toBeInTheDocument()
  })

  it('starts API harness jobs through the backend and renders bounded artifacts', async () => {
    setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'API Testing Harness' }))
    fireEvent.click(screen.getByRole('button', { name: /start large job/i }))

    expect(await screen.findByText('completed')).toBeInTheDocument()
    expect(screen.getByText('all-treatment-plans.all-fields.redacted.jsonl')).toBeInTheDocument()
    expect(screen.queryByText(/signatureData.*base64/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/read-only operation path/i), { target: { value: '/health' } })
    fireEvent.click(screen.getByRole('button', { name: /test read-only operation/i }))
    expect(await screen.findByText(/Read-only operation completed\. 200 \| 24 bytes/i)).toBeInTheDocument()
  })

  it('imports normalized manual treatment-plan aggregate files through the backend', async () => {
    const fetchMock = setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Manual Upload' }))
    const file = new File([JSON.stringify({ patient_id: '812', source_mode: 'manual_upload' })], 'manual-aggregate.json', {
      type: 'application/json',
    })
    fireEvent.change(screen.getByLabelText(/normalized V2 aggregate JSON/i), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /import treatment-plan aggregate/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('Imported Patient ID 812 from manual_upload.')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/manual-uploads/treatment-plan-aggregate', expect.objectContaining({ method: 'POST' }))
  })

  it('uploads parsed text treatment-plan files through the backend', async () => {
    const fetchMock = setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Manual Upload' }))
    fireEvent.change(screen.getByLabelText(/patient id override/i), { target: { value: '914' } })
    const file = new File(['Patient ID: 914\nIntervention: Weekly CBT skills practice.'], 'manual-text.txt', {
      type: 'text/plain',
    })
    fireEvent.change(screen.getByLabelText(/treatment-plan file \(TXT, CSV, TSV, MD, text-extractable PDF, XLSX\)/i), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /upload and parse treatment-plan file/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('Imported Patient ID 914 from parsed manual_upload file and archived encrypted source file.')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/manual-uploads/treatment-plan-file', expect.objectContaining({ method: 'POST', body: expect.any(FormData) }))
  })

  it('posts confirmed patient ID corrections for parsed treatment-plan files', async () => {
    setupFetch()
    await signIn()

    fireEvent.click(screen.getByRole('button', { name: 'Manual Upload' }))
    fireEvent.change(screen.getByLabelText(/patient id override/i), { target: { value: '914' } })
    fireEvent.click(screen.getByLabelText(/I confirm this override corrects/i))
    const file = new File(['Patient ID: 913\nIntervention: Synthetic correction review.'], 'manual-correction.txt', {
      type: 'text/plain',
    })
    fireEvent.change(screen.getByLabelText(/treatment-plan file \(TXT, CSV, TSV, MD, text-extractable PDF, XLSX\)/i), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /upload and parse treatment-plan file/i }))

    expect(await screen.findByRole('status')).toHaveTextContent('Imported Patient ID 914 from parsed manual_upload file after confirmed Patient ID correction and archived encrypted source file.')
  })
})
