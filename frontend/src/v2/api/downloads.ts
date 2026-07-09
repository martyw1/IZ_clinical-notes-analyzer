import { request } from './request'

const SOURCE_DOWNLOAD_FALLBACK_FILENAME = 'manual-treatment-plan-source.txt'

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

function filenameFromDisposition(header: string | null): string {
  if (!header) return SOURCE_DOWNLOAD_FALLBACK_FILENAME
  const filenamePart = header.split(';').map((part) => part.trim()).find((part) => part.toLowerCase().startsWith('filename='))
  if (!filenamePart) return SOURCE_DOWNLOAD_FALLBACK_FILENAME
  const filename = filenamePart.slice('filename='.length).trim().replace(/^"|"$/g, '')
  return filename || SOURCE_DOWNLOAD_FALLBACK_FILENAME
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
