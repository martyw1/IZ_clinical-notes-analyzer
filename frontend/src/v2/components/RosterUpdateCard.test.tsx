import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { RosterUpdateCard } from './RosterUpdateCard'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
const config = { client_id_configured: true, client_secret_configured: true, api_enabled: true,
  treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true }
const job = { job_id: 'synthetic-update', job_type: 'two_stage_roster_update', status: 'running',
  stage_number: 2, phase: 'fetching_plan_details', phase_completed: 4, phase_total: 10,
  progress_percent: 40, progress_determinate: true, records_seen: 10, records_written: 0 }

test('starts the backend workflow and keeps the panel usable while progress is pending', async () => {
  let finish: (value: Response) => void = () => {}
  const completed = vi.fn()
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    if (path === '/api/api-configuration') return response(config)
    if (path === '/api/v2/roster-update/latest') return response({}, 404)
    if (path === '/api/v2/roster-update/run') return response(job, 202)
    if (path.endsWith('/cancel')) return response({ ...job, cancel_requested: true })
    if (path.endsWith('/synthetic-update')) return new Promise<Response>((resolve) => { finish = resolve })
    throw new Error(`Unexpected synthetic route ${path} ${init?.method}`)
  })
  vi.stubGlobal('fetch', fetch)
  render(<RosterUpdateCard token='synthetic-token' onCompleted={completed} />)
  const start = screen.getByRole('button', { name: 'Update patients and treatment plans' })
  await waitFor(() => expect(start).toBeEnabled())
  fireEvent.click(start)
  expect(await screen.findByText(/Stage 2 of 2/)).toBeVisible()
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40')
  expect(screen.getByRole('button', { name: 'Cancel local update' })).toBeEnabled()
  await act(async () => { finish(response({ ...job, status: 'completed', progress_percent: 100 })) })
  expect(completed).toHaveBeenCalledTimes(1)
  expect(await screen.findByText(/up to date for this pull/)).toBeVisible()
  expect(fetch.mock.calls.filter(([path]) => path === '/api/v2/roster-update/run')).toHaveLength(1)
})

test('restores an in-progress workflow without submitting another pull', async () => {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input)
    if (path === '/api/api-configuration') return response(config)
    if (path === '/api/v2/roster-update/latest') return response(job)
    if (path.endsWith('/synthetic-update')) return response({ ...job, status: 'completed_with_warnings' })
    return response({}, 404)
  })
  vi.stubGlobal('fetch', fetch)
  render(<RosterUpdateCard token='synthetic-token' onCompleted={vi.fn()} />)
  expect(await screen.findByText(/Update completed with partial results/)).toBeVisible()
  expect(fetch.mock.calls.some(([path]) => path === '/api/v2/roster-update/run')).toBe(false)
})
