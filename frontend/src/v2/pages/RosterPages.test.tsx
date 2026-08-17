import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PatientSelection, TreatmentPlanSelection, UserProfile } from '../api/types'
import { PatientRosterPage } from './PatientRosterPage'
import { TreatmentPlansRosterPage } from './TreatmentPlansRosterPage'

const viewer: UserProfile = {
  id: 4,
  username: 'viewer',
  fullName: 'Synthetic Viewer',
  role: 'viewer',
  isActive: true,
  isLocked: false,
  mustResetPassword: false,
  authState: 'active',
  lockedUntil: '',
  facilityIds: [10],
}

describe('MRN-centered roster pages', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists every patient treatment plan in descending update order and selects one exact plan', async () => {
    const onSelectTreatmentPlan = vi.fn<(selection: TreatmentPlanSelection) => void>()
    const onSelectPatient = vi.fn<(selection: PatientSelection) => void>()
    vi.stubGlobal('fetch', vi.fn(async () => response({
      items: [{
        mrn: 'MRN-812',
        full_name: 'Alex Example',
        source_mode: 'alleva_rest_api',
        lifecycle_state: 'active',
        current_level_of_care: 'PHP',
        treatment_plans: [
          { treatment_plan_id: 'plan-813', last_updated: '2026-07-09T17:45:00Z' },
          { treatment_plan_id: 'plan-812', last_updated: '2026-07-01T08:15:00Z' },
        ],
        first_seen_at: '2026-06-01T10:00:00Z',
        last_seen_at: '2026-07-10T10:00:00Z',
        reconciled_at: '',
      }],
    })))
    render(
      <PatientRosterPage
        token='token'
        user={viewer}
        onNavigate={vi.fn()}
        onSelectPatient={onSelectPatient}
        onSelectTreatmentPlan={onSelectTreatmentPlan}
      />,
    )

    const table = await screen.findByRole('table')
    expect(within(table).getByRole('columnheader', { name: 'MRN' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Treatment Plans' })).toBeInTheDocument()
    expect(within(table).getByText('MRN-812').closest('td')).toHaveAttribute('headers', 'patient-roster-mrn')
    expect(within(table).getByText('Alex Example')).toBeInTheDocument()
    expect(within(table).getByText('Alex Example').parentElement).toHaveClass('patient-identity')
    fireEvent.click(within(table).getByRole('button', { name: 'Open patient record for Alex Example, MRN MRN-812' }))
    expect(onSelectPatient).toHaveBeenCalledWith({ mrn: 'MRN-812', patientKey: 'MRN-812', sourceMode: 'alleva_rest_api' })
    expect(within(table).queryByRole('columnheader', { name: 'Status' })).not.toBeInTheDocument()
    expect(within(table).queryByRole('columnheader', { name: 'Treatment Plan ID' })).not.toBeInTheDocument()
    const selector = within(table).getByRole('combobox', { name: 'Treatment plans for MRN MRN-812' })
    expect(within(selector).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Select a treatment plan',
      '(#plan-813) 2026-07-09 17:45 UTC',
      '(#plan-812) 2026-07-01 08:15 UTC',
    ])

    fireEvent.change(selector, { target: { value: 'plan-812' } })

    expect(onSelectTreatmentPlan).toHaveBeenCalledWith({
      mrn: 'MRN-812',
      patientKey: 'MRN-812',
      treatmentPlanId: 'plan-812',
      sourceMode: 'alleva_rest_api',
    })
  })

  it('shows Alleva plan lineage and opens the selected full-detail record', async () => {
    const onSelectTreatmentPlan = vi.fn<(selection: TreatmentPlanSelection) => void>()
    const onSelectPatient = vi.fn<(selection: PatientSelection) => void>()
    vi.stubGlobal('fetch', vi.fn(async () => response({
      items: [{
        treatment_plan_id: 'plan-813',
        mrn: 'MRN-812',
        patient_key: 'MRN-812',
        linked_to_mrn: true,
        full_name: 'Alex Example',
        last_updated: '2026-07-09T17:45:00Z',
        previous_treatment_plan_id: 'plan-812',
        initial_treatment_plan_id: 'plan-800',
        initial_treatment_plan_date: '2026-01-03',
      }],
    })))
    render(
      <TreatmentPlansRosterPage
        token='token'
        user={viewer}
        onNavigate={vi.fn()}
        onSelectPatient={onSelectPatient}
        onSelectTreatmentPlan={onSelectTreatmentPlan}
      />,
    )

    const table = await screen.findByRole('table')
    expect(within(table).getByText('MRN-812')).toBeInTheDocument()
    expect(within(table).getByText('MRN-812').closest('td')).toHaveAttribute('headers', 'plan-roster-mrn')
    expect(within(table).getByText('Alex Example')).toBeInTheDocument()
    expect(within(table).getByText('Alex Example').parentElement).toHaveClass('patient-identity')
    fireEvent.click(within(table).getByRole('button', { name: 'Open patient record for Alex Example, MRN MRN-812' }))
    expect(onSelectPatient).toHaveBeenCalledWith({ mrn: 'MRN-812', patientKey: 'MRN-812', sourceMode: 'alleva_rest_api' })
    expect(within(table).getByText('plan-812')).toBeInTheDocument()
    expect(within(table).getByText('(#plan-800) 2026-01-03')).toBeInTheDocument()
    fireEvent.click(within(table).getByRole('button', { name: 'Open treatment plan plan-813 for MRN MRN-812' }))

    expect(onSelectTreatmentPlan).toHaveBeenCalledWith({
      mrn: 'MRN-812',
      patientKey: 'MRN-812',
      treatmentPlanId: 'plan-813',
      sourceMode: 'alleva_rest_api',
    })
  })
})

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}
