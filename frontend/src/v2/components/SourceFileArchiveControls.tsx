import { useEffect, useState } from 'react'
import { SourceFileArchivePanel } from './SourceFileArchivePanel'
import type { SourceDocument } from '../types/treatmentPlan'

type SourceFileArchiveControlsProps = {
  readonly patientId: string
  readonly sourceDocuments: readonly SourceDocument[]
  readonly onDownloadSourceDocument: (sourceFileId: string) => Promise<void>
  readonly onDeleteSourceDocument: (sourceFileId: string) => Promise<void>
}

function messageForError(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Unable to update the source-file archive.'
}

export function SourceFileArchiveControls({
  patientId,
  sourceDocuments,
  onDownloadSourceDocument,
  onDeleteSourceDocument,
}: SourceFileArchiveControlsProps) {
  const [archiveMessage, setArchiveMessage] = useState('')
  const [downloadingSourceFileId, setDownloadingSourceFileId] = useState('')
  const [deletingSourceFileId, setDeletingSourceFileId] = useState('')

  useEffect(() => {
    setArchiveMessage('')
    setDownloadingSourceFileId('')
    setDeletingSourceFileId('')
  }, [patientId])

  async function downloadSourceDocument(document: SourceDocument) {
    setDownloadingSourceFileId(document.sourceFileId)
    setArchiveMessage('')
    try {
      await onDownloadSourceDocument(document.sourceFileId)
      setArchiveMessage('Source file download started.')
    } catch (error) {
      setArchiveMessage(messageForError(error))
    } finally {
      setDownloadingSourceFileId('')
    }
  }

  async function deleteSourceDocument(document: SourceDocument) {
    const confirmed = window.confirm('Delete archived source file? The treatment-plan aggregate remains, but the original uploaded source bytes will be removed.')
    if (!confirmed) return
    setDeletingSourceFileId(document.sourceFileId)
    setArchiveMessage('')
    try {
      await onDeleteSourceDocument(document.sourceFileId)
      setArchiveMessage('Archived source file deleted.')
    } catch (error) {
      setArchiveMessage(messageForError(error))
    } finally {
      setDeletingSourceFileId('')
    }
  }

  return (
    <SourceFileArchivePanel
      sourceDocuments={sourceDocuments}
      archiveMessage={archiveMessage}
      downloadingSourceFileId={downloadingSourceFileId}
      deletingSourceFileId={deletingSourceFileId}
      onDownloadSourceDocument={(document) => void downloadSourceDocument(document)}
      onDeleteSourceDocument={(document) => void deleteSourceDocument(document)}
    />
  )
}
