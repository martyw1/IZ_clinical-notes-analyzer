import type { CriterionResult, TreatmentPlanAggregate } from './types/treatmentPlan'

const criterionTitles = [
  'Confirm this is the correct client chart',
  'Identify whether this is a new chart or update',
  'Confirm the client is active',
  'Confirm the admission date',
  'Confirm the current LOC',
  'Confirm treatment plan exists',
]

function criterion(index: number): CriterionResult {
  const title = criterionTitles[index - 1] ?? `Treatment-plan checklist criterion ${index}`
  const status = index === 8 || index === 19 || index === 27 ? 'Missing Data' : index === 12 ? 'Needs Review' : 'Compliant'
  return {
    criterionId: `criterion_${String(index).padStart(2, '0')}`,
    title,
    status,
    severity: status === 'Compliant' ? 'info' : 'medium',
    finding: `${title}: evaluated from nested V2 treatment-plan content.`,
    sourcePath: 'problems[0].goals[0].objectives[0].interventions[0].description',
    safePreview: status === 'Missing Data' ? 'Required source field unavailable.' : 'Nested content supports this criterion.',
    managerActionOptions: ['approve criterion', 'return criterion for correction', 'override with reason'],
  }
}

export const syntheticTreatmentPlan: TreatmentPlanAggregate = {
  patientId: '307',
  patientDisplayLabel: 'Patient ID 307',
  currentLevelOfCare: 'IOP',
  admissionDate: '2026-05-15',
  dueDate: '2026-08-30',
  status: 'Needs Review',
  sourceMode: 'synthetic_fixture',
  contentSectionsPresent: [
    'Reason for admission',
    'Initial client needs',
    'Family education needs',
    'Diagnoses',
    'Behavioral definitions',
    'Goals',
    'Objectives',
    'Interventions',
    'Signatures metadata',
  ],
  contentSectionsMissing: ['Trusted nextReviewDue from REST'],
  criteria: Array.from({ length: 42 }, (_, index) => criterion(index + 1)),
  problems: [
    {
      problemNumber: '1',
      description: 'Substance-use recovery stabilization needs continued clinical support.',
      diagnoses: ['F10.20 Synthetic active diagnosis, primary'],
      behavioralDefinitions: ['Synthetic behavioral definition for treatment planning.'],
      goals: [
        {
          goalNumber: '1',
          description: 'Improve recovery stability through measurable coping strategies.',
          objectives: [
            {
              objectiveNumber: '1',
              description: 'Identify three coping skills and practice them between sessions.',
              interventions: ['Weekly CBT-based skills practice with progress review.'],
            },
          ],
        },
      ],
    },
  ],
  signatures: [
    {
      signatureType: 'staff',
      signerRoleOrType: 'clinician',
      signatureDatetime: '2026-07-01T15:30:00-04:00',
      hasSignatureData: true,
      signatureDataOmittedReason: 'Signature image/base64 never renders in the default browser payload.',
    },
  ],
  observedFields: [
    {
      fieldPath: 'reason_for_admission',
      valueType: 'string',
      state: 'present',
      sampleRedactedValue: 'Clinical rationale present.',
      usedByChecklist: true,
    },
    {
      fieldPath: 'signatures.staff.signatureData',
      valueType: 'string',
      state: 'redacted',
      sampleRedactedValue: '[signature image omitted]',
      usedByChecklist: false,
    },
  ],
}

export const dashboardMetrics = [
  ['Active patient IDs', '1'],
  ['Missing data', '3'],
  ['Needs review', '1'],
  ['Incomplete', '0'],
  ['Within window', '0'],
  ['Late', '0'],
  ['Conflicting', '0'],
  ['Unable', '0'],
] as const
