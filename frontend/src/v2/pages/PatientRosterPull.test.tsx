import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PatientRosterPage } from './PatientRosterPage'
import { TreatmentPlansRosterPage } from './TreatmentPlansRosterPage'
import type { UserProfile } from '../api/types'

const adminUser: UserProfile = {
  id: 1,
  username: 'admin',
  fullName: 'Local Administrator',
  role: 'admin',
  isActive: true,
  isLocked: false,
  mustResetPassword: false,
  authState: 'active',
  lockedUntil: '',
  facilityIds: [10],
}

describe('Patient roster pull', () => {
  afterEach(() => vi.unstubAllGlobals())

  it.each(['patient', 'treatment-plan'] as const)('preserves %s pull completion while refreshed rows are pending', async (kind) => {
    const rosterPath = kind === 'patient' ? '/api/v2/patient-roster' : '/api/v2/treatment-plan-roster'
    const startPath = kind === 'patient' ? '/api/v2/patient-roster/pull' : '/api/v2/alleva-sync/run'
    const pollPath = kind === 'patient' ? '/api/v2/patient-roster/jobs/roster-1' : '/api/v2/alleva-sync/jobs/roster-1'
    let rosterReads = 0
    let releaseRefresh: ((value: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost').pathname
      if (path === rosterPath) {
        rosterReads += 1
        if (rosterReads === 1) return response({ items: [] })
        return new Promise<Response>((resolve) => { releaseRefresh = resolve })
      }
      if (path === '/api/api-configuration') return response(configuredProfile())
      if (path === '/api/v2/patient-roster/jobs/latest') return response({}, 404)
      if (path === startPath) return response(job('queued', 0), 202)
      if (path === pollPath) return response(job('completed', 100))
      return response({}, 404)
    }))
    const Page = kind === 'patient' ? PatientRosterPage : TreatmentPlansRosterPage
    render(<Page token='token' user={adminUser} onNavigate={vi.fn()} onSelectPatient={vi.fn()} onSelectTreatmentPlan={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: kind === 'patient' ? 'Pull patient roster' : 'Pull full treatment plans' }))
    try {
      await waitFor(() => expect(rosterReads).toBe(2))
      expect(await screen.findByRole('status')).toHaveTextContent(kind === 'patient' ? '1 record updated' : '1 treatment plan')
      expect(screen.getByText(kind === 'patient' ? 'Loading patient roster...' : 'Loading treatment plans roster...')).toBeInTheDocument()
    } finally {
      await act(async () => { releaseRefresh?.(response({ items: [] })) })
    }
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(kind === 'patient' ? '1 record updated' : '1 treatment plan')
  })

  it('pulls the complete roster through the roster job and refreshes visible data', async () => {
    // Given: an authorized Alleva profile and an initially empty local roster.
    let rosterReads = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost').pathname
      const method = init?.method ?? 'GET'
      if (path === '/api/v2/patient-roster') {
        rosterReads += 1
        return response({ items: rosterReads > 1 ? [rosterItem()] : [] })
      }
      if (path === '/api/api-configuration') return response(configuredProfile())
      if (path === '/api/v2/patient-roster/jobs/latest') return response({}, 404)
      if (path === '/api/v2/patient-roster/pull' && method === 'POST') return response(job('queued', 0), 202)
      if (path === '/api/v2/patient-roster/jobs/roster-1') return response(job('completed_with_warnings', 100))
      return response({ detail: `Unexpected ${method} ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<PatientRosterPage token='token' user={adminUser} onNavigate={vi.fn()} onSelectPatient={vi.fn()} onSelectTreatmentPlan={vi.fn()} />)

    // When: the administrator pulls the complete patient roster.
    fireEvent.click(await screen.findByRole('button', { name: 'Pull patient roster' }))

    // Then: the roster-specific endpoint runs, warning completion is visible, and the roster refreshes.
    expect(await screen.findByText('client-812')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/completed with warnings/i)
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/patient-roster/pull', expect.objectContaining({ method: 'POST' }))
    await waitFor(() => expect(rosterReads).toBeGreaterThanOrEqual(2))
  })
})

function configuredProfile() {
  return {
    vendor_name: 'Alleva REST API', api_base_url: 'https://api.allevasoft.com', openapi_url: '',
    token_url: 'https://authorization.allevasoft.com/connect/token', client_id_configured: true,
    api_key_configured: true, client_secret_configured: true, token_auth_style: 'body', scopes: '',
    api_version: '1.0', treatment_plan_start_date: '2020-01-01T00:00:00Z', pagination_limit: 100,
    sync_limit: 100, requests_per_minute: 600, timeout_seconds: 10, api_enabled: true,
    treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true,
    active_contract_version: 'alleva-rest-v1', active_contract_effective_at: null,
  }
}

function rosterItem() {
  return {
    patient_record_id: 6812,
    mrn: 'client-812', full_name: 'Synthetic Patient', source_mode: 'alleva_rest_api', lifecycle_state: 'active',
    current_level_of_care: 'PHP', treatment_plans: [], first_seen_at: '2026-07-14T10:00:00Z',
    last_seen_at: '2026-07-14T10:01:00Z', reconciled_at: '2026-07-14T10:01:00Z',
  }
}

function job(status: string, progress: number) {
  return {
    job_id: 'roster-1', job_type: 'active_patient_roster_pull', created_at: '2026-07-14T10:00:00Z',
    started_at: '2026-07-14T10:00:01Z', updated_at: '2026-07-14T10:00:02Z',
    completed_at: progress === 100 ? '2026-07-14T10:00:02Z' : null, cancelled_at: null, failed_at: null,
    status, phase: progress === 100 ? 'completed' : 'queued', message: 'Sanitized roster status.',
    progress_percent: progress, current_endpoint: 'GET /clients', current_page: 1, records_seen: 1,
    records_written: progress === 100 ? 1 : 0, records_failed: 0, warnings_count: progress === 100 ? 1 : 0,
    errors_count: 0, cancel_requested: false, last_heartbeat_at: '2026-07-14T10:00:02Z', artifacts: [],
  }
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } })
}
