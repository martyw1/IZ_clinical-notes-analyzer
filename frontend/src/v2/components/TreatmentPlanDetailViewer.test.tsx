import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
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
  expect(container.querySelectorAll('details[open]')).toHaveLength(0)
})
