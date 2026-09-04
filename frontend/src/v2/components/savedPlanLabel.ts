import type { PatientRosterTreatmentPlan } from '../api/types'
import { sourceLabel } from '../types/identity'
import { formatDateTime24Hour } from './treatmentPlanFormatting'

export function savedPlanLabel(plan: PatientRosterTreatmentPlan): string {
  return `${plan.treatmentPlanId} · ${sourceLabel(plan.sourceMode)} · record ${plan.patientRecordId} · version ${plan.versionOrdinal} (#${plan.planVersionId}) · ${formatDateTime24Hour(plan.lastUpdated)}`
}
