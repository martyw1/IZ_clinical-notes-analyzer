import { cleanup, render, screen, within, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { CounselorsPage } from './CounselorsPage'
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
test('loads a real directory table independently of slow treatment plan evaluation', async () => {
  vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('treatment-plan-roster')
    ? new Promise<Response>(() => {})
    : Promise.resolve(new Response(JSON.stringify(url.endsWith('/clinicians')
      ? { items: [{ id: 1, name: 'Synthetic Clinician' }] } : { items: [] })))))
  render(<CounselorsPage token='synthetic' isSessionCurrent={() => true} onSelectTreatmentPlan={vi.fn()} />)
  const table = screen.getByRole('table', { name: 'Clinician directory' })
  expect(await within(table).findByRole('button', { name: 'Synthetic Clinician (#1)' })).toBeVisible()
  expect(screen.getByText(/No mapped staff directory is saved/)).toBeVisible()
})
test('explains unmapped staff rather than treating unassigned as a staff directory', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items: [] }))))
  render(<CounselorsPage token='synthetic' isSessionCurrent={() => true} onSelectTreatmentPlan={vi.fn()} />)
  expect(await screen.findByText(/No verified clinician assignments have been imported/)).toBeVisible()
})


test('a failed directory request never claims a completed empty import', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('synthetic offline') }))
  render(<CounselorsPage token='synthetic' isSessionCurrent={() => true} onSelectTreatmentPlan={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('This is not an empty pull result')
  expect(screen.queryByText(/No verified clinician assignments/)).not.toBeInTheDocument()
})

test('opening directory does not request all rosters; selecting a clinician scopes both requests', async () => {
  const fetcher = vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith('/clinicians')
    ? { items: [{ id: 7, name: 'Synthetic Scoped' }] } : { items: [] })))
  vi.stubGlobal('fetch', fetcher)
  render(<CounselorsPage token='synthetic' isSessionCurrent={() => true} onSelectTreatmentPlan={vi.fn()} />)
  const button = await screen.findByRole('button', { name: 'Synthetic Scoped (#7)' })
  expect(fetcher).toHaveBeenCalledTimes(1)
  fireEvent.click(button)
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3))
  expect(fetcher.mock.calls.slice(1).every(([url]) => url.includes('primary_clinician_id=7'))).toBe(true)
})


test('retains incomplete clinicians and labels missing facilities explicitly', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({items:[
    {id:1,name:'Synthetic Missing',facility_status:'missing'},
    {id:2,name:'Synthetic Unmapped',facility_status:'unmapped'},
  ]}))))
  render(<CounselorsPage token='synthetic' isSessionCurrent={() => true} onSelectTreatmentPlan={vi.fn()} />)
  expect(await screen.findByRole('button',{name:'Synthetic Missing (#1)'})).toBeVisible()
  expect(screen.getByText('Missing in source')).toBeVisible()
  expect(screen.getByText('Not linked to a local facility')).toBeVisible()
})
