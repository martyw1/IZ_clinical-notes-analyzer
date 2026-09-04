import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { ForensicLogsPage } from './ForensicLogsPage'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test('renders forensic history timestamps with an explicit UTC display', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response({
    items: [{
      event_id: 'audit-1',
      timestamp_utc: '2026-08-01T12:34:00-04:00',
      actor_username: 'synthetic_manager',
      actor_role: 'office_manager',
      action: 'reviewed',
      target_entity_type: 'treatment_plan',
      target_entity_id: 'plan-1',
      outcome_status: 'success',
      details: { source: 'synthetic_fixture' },
    }],
  })))

  render(<ForensicLogsPage token='token' />)

  const timestamp = await screen.findByText('2026-08-01 16:34 UTC')
  expect(timestamp).toBeInTheDocument()
  expect(timestamp.tagName).toBe('TIME')
  expect(timestamp).toHaveAttribute('dateTime', '2026-08-01T12:34:00-04:00')
})

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

test('does not shift a naive backend UTC audit timestamp to browser local time', async () => {
  // Given: the real SQLite-backed API emits a naive UTC timestamp.
  vi.stubGlobal('fetch', vi.fn(async () => response({ items: [{ event_id: 'audit-utc',
    timestamp_utc: '2026-09-04 04:46:28.560103', action: 'login', actor_role: 'admin',
    target_entity_type: 'auth', target_entity_id: 'synthetic', outcome_status: 'success', details: {},
  }] })))
  // When: the event is displayed with an explicit UTC label.
  render(<ForensicLogsPage token='synthetic-nonworking-token' />)
  // Then: its UTC clock value remains unchanged in America/New_York.
  expect(await screen.findByText('2026-09-04 04:46 UTC')).toHaveAttribute('dateTime', '2026-09-04 04:46:28.560103')
})
