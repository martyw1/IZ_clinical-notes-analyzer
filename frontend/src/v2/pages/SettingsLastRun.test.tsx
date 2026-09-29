import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SettingsPage } from './SettingsPage'

describe('Settings persisted sync status', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hydrates the latest completed sync without starting another run', async () => {
    // Given: a persisted warning-complete sync exists when Settings opens.
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost').pathname
      if (path === '/api/settings') return response(settings())
      if (path === '/api/api-configuration') return response(configuration())
      if (path === '/api/v2/api-harness/jobs') return response([latestSync()])
      return response({ detail: `Unexpected ${init?.method ?? 'GET'} ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)

    // When: Settings loads.
    render(<SettingsPage token='token' />)

    // Then: the last run is visible and no new sync was started.
    expect(await screen.findByText('completed with warnings')).toBeInTheDocument()
    expect(screen.getByText('Updated').parentElement).toHaveTextContent('3')
    expect(screen.getByText('Warnings').parentElement).toHaveTextContent('2')
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalledWith('/api/v2/alleva-sync/run', expect.anything()))
  })

  it('saves organization settings without sending versioned clinical rules', async () => {
    // Given: Settings has loaded active clinical-rule values from the API.
    const patches: Record<string, unknown>[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost').pathname
      if (path === '/api/settings' && init?.method === 'PATCH') {
        patches.push(JSON.parse(String(init.body)) as Record<string, unknown>)
        return response(settings())
      }
      if (path === '/api/settings') return response(settings())
      if (path === '/api/api-configuration') return response(configuration())
      if (path === '/api/v2/api-harness/jobs') return response([])
      return response({ detail: `Unexpected ${init?.method ?? 'GET'} ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<SettingsPage token='token' />)
    await screen.findByText('Save settings')

    // When: an administrator saves the ordinary local settings.
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))

    // Then: only writable fields are submitted and clinical timing has no edit controls.
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(Object.keys(patches[0] ?? {}).sort()).toEqual(['facility_timezone', 'organization_name'])
    expect(screen.queryByRole('spinbutton', { name: 'LOC-change window days' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'LOC-change window validated' })).not.toBeInTheDocument()
  })
})

function latestSync() {
  return {
    job_id: 'sync-last', job_type: 'approved_treatment_plan_sync', created_at: '2026-07-14T09:00:00Z',
    started_at: '2026-07-14T09:00:01Z', updated_at: '2026-07-14T09:01:00Z', completed_at: '2026-07-14T09:01:00Z',
    status: 'completed_with_warnings', phase: 'completed_with_warnings', message: 'Completed with sanitized warnings.',
    progress_percent: 100, current_endpoint: 'GET /treatment-plans', current_page: 2, records_seen: 3,
    records_written: 3, records_failed: 0, warnings_count: 2, errors_count: 0, cancel_requested: false,
    last_heartbeat_at: '2026-07-14T09:01:00Z', artifacts: [],
  }
}

function configuration() {
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

function settings() {
  return {
    organization_name: 'R3 Recovery Services', facility_timezone: 'America/New_York',
    treatment_plan_master_due_days: 30, treatment_plan_php_review_interval_days: 30,
    treatment_plan_iop_op_review_interval_days: 60, treatment_plan_loc_change_window_days: 7,
    treatment_plan_loc_change_window_validated: false,
  }
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } })
}
