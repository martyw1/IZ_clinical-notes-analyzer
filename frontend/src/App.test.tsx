import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App } from './App'

declare global {
  // eslint-disable-next-line no-var
  var fetch: typeof window.fetch
}

type MockResponse = { ok: boolean; status: number; json: () => Promise<unknown> }

function makeResponse(status: number, payload: unknown): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

function mockFetchSequence(responses: MockResponse[]) {
  const fn = vi.fn()
  responses.forEach((response) => fn.mockResolvedValueOnce(response))
  global.fetch = fn as unknown as typeof window.fetch
  return fn
}

function templatePayload() {
  return [
    {
      section: 'Header Verification',
      items: [
        {
          key: 'client_overview_episode_metadata',
          step: 1,
          section: 'Header Verification',
          label: 'Client overview episode metadata',
          timeframe: 'Audit setup',
          instructions: 'Confirm episode dates and LOC.',
          evidence_hint: 'Record where the evidence was found.',
          policy_note: null,
        },
      ],
    },
  ]
}

function chartSummary() {
  return {
    id: 1,
    patient_id: 'PAT-001',
    client_name: 'PAT-001',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    primary_clinician: 'Marleigh Johnson',
    auditor_name: 'admin',
    other_details: '',
    counselor_id: 1,
    state: 'Draft',
    notes: '',
    pending_items: 1,
    passed_items: 0,
    failed_items: 0,
    not_applicable_items: 0,
  }
}

function chartDetail() {
  return {
    ...chartSummary(),
    checklist_items: [
      {
        item_key: 'client_overview_episode_metadata',
        step: 1,
        section: 'Header Verification',
        label: 'Client overview episode metadata',
        timeframe: 'Audit setup',
        instructions: 'Confirm episode dates and LOC.',
        evidence_hint: 'Record where the evidence was found.',
        policy_note: null,
        status: 'pending',
        notes: '',
        evidence_location: '',
        evidence_date: '',
        expiration_date: '',
      },
    ],
  }
}

function noteSetSummary() {
  return {
    id: 5,
    patient_id: 'PAT-001',
    version: 1,
    status: 'active',
    upload_mode: 'initial',
    source_system: 'Alleva EMR',
    primary_clinician: 'Marleigh Johnson',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    upload_notes: 'Initial Alleva intake upload.',
    created_at: '2026-03-08T00:00:00Z',
    file_count: 1,
  }
}

function noteSetDetail() {
  return {
    ...noteSetSummary(),
    documents: [
      {
        id: 11,
        document_label: 'Intake Packet',
        original_filename: 'intake-packet.pdf',
        content_type: 'application/pdf',
        size_bytes: 2048,
        sha256: 'a'.repeat(64),
        alleva_bucket: 'custom_forms',
        document_type: 'clinical_note',
        completion_status: 'completed',
        client_signed: true,
        staff_signed: true,
        document_date: '04/01/2025',
        description: 'Admission binder import.',
        created_at: '2026-03-08T00:00:00Z',
      },
    ],
  }
}

describe('App chart audit flow', () => {
  it('renders dashboard, queue, note set panel, and checklist after login', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-a', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, [chartSummary()]),
      makeResponse(200, templatePayload()),
      makeResponse(200, []),
      makeResponse(200, chartDetail()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Admin Dashboard')).toBeInTheDocument())
    expect(screen.getByText('Clinical Note Sets')).toBeInTheDocument()
    expect(screen.getByText('Review Criteria')).toBeInTheDocument()
    expect(screen.getAllByText('PAT-001').length).toBeGreaterThan(0)
  })

  it('shows the new audit form when the queue and note sets are empty', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-b', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
      makeResponse(200, []),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Create audit and load checklist' })).toBeInTheDocument()
    expect(screen.getByLabelText('Patient ID')).toBeInTheDocument()
  })

  it('creates a new audit from the guided intake form', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-c', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
      makeResponse(200, []),
      makeResponse(200, chartDetail()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Patient ID'), { target: { value: 'PAT-001' } })
    fireEvent.change(screen.getByLabelText('Level of care'), { target: { value: 'Residential' } })
    fireEvent.change(screen.getByLabelText('Primary clinician'), { target: { value: 'Marleigh Johnson' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create audit and load checklist' }))

    await waitFor(() => expect(screen.getByText('Review Criteria')).toBeInTheDocument())
    expect(screen.getAllByText('PAT-001').length).toBeGreaterThan(0)
  })

  it('opens the patient note intake when note sets exist before audits', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-notes', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
      makeResponse(200, [noteSetSummary()]),
      makeResponse(200, noteSetDetail()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Patient Note Intake')).toBeInTheDocument())
    expect(screen.getByText('Patient PAT-001')).toBeInTheDocument()
    expect(screen.getByText('Intake Packet')).toBeInTheDocument()
  })

  it('completes reset and lands in the audit workspace', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-d', must_reset_password: true }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: true }),
      makeResponse(200, { status: 'ok' }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
      makeResponse(200, []),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Password Reset Required')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('New password (min 12 chars)'), { target: { value: 'new-password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
  })
})
