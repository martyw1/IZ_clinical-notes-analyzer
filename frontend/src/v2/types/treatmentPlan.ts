export const statusOrder = [
  'Missing Data',
  'Conflicting Evidence',
  'Unable to Evaluate',
  'Needs Review',
  'Overdue',
  'Urgent',
  'Due Soon',
  'Current/Compliant',
  'Incomplete',
  'Within Window',
  'Late',
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

export type ManagerReview = {
  readonly criterionId: string
  readonly action: string
  readonly managerStatus: string
  readonly comment: string
  readonly overrideReason: string
  readonly actorUsername: string
  readonly actorRole: string
  readonly createdAt: string
}

export type SourceDocument = {
  readonly sourceFileId: string
  readonly sourceKind: string
  readonly sourceFormat: string
  readonly contentType: string
  readonly sizeBytes: number
  readonly sha256: string
  readonly redactionStatus: string
  readonly createdAt: string
  readonly downloadUrl: string
}

export type TreatmentPlanAggregate = {
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly treatmentPlanId: string
  readonly currentLevelOfCare: string
  readonly admissionDate: string
  readonly dueDate: string
  readonly sourceDueDate: string
  readonly locChangeDueDate: string
  readonly checklistVersion: string
  readonly rulesVersion: string
  readonly evaluationDate: string
  readonly facilityTimezone: string
  readonly status: TreatmentPlanStatus
  readonly sourceMode: 'manual_upload' | 'alleva_rest_api' | 'synthetic_fixture' | 'unavailable'
  readonly reasonForAdmission: string
  readonly initialClientNeeds: string
  readonly familyEducationNeeds: string
  readonly contentSectionsPresent: readonly string[]
  readonly contentSectionsMissing: readonly string[]
  readonly dataQualityWarnings: readonly string[]
  readonly criteria: readonly CriterionResult[]
  readonly managerReviews: readonly ManagerReview[]
  readonly overrides: readonly ManagerReview[]
  readonly sourceDocuments: readonly SourceDocument[]
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
  readonly evidenceCoverageSummary: {
    readonly criteriaTotal: number
    readonly criteriaWithEvidence: number
    readonly criteriaMissingEvidence: number
    readonly criteriaConflicting: number
    readonly runtimeOnlyFields: readonly string[]
  }
}
