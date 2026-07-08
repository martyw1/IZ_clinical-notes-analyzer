import { useState } from 'react'

export type AppDialogState = {
  title: string
  message: string
}

export type ConfirmDialogState = {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  confirmationPhrase?: string
  confirmationLabel?: string
  confirmationPlaceholder?: string
  onConfirm: () => void
}

export type UploadProgressState = {
  phase: 'uploading' | 'processing'
  percent: number
  loadedBytes: number
  totalBytes: number
  fileCount: number
  fileNames: string[]
  message: string
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function summarizeFileNames(fileNames: string[]) {
  if (!fileNames.length) return 'No files selected'
  return `${fileNames.length} selected ${fileNames.length === 1 ? 'file' : 'files'}`
}

type UploadProgressPanelProps = {
  progress: UploadProgressState
}

export function UploadProgressPanel({ progress }: UploadProgressPanelProps) {
  return (
    <div className='full-width upload-progress' role='status' aria-live='polite'>
      <div className='upload-progress__header'>
        <strong>{progress.message}</strong>
        <span>{progress.percent}%</span>
      </div>
      <div className='upload-progress__bar' aria-hidden='true'>
        <span style={{ width: `${progress.percent}%` }} />
      </div>
      <div className='upload-progress__meta'>
        <span>
          {progress.fileCount} {progress.fileCount === 1 ? 'file' : 'files'}
        </span>
        <span>{formatBytes(progress.totalBytes)}</span>
        <span>{summarizeFileNames(progress.fileNames)}</span>
      </div>
    </div>
  )
}

type AppDialogModalProps = {
  dialog: AppDialogState
  onClose: () => void
}

export function AppDialogModal({ dialog, onClose }: AppDialogModalProps) {
  return (
    <div className='modal-backdrop' role='presentation'>
      <section className='app-dialog' role='dialog' aria-modal='true' aria-labelledby='app-dialog-title'>
        <h2 id='app-dialog-title'>{dialog.title}</h2>
        <p>{dialog.message}</p>
        <div className='form-actions'>
          <button type='button' onClick={onClose}>
            OK
          </button>
        </div>
      </section>
    </div>
  )
}

type ConfirmDialogModalProps = {
  dialog: ConfirmDialogState
  onCancel: () => void
}

export function ConfirmDialogModal({ dialog, onCancel }: ConfirmDialogModalProps) {
  const [typedPhrase, setTypedPhrase] = useState('')
  const requiresPhrase = Boolean(dialog.confirmationPhrase)
  const canConfirm = !requiresPhrase || typedPhrase.trim() === dialog.confirmationPhrase

  return (
    <div className='modal-backdrop' role='presentation'>
      <section className='app-dialog' role='alertdialog' aria-modal='true' aria-labelledby='confirm-dialog-title' aria-describedby='confirm-dialog-message'>
        <h2 id='confirm-dialog-title'>{dialog.title}</h2>
        <p id='confirm-dialog-message'>{dialog.message}</p>
        {requiresPhrase ? (
          <label className='form-field confirmation-field'>
            <span>{dialog.confirmationLabel || `Type ${dialog.confirmationPhrase} to continue`}</span>
            <input
              value={typedPhrase}
              onChange={(event) => setTypedPhrase(event.target.value)}
              placeholder={dialog.confirmationPlaceholder || dialog.confirmationPhrase}
              autoFocus
            />
          </label>
        ) : null}
        <div className='form-actions'>
          <button type='button' className='ghost-button' onClick={onCancel}>
            {dialog.cancelLabel}
          </button>
          <button type='button' onClick={dialog.onConfirm} disabled={!canConfirm}>
            {dialog.confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}
