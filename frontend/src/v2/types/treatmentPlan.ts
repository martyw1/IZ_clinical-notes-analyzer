export const statusOrder = [
  'Missing Data',
  'Needs Review',
  'Incomplete',
  'Within Window',
  'Late',
  'Conflicting Evidence',
  'Unable to Evaluate',
] as const

export type TreatmentPlanStatus = (typeof statusOrder)[number] | 'Approved' | 'Compliant' | 'Not Applicable'

export type CriterionResult = {
  readonly criterionId: string
  readonly title: string
  readonly status: TreatmentPlanStatus
  readonly severity: 'info' | 'medium' | 'high'
  readonly finding: string
  readonly sourcePath: string
  readonly safePreview: string
  readonly managerActionOptions: readonly string[]
}

export type ContentProblem = {
  readonly problemNumber: string
  readonly description: string
  readonly diagnoses: readonly string[]
  readonly behavioralDefinitions: readonly string[]
  readonly goals: readonly {
    readonly goalNumber: string
    readonly description: string
    readonly objectives: readonly {
      readonly objectiveNumber: string
      readonly description: string
      readonly interventions: readonly string[]
    }[]
  }[]
}

export type TreatmentPlanAggregate = {
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly currentLevelOfCare: string
  readonly admissionDate: string
  readonly dueDate: string
  readonly status: TreatmentPlanStatus
  readonly sourceMode: 'synthetic_fixture'
  readonly contentSectionsPresent: readonly string[]
  readonly contentSectionsMissing: readonly string[]
  readonly criteria: readonly CriterionResult[]
  readonly problems: readonly ContentProblem[]
  readonly signatures: readonly {
    readonly signatureType: string
    readonly signerRoleOrType: string
    readonly signatureDatetime: string
    readonly hasSignatureData: boolean
    readonly signatureDataOmittedReason: string
  }[]
  readonly observedFields: readonly {
    readonly fieldPath: string
    readonly valueType: string
    readonly state: string
    readonly sampleRedactedValue: string
    readonly usedByChecklist: boolean
  }[]
}
