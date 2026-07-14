import type { ApiConfiguration } from './configurationTypes'

export function approvedImportBlockers(config: ApiConfiguration | null): readonly string[] {
  if (!config) return ['Loading saved API configuration.']
  const blockers: string[] = []
  if (!config.clientIdConfigured) blockers.push('Save the Alleva OAuth client ID in Settings.')
  if (!config.clientSecretConfigured) blockers.push('Save the Alleva client secret in Settings.')
  if (!config.apiEnabled) blockers.push('Enable API testing in Settings.')
  if (!config.treatmentPlanSyncEnabled) blockers.push('Enable treatment-plan sync in Settings.')
  if (!config.treatmentPlanSyncApproved) blockers.push('Authorize live read-only import for this tenant in Settings.')
  return blockers
}
