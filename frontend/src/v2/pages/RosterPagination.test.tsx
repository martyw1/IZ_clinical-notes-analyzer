import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { PatientRosterPage } from './PatientRosterPage'
import { TreatmentPlansRosterPage } from './TreatmentPlansRosterPage'
import type { UserProfile } from '../api/types'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test.each(['patients', 'plans'])('%s roster renders bounded pages and searches all saved rows', async (kind) => {
  const items = Array.from({ length: 81 }, (_, index) => ({
    patient_record_id: index + 1, plan_version_id: index + 1, mrn: `SYNTHETIC-${index + 1}`,
    full_name: `Synthetic row ${index + 1}`, source_mode: 'manual_upload', lifecycle_state: 'active',
    current_level_of_care: index === 79 ? 'Case Management' : 'PHP-5', treatment_plans: [], treatment_plan_id: `synthetic-plan-${index + 1}`,
    linked_to_mrn: true, patient_key: `SYNTHETIC-${index + 1}`,
  }))
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items }))))
  const props = { token: 'synthetic-token', user: { role: 'viewer' } as UserProfile,
    onNavigate: vi.fn(), onSelectPatient: vi.fn(), onSelectTreatmentPlan: vi.fn() }
  render(kind === 'patients' ? <PatientRosterPage {...props} /> : <TreatmentPlansRosterPage {...props} />)
  const table = await screen.findByRole('table')
  expect(within(table).getAllByRole('row')).toHaveLength(76)
  fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
  expect(within(table).getAllByRole('row')).toHaveLength(7)
  expect(screen.getByText('Showing 76–81 of 81')).toBeVisible()
  if (kind === 'patients') {
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'active' } })
    expect(screen.getByText('Showing 1–75 of 81')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Level of care'), { target: { value: 'Case Management' } })
    expect(within(table).getAllByRole('row')).toHaveLength(2)
    expect(screen.getByText('SYNTHETIC-80', { exact: true })).toBeVisible()
  }
  const search = screen.getByRole('textbox')
  fireEvent.change(search, { target: { value: 'SYNTHETIC-80' } })
  expect(within(table).getAllByRole('row')).toHaveLength(2)
  expect(screen.getByText('SYNTHETIC-80', { exact: true })).toBeVisible()
})


test('overdue by clinician groups alphabetically with highest days overdue first and filters by clinician', async () => {
  const items = [
    { id: 1, name: 'Synthetic Beta', days: 90 },
    { id: 2, name: 'Synthetic Alpha', days: 5 },
    { id: 3, name: 'Synthetic Alpha', days: 30 },
  ].map(({ id, name, days }) => ({
    patient_record_id: id, plan_version_id: id, mrn: `SYNTHETIC-${id}`, full_name: '',
    source_mode: 'manual_upload', treatment_plan_id: `plan-${id}`, linked_to_mrn: true, patient_key: `SYNTHETIC-${id}`,
    primary_counselor_id: name.endsWith('Alpha') ? 2 : 1, primary_counselor_name: name,
    deadline_status: 'Overdue', days_overdue: days, next_due_date: '2026-01-01',
  }))
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ items }))))
  render(<TreatmentPlansRosterPage token='synthetic' user={{ role: 'viewer' } as UserProfile}
    onNavigate={vi.fn()} onSelectPatient={vi.fn()} onSelectTreatmentPlan={vi.fn()} />)
  await screen.findByRole('table')
  fireEvent.change(screen.getByLabelText('Worklist'), { target: { value: 'Overdue by clinician' } })
  const buttons = within(screen.getByRole('table')).getAllByRole('button', { name: /^Open treatment plan/ })
  expect(buttons.map((button) => button.textContent)).toEqual(['plan-3', 'plan-2', 'plan-1'])
  expect(screen.getByRole('rowheader', { name: /Synthetic Alpha/ })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Synthetic Alpha (#2) (2)' }))
  expect(within(screen.getByRole('table')).getAllByRole('button', { name: /^Open treatment plan/ })).toHaveLength(2)
})
