import { request } from './request'
import { planSelectionQuery } from './identity'
import type { PlanVersionId, SourceFilter, TreatmentPlanSelection } from './types'
type SelectedDownload = TreatmentPlanSelection & { readonly isCurrent?: () => boolean }

const SOURCE_DOWNLOAD_FALLBACK_FILENAME = 'manual-treatment-plan-source.txt'
const TREATMENT_PLAN_EXPORT_FALLBACK_FILENAME = 'treatment-plans.csv'

export async function downloadTreatmentPlanSourceDocument(token: string, selection: SelectedDownload, sourceFileId: string): Promise<void> {
  if (selection.isCurrent && !selection.isCurrent()) return
  const response = await request(
    `/api/v2/treatment-plans/${encodeURIComponent(selection.patientKey)}/source-documents/${encodeURIComponent(sourceFileId)}/download?${planSelectionQuery(selection)}`,
    { token },
  )
  const blob = await response.blob()
  if (selection.isCurrent && !selection.isCurrent()) return
  const filename = filenameFromDisposition(response.headers.get('content-disposition'))
  triggerBrowserDownload(blob, filename)
}

export async function deleteTreatmentPlanSourceDocument(token: string, selection: TreatmentPlanSelection, sourceFileId: string): Promise<void> {
  await request(
    `/api/v2/treatment-plans/${encodeURIComponent(selection.patientKey)}/source-documents/${encodeURIComponent(sourceFileId)}?${planSelectionQuery(selection)}`,
    { token, method: 'DELETE' },
  )
}

export async function downloadChecklistEvidenceExport(token: string, selection: SelectedDownload): Promise<void> {
  if (selection.isCurrent && !selection.isCurrent()) return
  const response = await request(`/api/v2/exports/${encodeURIComponent(selection.patientKey)}/checklist-evidence.csv?${planSelectionQuery(selection)}`, { token })
  const blob = await response.blob()
  if (selection.isCurrent && !selection.isCurrent()) return
  triggerBrowserDownload(blob, filenameFromDisposition(response.headers.get('content-disposition')))
}

export type TreatmentPlanExportScope = { readonly planVersionIds: readonly PlanVersionId[]; readonly sourceMode?: Exclude<SourceFilter, 'all'>; readonly isCurrent?: () => boolean }

export async function downloadTreatmentPlanListExport(token: string, scope: TreatmentPlanExportScope): Promise<void> {
  if (scope.isCurrent && !scope.isCurrent()) return
  const response = await request('/api/v2/exports/treatment-plans.csv', { token, method: 'POST', body: { plan_version_ids: scope.planVersionIds, ...(scope.sourceMode ? { source_mode: scope.sourceMode } : {}) } })
  const blob = await response.blob()
  if (scope.isCurrent && !scope.isCurrent()) return
  triggerBrowserDownload(
    blob,
    filenameFromDisposition(response.headers.get('content-disposition'), TREATMENT_PLAN_EXPORT_FALLBACK_FILENAME),
  )
}

function filenameFromDisposition(header: string | null, fallbackFilename = SOURCE_DOWNLOAD_FALLBACK_FILENAME): string {
  if (!header) return fallbackFilename
  const filenamePart = header.split(';').map((part) => part.trim()).find((part) => part.toLowerCase().startsWith('filename='))
  if (!filenamePart) return fallbackFilename
  const filename = filenamePart.slice('filename='.length).trim().replace(/^"|"$/g, '')
  return filename || fallbackFilename
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
