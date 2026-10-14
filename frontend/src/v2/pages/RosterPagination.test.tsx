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
    current_level_of_care: 'PHP', treatment_plans: [], treatment_plan_id: `synthetic-plan-${index + 1}`,
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
  const search = screen.getByRole('textbox')
  fireEvent.change(search, { target: { value: 'SYNTHETIC-80' } })
  expect(within(table).getAllByRole('row')).toHaveLength(2)
  expect(screen.getByText('SYNTHETIC-80', { exact: true })).toBeVisible()
})
