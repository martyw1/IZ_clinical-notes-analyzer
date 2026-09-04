import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { ManagerActionPayload } from '../api/types'
import { mapTreatmentPlanAggregate } from '../api/treatmentPlanMapper'
import { TreatmentPlanDetailViewer } from './TreatmentPlanDetailViewer'

test('renders one readable selected-plan document with timeline, full clinical hierarchy, and review history', () => {
  const plan = mapTreatmentPlanAggregate({
    patient_id: 'MRN-SYNTHETIC-1',
    patient_display_label: 'MRN MRN-SYNTHETIC-1',
    source_mode: 'alleva_rest_api',
    source_last_updated: '2026-02-04T17:30:00Z',
    current_level_of_care: 'PHP',
    admission_date: '2026-01-01T08:00:00Z',
    date_clock_due_date: '2026-02-15T08:00:00Z',
    source_due_date: '2026-02-14T08:00:00Z',
    overall_status: 'Needs Review',
    treatment_plans: [
      { plan_id: 'plan-complete', plan_date: '2026-01-03T09:00:00Z', last_modified: '2026-02-04T17:30:00Z' },
    ],
    treatment_reviews: [
      { id: 'review-1', createdDated: '2026-02-01T09:00:00Z', creatorSignatureDate: '2026-02-02T10:00:00Z' },
    ],
    content_snapshot: {
      plan_id: 'plan-complete',
      reason_for_admission: 'Synthetic reason.',
      initial_client_needs: 'Synthetic needs.',
      family_education_needs: 'Synthetic family education.',
      problems: [
        {
          problem_number: '1',
          problem_description: 'Synthetic problem one.',
          diagnoses: [
            { icd10_code: 'F10.20', diagnosis_description: 'Synthetic diagnosis one.' },
            { icd10_code: 'F41.1', diagnosis_description: 'Synthetic diagnosis two.' },
          ],
          behavioral_definitions: [{ behavioral_definition: 'Synthetic behavior one.' }],
          goals: [{
            goal_number: '1',
            goal_description: 'Synthetic goal one.',
            objectives: [{
              objective_number: '1',
              objective_description: 'Synthetic objective one.',
              interventions: [
                { intervention_description: 'Synthetic intervention one.' },
                { intervention_description: 'Synthetic intervention two.' },
              ],
            }],
          }],
        },
        {
          problem_number: '2',
          problem_description: 'Synthetic problem two.',
          diagnoses: [],
          behavioral_definitions: [],
          goals: [],
        },
      ],
      signatures: [{
        signature_type: 'clientSignature',
        signer_role_or_type: 'client',
        signature_datetime: '2026-02-03T10:00:00Z',
        has_signature_data: true,
        signature_data_omitted_reason: 'signature binary omitted',
      }],
      observed_fields: [],
    },
    criteria_results: [],
    manager_reviews: [],
    overrides: [],
    source_documents: [],
    evidence_coverage_summary: {},
  })

  const { container } = render(
    <TreatmentPlanDetailViewer
      plan={plan}
      canManage={false}
      onManagerAction={async () => undefined}
      onExportChecklistEvidence={async () => undefined}
      onDownloadSourceDocument={async () => undefined}
      onDeleteSourceDocument={async () => undefined}
    />,
  )

  expect(screen.getByRole('heading', { name: 'Treatment Plan ID plan-complete' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Plan timeline' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Clinical overview' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Clinical review history' })).toBeInTheDocument()
  expect(screen.getByText('Synthetic diagnosis one.')).toBeInTheDocument()
  expect(screen.getByText('Synthetic diagnosis two.')).toBeInTheDocument()
  expect(screen.getByText('Synthetic intervention two.')).toBeInTheDocument()
  const rawFieldSummary = screen.getByText('Raw Field Explorer').closest('summary')
  expect(rawFieldSummary).toHaveClass('raw-field-summary')
  expect(rawFieldSummary?.querySelector('.raw-field-summary__count')).toHaveTextContent('0 source paths')
  expect(container.querySelectorAll('details[open]')).toHaveLength(0)
})

test('searches title, finding, redacted preview, and source path without searching clinical source text', () => {
  const plan = presentationPlan({
    reason_for_admission: 'SECRET-CLINICAL-SOURCE-TEXT',
    criteria_results: [{
      criterion_id: 'criterion-safe-evidence',
      criterion_title: 'Current level of care',
      result_status: 'Needs Review',
      severity: 'medium',
      finding_message: 'Review required for this criterion.',
      evidence_refs: [{ safe_preview: 'Already-redacted evidence preview.' }],
      source_json_paths: ['Clinical.Source.LevelOfCare'],
      manager_action_options: [],
    }],
  })
  renderViewer(plan)

  const search = screen.getByRole('textbox', { name: 'Search checklist evidence' })
  for (const query of ['CURRENT LEVEL', 'REVIEW REQUIRED', 'ALREADY-REDACTED', 'clinical.source']) {
    fireEvent.change(search, { target: { value: query } })
    expect(screen.getByRole('button', { name: /Current level of care/i })).toBeInTheDocument()
  }

  fireEvent.change(search, { target: { value: 'secret-clinical-source-text' } })
  expect(screen.getByText('No checklist evidence matches “secret-clinical-source-text”.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Current level of care/i })).not.toBeInTheDocument()
})

test('clears actionable selection on zero matches and restores it when search is cleared', () => {
  const onManagerAction = vi.fn(async () => undefined)
  renderViewer(presentationPlan({
    criteria_results: [
      criterion('criterion-one', 'First criterion'),
      criterion('criterion-two', 'Second criterion'),
    ],
  }), true, onManagerAction)

  const search = screen.getByRole('textbox', { name: 'Search checklist evidence' })
  const actionNames = ['Approve criterion', 'Save comment', 'Return for correction', 'Save override']
  fireEvent.change(search, { target: { value: 'zz-no-such-safe-evidence' } })

  expect(screen.getByText('No checklist evidence matches “zz-no-such-safe-evidence”.')).toBeInTheDocument()
  for (const actionName of actionNames) {
    const action = screen.getByRole('button', { name: actionName })
    expect(action).toBeDisabled()
    fireEvent.click(action)
  }
  expect(onManagerAction).not.toHaveBeenCalled()

  fireEvent.change(search, { target: { value: '' } })
  expect(screen.getByRole('button', { name: /First criterion/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Approve criterion' })).not.toBeDisabled()
})

test('keeps manager feedback when a saved plan refreshes with a fresh criteria array', async () => {
  const onManagerAction = vi.fn(async () => undefined)
  const initialPlan = presentationPlan({ criteria_results: [criterion('criterion-one', 'First criterion')] })
  const props = {
    canManage: true,
    onManagerAction,
    onExportChecklistEvidence: async () => undefined,
    onDownloadSourceDocument: async () => undefined,
    onDeleteSourceDocument: async () => undefined,
  }
  const view = render(<TreatmentPlanDetailViewer plan={initialPlan} {...props} />)

  fireEvent.click(screen.getByRole('button', { name: 'Approve criterion' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Approval saved as a manager disposition.'))

  const refreshedPlan = presentationPlan({ criteria_results: [criterion('criterion-one', 'First criterion')] })
  view.rerender(<TreatmentPlanDetailViewer plan={refreshedPlan} {...props} />)
  expect(screen.getByRole('status')).toHaveTextContent('Approval saved as a manager disposition.')
})

test('separates signature metadata and renders absent overview values as Not supplied', () => {
  renderViewer(presentationPlan({
    content_snapshot: {
      plan_id: 'plan-presentation',
      reason_for_admission: '',
      initial_client_needs: 'Unknown',
      family_education_needs: 'No family-education text returned.',
      problems: [],
      signatures: [{
        signature_type: 'staff',
        signer_role_or_type: 'counselor',
        signature_datetime: '2026-08-01T12:34:00Z',
        has_signature_data: false,
        signature_data_omitted_reason: 'Signature bytes are not returned in the browser payload.',
      }],
      observed_fields: [],
    },
  }))

  expect(screen.getByText('Signature type').tagName).toBe('DT')
  expect(screen.getByText('Signer role or type').tagName).toBe('DT')
  expect(screen.getByText('Signature date').tagName).toBe('DT')
  expect(screen.getByText('Explanation').tagName).toBe('DT')
  expect(screen.getByText('2026-08-01 12:34 UTC')).toBeInTheDocument()
  expect(screen.getByText('Signature bytes are not returned in the browser payload.')).toBeInTheDocument()
  expect(screen.getAllByText('Not supplied')).toHaveLength(3)
})

test('explains coverage overlap and keeps Unable/Not Applicable statuses distinct', () => {
  renderViewer(presentationPlan({
    criteria_results: [
      criterion('criterion-unknown', 'Unknown result', 'Unable to Evaluate'),
      criterion('criterion-na', 'Not applicable result', 'Not Applicable'),
    ],
    evidence_coverage_summary: {
      criteria_total: 42,
      criteria_with_evidence: 1,
      criteria_missing_evidence: 1,
      criteria_conflicting: 0,
      runtime_only_fields: ['source.createdAt'],
    },
  }))

  expect(screen.getByText(/do not partition the 42 criteria/i)).toBeInTheDocument()
  expect(screen.getByText('Result status: Unable to Evaluate')).toBeInTheDocument()
  expect(screen.getByText('Result status: Not Applicable')).toBeInTheDocument()
  expect(screen.getByText('Source support: observed evidence')).toBeInTheDocument()
  expect(screen.getByText('Source support: missing evidence')).toBeInTheDocument()
})

function renderViewer(
  plan: ReturnType<typeof mapTreatmentPlanAggregate>,
  canManage = false,
  onManagerAction: (payload: ManagerActionPayload) => Promise<void> = async () => undefined,
) {
  return render(
    <TreatmentPlanDetailViewer
      plan={plan}
      canManage={canManage}
      onManagerAction={onManagerAction}
      onExportChecklistEvidence={async () => undefined}
      onDownloadSourceDocument={async () => undefined}
      onDeleteSourceDocument={async () => undefined}
    />,
  )
}

function criterion(criterionId: string, title: string, status = 'Needs Review') {
  return {
    criterion_id: criterionId,
    criterion_title: title,
    result_status: status,
    severity: 'medium',
    finding_message: `${title} finding`,
    evidence_refs: [],
    source_json_paths: [],
    manager_action_options: [],
  }
}

function presentationPlan(overrides: Record<string, unknown> = {}) {
  return mapTreatmentPlanAggregate({
    patient_id: 'MRN-PRESENTATION',
    patient_display_label: 'MRN MRN-PRESENTATION',
    source_mode: 'synthetic_fixture',
    current_level_of_care: 'PHP',
    admission_date: 'Unknown',
    overall_status: 'Needs Review',
    treatment_plans: [],
    treatment_reviews: [],
    manager_reviews: [],
    overrides: [],
    source_documents: [],
    criteria_results: [],
    evidence_coverage_summary: {},
    content_snapshot: {
      plan_id: 'plan-presentation',
      reason_for_admission: '',
      initial_client_needs: '',
      family_education_needs: '',
      problems: [],
      signatures: [],
      observed_fields: [],
    },
    ...overrides,
  })
}
