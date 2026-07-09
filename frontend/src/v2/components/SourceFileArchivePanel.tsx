import type { SourceDocument } from '../types/treatmentPlan'

type SourceFileArchivePanelProps = {
  readonly sourceDocuments: readonly SourceDocument[]
  readonly archiveMessage: string
  readonly downloadingSourceFileId: string
  readonly deletingSourceFileId: string
  readonly onDownloadSourceDocument: (document: SourceDocument) => void
  readonly onDeleteSourceDocument: (document: SourceDocument) => void
}

function sourceDocumentKey(document: SourceDocument): string {
  return document.sourceFileId
}

export function SourceFileArchivePanel({
  sourceDocuments,
  archiveMessage,
  downloadingSourceFileId,
  deletingSourceFileId,
  onDownloadSourceDocument,
  onDeleteSourceDocument,
}: SourceFileArchivePanelProps) {
  return (
    <section className='panel source-archive-panel'>
      <div className='section-heading'>
        <div>
          <p className='eyebrow'>Source evidence controls</p>
          <h2>Source File Archive</h2>
        </div>
        <span>{sourceDocuments.length} archived</span>
      </div>
      {sourceDocuments.length ? (
        <ul className='artifact-list source-document-list'>
          {sourceDocuments.map((document) => (
            <li key={sourceDocumentKey(document)}>
              <div className='source-document-metadata'>
                <strong>{document.sourceKind}</strong>
                <span>{document.sourceFormat} | {document.contentType} | {document.sizeBytes} bytes</span>
                <span>{document.redactionStatus}</span>
                <code>{document.sha256}</code>
              </div>
              <div className='source-document-actions'>
                <button
                  type='button'
                  className='secondary-button'
                  aria-label='Download archived source file'
                  onClick={() => onDownloadSourceDocument(document)}
                  disabled={downloadingSourceFileId === document.sourceFileId || deletingSourceFileId === document.sourceFileId}
                >
                  Download source file
                </button>
                <button
                  type='button'
                  className='danger-button'
                  aria-label='Delete archived source file'
                  onClick={() => onDeleteSourceDocument(document)}
                  disabled={deletingSourceFileId === document.sourceFileId}
                >
                  Delete source file
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className='muted'>No archived source files are linked to this treatment-plan record yet.</p>
      )}
      {archiveMessage && <p role='status'>{archiveMessage}</p>}
    </section>
  )
}
