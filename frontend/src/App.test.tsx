import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { App } from './App'

declare global {
  // eslint-disable-next-line no-var
  var fetch: typeof window.fetch
}

type RouteHandler = (path: string, init?: RequestInit) => { status?: number; body?: unknown }

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response
}

function installFetchMock(routes: Record<string, unknown | RouteHandler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === 'string' ? input : input.toString()
    const url = new URL(rawUrl, 'http://localhost')
    const key = `${(init?.method || 'GET').toUpperCase()} ${url.pathname}`
    const route = routes[key]
    if (!route) {
      throw new Error(`Unhandled request ${key}`)
    }

    if (typeof route === 'function') {
      const result = route(url.pathname, init)
      return jsonResponse(result.status ?? 200, result.body)
    }

    return jsonResponse(200, route)
  })

  global.fetch = fn as unknown as typeof window.fetch
  return fn
}

function userPayload(role: 'admin' | 'counselor' | 'manager', mustResetPassword = false) {
  return {
    id: role === 'admin' ? 1 : role === 'manager' ? 2 : 3,
    username: role,
    full_name: role === 'manager' ? 'Office Manager' : role === 'counselor' ? 'Counselor One' : 'System Administrator',
    role,
    is_active: true,
    is_locked: false,
    must_reset_password: mustResetPassword,
    last_login_at: '2026-03-08T12:00:00Z',
    created_at: '2026-03-08T11:00:00Z',
  }
}

function chartSummary(state: string = 'Awaiting Office Manager Review') {
  return {
    id: 8,
    source_note_set_id: 5,
    patient_id: 'PAT-001',
    client_name: 'PAT-001',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    primary_clinician: 'Marleigh Johnson',
    auditor_name: 'Counselor One',
    other_details: 'Auto-generated from uploaded clinical note binder.',
    counselor_id: 3,
    state,
    system_score: 84,
    system_summary: 'System evaluation completed for patient PAT-001.',
    manager_comment: state === 'Returned to Counselor' ? 'Attendance consent is missing a clear selection.' : '',
    reviewed_by_id: state === 'Awaiting Office Manager Review' ? null : 2,
    system_generated_at: '2026-03-08T12:00:00Z',
    reviewed_at: state === 'Awaiting Office Manager Review' ? null : '2026-03-08T13:00:00Z',
    created_at: '2026-03-08T12:00:00Z',
    notes: 'Binder uploaded from Alleva.',
    pending_items: 2,
    passed_items: 13,
    failed_items: 3,
    not_applicable_items: 0,
  }
}

function chartDetail(state: string = 'Awaiting Office Manager Review') {
  return {
    ...chartSummary(state),
    checklist_items: [
      {
        item_key: 'attendance_policy_consent',
        step: 5,
        section: 'Other / Admission Packet',
        label: 'Attendance Policy Consent',
        timeframe: 'Completed at admission',
        instructions: 'Verify that exactly one Accept or Decline option is selected and the form is fully signed.',
        evidence_hint: 'Note the selected option and whether both signatures are present.',
        policy_note: null,
        status: 'no',
        notes: 'Accept or Decline could not be confirmed from the uploaded packet.',
        evidence_location: 'Attendance Policy Consent (custom forms)',
        evidence_date: '04/01/2025',
        expiration_date: '',
      },
      {
        item_key: 'client_overview_primary_clinician',
        step: 2,
        section: 'Header Verification',
        label: 'Primary clinician assignment',
        timeframe: 'Audit setup',
        instructions: 'Confirm the primary clinician field is populated correctly in Client Overview before continuing the audit.',
        evidence_hint: 'Capture where the clinician assignment was verified and note any mismatch.',
        policy_note: null,
        status: 'yes',
        notes: 'Primary clinician supplied with uploaded binder.',
        evidence_location: 'Upload header',
        evidence_date: '04/01/2025',
        expiration_date: '',
      },
    ],
  }
}

function noteSetSummary() {
  return {
    id: 5,
    patient_id: 'PAT-001',
    review_chart_id: 8,
    version: 1,
    status: 'active',
    upload_mode: 'initial',
    source_system: 'Alleva EMR',
    primary_clinician: 'Marleigh Johnson',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    upload_notes: 'Initial Alleva upload.',
    created_at: '2026-03-08T12:00:00Z',
    file_count: 1,
  }
}

function noteSetDetail() {
  return {
    ...noteSetSummary(),
    documents: [
      {
        id: 14,
        document_label: 'Intake Packet',
        original_filename: 'intake-packet.txt',
        content_type: 'text/plain',
        size_bytes: 2048,
        sha256: 'a'.repeat(64),
        alleva_bucket: 'custom_forms',
        document_type: 'clinical_note',
        completion_status: 'completed',
        client_signed: true,
        staff_signed: true,
        document_date: '04/01/2025',
        description: 'Admission binder import.',
        created_at: '2026-03-08T12:00:00Z',
      },
    ],
  }
}

describe('App turnkey workflow', () => {
  it('renders the summary dashboard and admin tools for administrators', async () => {
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-a', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Summary dashboard' })).toBeInTheDocument())
    expect(screen.getAllByRole('button', { name: 'User management' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'My account' }).length).toBeGreaterThan(0)
    expect(screen.getByText('Waiting re-verification')).toBeInTheDocument()
  })

  it('uploads a note binder and opens the generated automated review', async () => {
    let chartCalls = 0
    let noteSetCalls = 0

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-b', must_reset_password: false },
      'GET /api/users/me': userPayload('counselor'),
      'POST /api/patient-note-sets/detect-patient-id': {
        patient_id: 'PAT-001',
        confidence: 'high',
        source_filename: 'intake-packet.txt',
        source_kind: 'text_label',
        match_text: 'Patient ID: PAT-001',
        reason: 'Detected patient ID from labeled content in intake-packet.txt.',
      },
      'GET /api/charts': () => {
        chartCalls += 1
        return { body: chartCalls === 1 ? [] : [chartSummary()] }
      },
      'GET /api/patient-note-sets': () => {
        noteSetCalls += 1
        return { body: noteSetCalls === 1 ? [] : [noteSetSummary()] }
      },
      'POST /api/patient-note-sets': noteSetDetail(),
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload clinical notes' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Upload clinical notes' }))

    fireEvent.change(screen.getByLabelText('Level of care'), { target: { value: 'Residential' } })
    fireEvent.change(screen.getByLabelText('Primary clinician'), { target: { value: 'Marleigh Johnson' } })
    fireEvent.change(screen.getByLabelText('Clinical note files'), {
      target: {
        files: [new File(['Intake packet completed.'], 'intake-packet.txt', { type: 'text/plain' })],
      },
    })
    await waitFor(() => expect(screen.getByLabelText('Patient ID')).toHaveValue('PAT-001'))
    fireEvent.click(screen.getByRole('button', { name: 'Upload and run automated evaluation' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Criterion review workbench' })).toBeInTheDocument())
    expect(screen.getAllByText('Attendance Policy Consent').length).toBeGreaterThan(0)
  })

  it('lets an office manager drill into a criterion and save a decision', async () => {
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-c', must_reset_password: false },
      'GET /api/users/me': userPayload('manager'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'PUT /api/charts/8': (_, init) => {
        const body = JSON.parse(String(init?.body || '{}'))
        const savedItem = body.checklist_items.find((item: { item_key: string }) => item.item_key === 'attendance_policy_consent')
        return {
          body: {
            ...chartDetail(),
            checklist_items: [
              {
                ...chartDetail().checklist_items[0],
                status: savedItem.status,
                notes: savedItem.notes,
              },
              chartDetail().checklist_items[1],
            ],
          },
        }
      },
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Review queue' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Review queue' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Criterion review workbench' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Mark OK' }))
    fireEvent.change(screen.getByLabelText('Reviewer notes'), {
      target: { value: 'Manager confirmed the consent page manually.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save criterion review changes' }))

    await waitFor(() => expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0))
  })

  it('shows profile management, admin user management, and forensic logs', async () => {
    let directory = [userPayload('admin'), userPayload('manager')]

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-d', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': () => ({ body: directory }),
      'POST /api/users': (_, init) => {
        const body = JSON.parse(String(init?.body || '{}'))
        const created = {
          ...userPayload('counselor'),
          id: 7,
          username: body.username,
          full_name: body.full_name,
          role: body.role,
          must_reset_password: true,
        }
        directory = [...directory, created]
        return { body: created }
      },
      'PATCH /api/users/me': { ...userPayload('admin'), full_name: 'System Administrator Updated' },
      'GET /api/audit/logs': [
        {
          event_id: 'evt-1',
          timestamp_utc: '2026-03-08T13:00:00Z',
          actor_username: 'admin',
          actor_role: 'admin',
          actor_type: 'human',
          source_ip: '127.0.0.1',
          request_id: 'req-1',
          event_category: 'workflow',
          action: 'chart.system_evaluated',
          patient_id: 'PAT-001',
          message: 'Automated evaluation completed for chart 8.',
          outcome_status: 'success',
          severity: 'info',
        },
      ],
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'My account' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'My account' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'User profile' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'System Administrator Updated' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => expect(screen.getByText('Your profile has been updated.')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'User management' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Create user' })).toBeInTheDocument())
    const createUserSection = screen.getByRole('heading', { name: 'Create user' }).closest('section')
    expect(createUserSection).not.toBeNull()
    const createUserScope = within(createUserSection as HTMLElement)
    fireEvent.change(createUserScope.getByLabelText('Username'), { target: { value: 'counselor-02' } })
    fireEvent.change(createUserScope.getByLabelText('Full name'), { target: { value: 'Counselor Two' } })
    fireEvent.change(createUserScope.getByLabelText('Temporary password'), { target: { value: 'temporary-pass-1234' } })
    fireEvent.click(createUserScope.getByRole('button', { name: 'Create user' }))

    await waitFor(() => expect(screen.getByText('User counselor-02 created successfully.')).toBeInTheDocument())
    expect(screen.getByText('Counselor Two')).toBeInTheDocument()
    expect(screen.getByText('counselor-02')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Forensic logs' }))
    await waitFor(() => expect(screen.getByText('chart.system_evaluated')).toBeInTheDocument())
  })

  it('completes a required password reset before loading the workspace', async () => {
    let meCalls = 0
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-e', must_reset_password: true },
      'GET /api/users/me': () => {
        meCalls += 1
        return { body: userPayload('counselor', meCalls === 1) }
      },
      'POST /api/auth/reset-password': { status: 'ok' },
      'GET /api/charts': [],
      'GET /api/patient-note-sets': [],
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Password reset required')).toBeInTheDocument())
    fireEvent.change(screen.getByPlaceholderText('New password (min 12 chars)'), {
      target: { value: 'new-password-1234' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Summary dashboard' })).toBeInTheDocument())
  })
})
