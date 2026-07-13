import { request } from './request'

const SOURCE_DOWNLOAD_FALLBACK_FILENAME = 'manual-treatment-plan-source.txt'
const TREATMENT_PLAN_EXPORT_FALLBACK_FILENAME = 'treatment-plans.csv'

export async function downloadTreatmentPlanSourceDocument(token: string, patientId: string, sourceFileId: string): Promise<void> {
  const response = await request(
    `/api/v2/treatment-plans/${encodeURIComponent(patientId)}/source-documents/${encodeURIComponent(sourceFileId)}/download`,
    { token },
  )
  const blob = await response.blob()
  const filename = filenameFromDisposition(response.headers.get('content-disposition'))
  triggerBrowserDownload(blob, filename)
}

export async function deleteTreatmentPlanSourceDocument(token: string, patientId: string, sourceFileId: string): Promise<void> {
  await request(
    `/api/v2/treatment-plans/${encodeURIComponent(patientId)}/source-documents/${encodeURIComponent(sourceFileId)}`,
    { token, method: 'DELETE' },
  )
}

export async function downloadChecklistEvidenceExport(token: string, patientId: string): Promise<void> {
  const response = await request(`/api/v2/exports/${encodeURIComponent(patientId)}/checklist-evidence.csv`, { token })
  triggerBrowserDownload(await response.blob(), filenameFromDisposition(response.headers.get('content-disposition')))
}

export async function downloadTreatmentPlanListExport(token: string): Promise<void> {
  const response = await request('/api/v2/exports/treatment-plans.csv', { token })
  triggerBrowserDownload(
    await response.blob(),
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
