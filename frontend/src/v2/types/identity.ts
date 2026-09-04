export type SourceMode = 'manual_upload' | 'alleva_rest_api' | 'synthetic_fixture'
export type SourceFilter = 'all' | 'manual_upload' | 'alleva_rest_api'
export type PatientRecordId = number & { readonly __patientRecordId: unique symbol }
export type PlanVersionId = number & { readonly __planVersionId: unique symbol }

export type PatientIdentity = {
  readonly patientRecordId: PatientRecordId
  readonly sourceMode: SourceMode
}

export type PlanIdentity = PatientIdentity & {
  readonly planVersionId: PlanVersionId
  readonly treatmentPlanId: string
}

export function sourceLabel(source: SourceMode): string {
  switch (source) {
    case 'manual_upload': return 'Manual'
    case 'alleva_rest_api': return 'Alleva'
    case 'synthetic_fixture': return 'Synthetic fixture'
  }
}

export function planIdentityKey(identity: PlanIdentity): string {
  return `${identity.patientRecordId}:${identity.sourceMode}:${identity.planVersionId}`
}

export function patientIdentityKey(identity: PatientIdentity): string {
  return `${identity.patientRecordId}:${identity.sourceMode}`
}
