import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { TreatmentPlanSelection } from '../api/types'
import { PatientRecordDetailPage } from './PatientRecordDetailPage'

describe('Patient Record Detail selection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows every patient field in readable sections and opens an exact treatment plan', async () => {
    const fetchMock = vi.fn(async () => response(patientDetailPayload()))
    const onSelectTreatmentPlan = vi.fn<(selection: TreatmentPlanSelection) => void>()
    vi.stubGlobal('fetch', fetchMock)
    render(
      <PatientRecordDetailPage
        token='token'
        selection={{ mrn: 'MRN-812', patientKey: 'MRN-812', sourceMode: 'alleva_rest_api' }}
        onNavigate={vi.fn()}
        onSelectTreatmentPlan={onSelectTreatmentPlan}
      />,
    )

    expect(await screen.findByRole('heading', { name: 'Alex Example' })).toBeInTheDocument()
    expect(screen.getByText('MRN MRN-812')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Identity and demographics' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Contact information' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Care and admission' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Additional patient information' })).toBeInTheDocument()
    expect(screen.getByText('alex.synthetic@example.invalid')).toBeInTheDocument()
    expect(screen.getByText('Weekly transportation support')).toBeInTheDocument()
    expect(screen.getByText('patientPreferences.transportationNotes')).toBeInTheDocument()

    const selector = screen.getByRole('combobox', { name: 'Treatment plans for MRN MRN-812' })
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
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
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/patients/MRN-812?source_mode=alleva_rest_api',
      expect.objectContaining({ headers: expect.any(Headers) }),
    ))
  })

  it('directs an unselected user to either roster', () => {
    render(
      <PatientRecordDetailPage
        token='token'
        selection={null}
        onNavigate={vi.fn()}
        onSelectTreatmentPlan={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Select a patient record' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Patient Roster' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Treatment Plans Roster' })).toBeInTheDocument()
  })
})

function patientDetailPayload() {
  return {
    mrn: 'MRN-812',
    full_name: 'Alex Example',
    source_mode: 'alleva_rest_api',
    lifecycle_state: 'active',
    current_level_of_care: 'PHP',
    source_last_updated: '2026-07-10T10:00:00Z',
    first_seen_at: '2026-06-01T10:00:00Z',
    last_seen_at: '2026-07-10T10:00:00Z',
    reconciled_at: '2026-07-10T10:00:00Z',
    treatment_plans: [
      { treatment_plan_id: 'plan-813', last_updated: '2026-07-09T17:45:00Z' },
      { treatment_plan_id: 'plan-812', last_updated: '2026-07-01T08:15:00Z' },
    ],
    patient_record: {
      id: 'source-812',
      mrn: 'MRN-812',
      firstName: 'Alex',
      lastName: 'Example',
      dateOfBirth: '1990-02-03',
      email: 'alex.synthetic@example.invalid',
      levelOfCare: 'PHP',
      diagnoses: [{ code: 'SYNTHETIC', description: 'Synthetic diagnosis for testing' }],
      patientPreferences: { transportationNotes: 'Weekly transportation support' },
    },
  }
}

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}
