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
  readonly clientIdConfigured: boolean
  readonly apiKeyConfigured: boolean
  readonly clientSecretConfigured: boolean
  readonly tokenAuthStyle: string
  readonly scopes: string
  readonly apiVersion: string
  readonly treatmentPlanStartDate: string
  readonly paginationLimit: number
  readonly syncLimit: number
  readonly requestsPerMinute: number
  readonly timeoutSeconds: number
  readonly apiEnabled: boolean
  readonly treatmentPlanSyncEnabled: boolean
  readonly treatmentPlanSyncApproved: boolean
  readonly activeContractVersion: string
  readonly activeContractEffectiveAt: string
}
