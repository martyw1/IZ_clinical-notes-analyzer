import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { UserProfile } from '../api/types'
import { TreatmentPlanDetailPage } from './TreatmentPlanDetailPage'

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

describe('Treatment Plan Detail selection', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads the exact selected plan and presents its merged clinical content', async () => {
    const fetchMock = vi.fn(async () => response(detailPayload()))
    vi.stubGlobal('fetch', fetchMock)
    render(
      <TreatmentPlanDetailPage
        token='token'
        user={viewer}
        selection={{ mrn: 'MRN-812', treatmentPlanId: 'plan-813', sourceMode: 'alleva_rest_api' }}
        onNavigate={vi.fn()}
      />,
    )

    expect(await screen.findByRole('heading', { name: 'Treatment Plan ID plan-813' })).toBeInTheDocument()
    expect(screen.getByText('MRN MRN-812')).toBeInTheDocument()
    expect(screen.getByText(/Structured clinical rationale from every mapped treatment-plan piece/i)).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/v2/treatment-plans/MRN-812/plan-813?source_mode=alleva_rest_api',
      expect.objectContaining({ headers: expect.any(Headers) }),
    ))
  })

  it('directs an unselected user back to either roster', () => {
    render(<TreatmentPlanDetailPage token='token' user={viewer} selection={null} onNavigate={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Select a treatment plan' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Patient Roster' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open Treatment Plans Roster' })).toBeInTheDocument()
  })

  it('exposes and updates the selected checklist criterion', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(detailPayload())))
    render(
      <TreatmentPlanDetailPage
        token='token'
        user={viewer}
        selection={{ mrn: 'MRN-812', treatmentPlanId: 'plan-813', sourceMode: 'alleva_rest_api' }}
        onNavigate={vi.fn()}
      />,
    )

    const currentLoc = await screen.findByRole('button', { name: /Confirm current LOC/i })
    const admissionDate = screen.getByRole('button', { name: /Confirm admission date/i })
    expect(currentLoc).toHaveAttribute('aria-pressed', 'true')
    expect(admissionDate).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(admissionDate)

    expect(currentLoc).toHaveAttribute('aria-pressed', 'false')
    expect(admissionDate).toHaveAttribute('aria-pressed', 'true')
  })
})

function detailPayload() {
  return {
    patient_id: 'MRN-812',
    patient_display_label: 'MRN MRN-812',
    source_mode: 'alleva_rest_api',
    current_level_of_care: 'PHP',
    admission_date: '2026-06-01',
    date_clock_due_date: '2026-08-15',
    source_due_date: '2026-08-15',
    loc_change_due_date: 'unvalidated_configurable',
    overall_status: 'Needs Review',
    criteria_results: [
      {
        criterion_id: 'confirm_current_loc',
        criterion_title: 'Confirm current LOC',
        result_status: 'Needs Review',
        severity: 'medium',
        finding_message: 'Current LOC needs review.',
        evidence_refs: [],
        source_json_paths: ['client.levelOfCare'],
        manager_action_options: [],
      },
      {
        criterion_id: 'confirm_admission_date',
        criterion_title: 'Confirm admission date',
        result_status: 'Compliant',
        severity: 'info',
        finding_message: 'Admission date is present.',
        evidence_refs: [],
        source_json_paths: ['client.admissionDate'],
        manager_action_options: [],
      },
    ],
    manager_reviews: [],
    overrides: [],
    source_documents: [],
    evidence_coverage_summary: { criteria_total: 42, criteria_with_evidence: 40, criteria_missing_evidence: 2 },
    content_snapshot: {
      plan_id: 'plan-813',
      reason_for_admission: 'Structured clinical rationale from every mapped treatment-plan piece.',
      initial_client_needs: 'Stabilization and relapse prevention.',
      family_education_needs: 'Family education reviewed.',
      problems: [],
      signatures: [],
      observed_fields: [],
    },
  }
}

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}
