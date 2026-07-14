import type { TreatmentPlanStatus } from '../types/treatmentPlan'

export type UserRole = 'admin' | 'office_manager' | 'counselor' | 'viewer'
export type AuthState = 'bootstrap_required' | 'password_change_required' | 'active' | 'locked_until'

export type UserProfile = {
  readonly id: number
  readonly username: string
  readonly fullName: string
  readonly role: UserRole
  readonly isActive: boolean
  readonly isLocked: boolean
  readonly mustResetPassword: boolean
  readonly authState: AuthState
  readonly lockedUntil: string
  readonly facilityIds: readonly number[]
}

export type LoginResult = {
  readonly accessToken: string
  readonly mustResetPassword: boolean
  readonly authState: 'password_change_required' | 'active'
}

export type Facility = {
  readonly id: number
  readonly facilityKey: string
  readonly displayName: string
  readonly timezone: string
  readonly isActive: boolean
}

export type NavigationResult = {
  readonly items: readonly string[]
  readonly activeRuntime: string
}

export type SourceCard = {
  readonly label: string
  readonly status: string
  readonly detail: string
}

export type DashboardData = {
  readonly refreshedAt: string
  readonly sourceCards: readonly SourceCard[]
  readonly metrics: Record<string, number>
  readonly blockers: readonly string[]
}

export type TreatmentPlanListItem = {
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly treatmentPlanId: string
  readonly currentLevelOfCare: string
  readonly admissionDate: string
  readonly nextDueDate: string
  readonly status: TreatmentPlanStatus
  readonly missingCriteriaCount: number
  readonly returnedCriteriaCount: number
  readonly sourceMode: string
  readonly warnings: readonly string[]
}

export type TreatmentPlanListData = {
  readonly items: readonly TreatmentPlanListItem[]
  readonly statusOrder: readonly TreatmentPlanStatus[]
}

export type PatientRosterItem = {
  readonly patientId: string
  readonly sourceMode: string
  readonly lifecycleState: string
  readonly currentLevelOfCare: string
  readonly treatmentPlanId: string
  readonly treatmentPlanStatus: string
  readonly firstSeenAt: string
  readonly lastSeenAt: string
  readonly reconciledAt: string
}

export type PatientRosterData = {
  readonly items: readonly PatientRosterItem[]
}

export type ManualTreatmentPlanImportResult = {
  readonly status: 'imported'
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly sourceMode: 'manual_upload'
  readonly criteriaTotal: number
  readonly encryptedAtRest: boolean
  readonly sourceFileArchived: boolean
  readonly sourceFileId: string
  readonly patientIdCorrectionApplied: boolean
}

export type AppSettings = {
  readonly organizationName: string
  readonly facilityTimezone: string
  readonly treatmentPlanMasterDueDays: number
  readonly treatmentPlanPhpReviewIntervalDays: number
  readonly treatmentPlanIopOpReviewIntervalDays: number
  readonly treatmentPlanLocChangeWindowDays: number | null
  readonly treatmentPlanLocChangeWindowValidated: boolean
}

export type ApiConfiguration = {
  readonly vendorName: string
  readonly apiBaseUrl: string
  readonly openapiUrl: string
  readonly tokenUrl: string
  readonly clientId: string
  readonly apiKeyConfigured: boolean
  readonly clientSecretConfigured: boolean
  readonly tokenAuthStyle: string
  readonly scopes: string
  readonly paginationLimit: number
  readonly syncLimit: number
  readonly requestsPerMinute: number
  readonly timeoutSeconds: number
  readonly apiEnabled: boolean
  readonly treatmentPlanSyncEnabled: boolean
  readonly treatmentPlanSyncApproved: boolean
}

export type ApiHarnessPreviewRecord = {
  readonly recordIndex: number
  readonly recordId: string
  readonly sourceEndpoint: string
  readonly redactionStatus: string
}

export type ApiHarnessPreview = {
  readonly records: readonly ApiHarnessPreviewRecord[]
  readonly message: string
}

export type OpenApiDefinitionSummary = {
  readonly title: string
  readonly operationCount: number
}

export type OAuthConnectivityResult = {
  readonly status: 'ok' | 'failure'
  readonly tokenAuthStyle: 'body' | 'basic'
  readonly message: string
  readonly tokenType: string
  readonly expiresIn: number | null
}

export type OperationTestResult = {
  readonly status: 'ok' | 'failure'
  readonly message: string
  readonly statusCode: number | null
  readonly contentType: string
  readonly responseBytes: number
  readonly responseTruncated: boolean
}

export type AuditLogItem = {
  readonly eventId: string
  readonly timestampUtc: string
  readonly actorUsername: string
  readonly actorRole: string
  readonly action: string
  readonly targetEntityType: string
  readonly targetEntityId: string
  readonly outcomeStatus: string
  readonly detailsSummary: string
}

export type AuditVerification = {
  readonly valid: boolean
  readonly eventCount: number
  readonly verifiedEventCount: number
  readonly legacyEventCount: number
  readonly firstInvalidId: number | null
  readonly verificationScope: string
  readonly privacyMode: string
  readonly retentionHook: string
}

export type ApiHarnessArtifact = {
  readonly artifactId: string
  readonly name: string
  readonly mediaType: string
  readonly sizeBytes: number
  readonly redactionMode: string
}

export type ApiHarnessJob = {
  readonly jobId: string
  readonly status: string
  readonly progressPercent: number
  readonly recordsWritten: number
  readonly recordsFailed: number
  readonly warningsCount: number
  readonly artifacts: readonly ApiHarnessArtifact[]
}

export type ManagerActionPayload = {
  readonly criterionId: string
  readonly action: 'approve' | 'return_for_correction' | 'override' | 'comment'
  readonly comment: string
  readonly overrideReason: string
}

export type CorrectionQueueItem = {
  readonly workItemId: number
  readonly planVersionId: number
  readonly patientId: string
  readonly patientDisplayLabel: string
  readonly criterionId: string
  readonly criterionTitle: string
  readonly returnComment: string
  readonly returnedByUsername: string
  readonly returnedAt: string
}

export type CorrectionSubmissionPayload = {
  readonly workItemId: number
  readonly criterionId: string
  readonly comment: string
}
