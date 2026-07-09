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

<<<<<<< HEAD
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

=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
export type TreatmentPlanAggregate = {
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly currentLevelOfCare: string
  readonly admissionDate: string
  readonly dueDate: string
  readonly status: TreatmentPlanStatus
<<<<<<< HEAD
  readonly sourceMode: 'manual_upload' | 'alleva_rest_api' | 'synthetic_fixture'
  readonly reasonForAdmission: string
  readonly initialClientNeeds: string
  readonly familyEducationNeeds: string
  readonly contentSectionsPresent: readonly string[]
  readonly contentSectionsMissing: readonly string[]
  readonly criteria: readonly CriterionResult[]
  readonly managerReviews: readonly ManagerReview[]
  readonly overrides: readonly ManagerReview[]
  readonly sourceDocuments: readonly SourceDocument[]
=======
  readonly sourceMode: 'synthetic_fixture'
  readonly contentSectionsPresent: readonly string[]
  readonly contentSectionsMissing: readonly string[]
  readonly criteria: readonly CriterionResult[]
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
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
<<<<<<< HEAD
  readonly evidenceCoverageSummary: {
    readonly criteriaTotal: number
    readonly criteriaWithEvidence: number
    readonly criteriaMissingEvidence: number
    readonly runtimeOnlyFields: readonly string[]
  }
=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
}
