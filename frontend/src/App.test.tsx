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
    client_name: 'Aegis Test',
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

describe('App chart audit flow', () => {
  it('renders dashboard, queue, and checklist after login', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-a', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, [chartSummary()]),
      makeResponse(200, templatePayload()),
      makeResponse(200, chartDetail()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Admin Dashboard')).toBeInTheDocument())
    expect(screen.getByText('Combined Audit Flow')).toBeInTheDocument()
    expect(screen.getByText('Review Criteria')).toBeInTheDocument()
    expect(screen.getAllByText('Aegis Test').length).toBeGreaterThan(0)
  })

  it('shows the new audit form when the queue is empty', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-b', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Create audit and load checklist' })).toBeInTheDocument()
  })

  it('creates a new audit from the guided intake form', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-c', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
      makeResponse(200, chartDetail()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Aegis Test' } })
    fireEvent.change(screen.getByLabelText('Level of care'), { target: { value: 'Residential' } })
    fireEvent.change(screen.getByLabelText('Primary clinician'), { target: { value: 'Marleigh Johnson' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create audit and load checklist' }))

    await waitFor(() => expect(screen.getByText('Review Criteria')).toBeInTheDocument())
    expect(screen.getAllByText('Aegis Test').length).toBeGreaterThan(0)
  })

  it('completes reset and lands in the audit workspace', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-d', must_reset_password: true }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: true }),
      makeResponse(200, { status: 'ok' }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
      makeResponse(200, templatePayload()),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Password Reset Required')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('New password (min 12 chars)'), { target: { value: 'new-password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(screen.getByText('New Chart Audit')).toBeInTheDocument())
  })
})
