import { useEffect, useState } from 'react'
import { SourceFileArchivePanel } from './SourceFileArchivePanel'
import type { SourceDocument } from '../types/treatmentPlan'
import { planIdentityKey } from '../types/identity'
import type { PlanIdentity } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type SourceFileArchiveControlsProps = {
  readonly identity: PlanIdentity
  readonly isSessionCurrent?: SessionGuard
  readonly sourceDocuments: readonly SourceDocument[]
  readonly onDownloadSourceDocument: (sourceFileId: string) => Promise<void>
  readonly onDeleteSourceDocument: (sourceFileId: string) => Promise<void>
}

function messageForError(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Unable to update the source-file archive.'
}

export function SourceFileArchiveControls({
  identity,
  isSessionCurrent,
  sourceDocuments,
  onDownloadSourceDocument,
}: SourceFileArchiveControlsProps) {
  const [archiveMessage, setArchiveMessage] = useState('')
  const [downloadingSourceFileId, setDownloadingSourceFileId] = useState('')
  const identityKey = planIdentityKey(identity)
  const capture = useRequestGeneration(identityKey, isSessionCurrent)

  useEffect(() => {
    setArchiveMessage('')
    setDownloadingSourceFileId('')
  }, [identityKey])

  async function downloadSourceDocument(document: SourceDocument) {
    if (downloadingSourceFileId) return
    const isCurrent = capture()
    if (!isCurrent()) return
    setDownloadingSourceFileId(document.sourceFileId)
    setArchiveMessage('')
    try {
      await onDownloadSourceDocument(document.sourceFileId)
      if (isCurrent()) setArchiveMessage('Source file download started.')
    } catch (error) {
      if (isCurrent()) setArchiveMessage(messageForError(error))
    } finally {
      if (isCurrent()) setDownloadingSourceFileId('')
    }
  }

  return (
    <SourceFileArchivePanel
      sourceDocuments={sourceDocuments}
      archiveMessage={archiveMessage}
      downloadingSourceFileId={downloadingSourceFileId}
      onDownloadSourceDocument={(document) => void downloadSourceDocument(document)}
    />
  )
}
