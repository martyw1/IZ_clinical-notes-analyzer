import { useEffect, useState } from 'react'
import { getCorrectionQueue, submitCorrection } from '../api/correctionsClient'
import { ApiRequestError } from '../api/json'
import type { CorrectionQueueItem } from '../api/types'
import { planIdentityKey, sourceLabel } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type CorrectionsPageProps = {
  readonly token: string
  readonly isSessionCurrent?: SessionGuard
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the correction queue.'
}

function correctionKey(item: CorrectionQueueItem): string {
  return `${item.workItemId}:${planIdentityKey(item)}:${item.criterionId}`
}

export function CorrectionsPage({ token, isSessionCurrent }: CorrectionsPageProps) {
  const [items, setItems] = useState<readonly CorrectionQueueItem[] | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState('')
  const [message, setMessage] = useState('')
  const capture = useRequestGeneration(token, isSessionCurrent)

  useEffect(() => {
    const isCurrent = capture()
    setItems(null)
    setNotes({})
    setSavingKey('')
    setMessage('')
    void getCorrectionQueue(token).then(
      (queue) => { if (isCurrent()) setItems(queue) },
      (error: unknown) => { if (isCurrent()) setMessage(messageForError(error)) },
    )
  }, [token, capture, isSessionCurrent])

  async function submit(item: CorrectionQueueItem) {
    if (savingKey) return
    const isCurrent = capture()
    if (!isCurrent()) return
    const key = correctionKey(item)
    const comment = notes[key]?.trim() ?? ''
    if (!comment) {
      setMessage('Add a resolution note before submitting a correction.')
      return
    }
    setSavingKey(key)
    setMessage('')
    try {
      await submitCorrection(token, item.patientId, { ...item, comment })
      if (!isCurrent()) return
      setItems((current) => current?.filter((candidate) => correctionKey(candidate) !== key) ?? [])
      setMessage('Correction submitted for manager review.')
    } catch (error) {
      if (isCurrent()) setMessage(messageForError(error))
    } finally {
      if (isCurrent()) setSavingKey('')
    }
  }

  if (items === null && !message) return <section className='panel muted'>Loading correction queue...</section>
  if (items === null) return <section className='panel error-banner' role='alert'>{message}</section>

  return (
    <section className='page-grid'>
      <div className='panel'>
        <p className='eyebrow'>Counselor workflow</p>
        <h2>Corrections</h2>
        <p className='muted'>Returns stay open until a counselor submits a resolution note for manager review.</p>
      </div>
      <div className='panel'>
        <h2>Open Returns</h2>
        {items.length ? <ul className='artifact-list'>
          {items.map((item) => {
            const key = correctionKey(item)
            return <li key={key} data-plan-version-id={item.planVersionId} data-patient-record-id={item.patientRecordId} data-source-mode={item.sourceMode}>
              <strong>MRN {item.patientId}</strong> <span>on {item.criterionTitle}</span>
              <p>{sourceLabel(item.sourceMode)} · record {item.patientRecordId} · saved version #{item.planVersionId} · plan {item.treatmentPlanId}</p>
              <span> Returned by {item.returnedByUsername} at {item.returnedAt}</span>
              <p>Manager note: {item.returnComment}</p>
              <label>
                Resolution note
                <textarea value={notes[key] ?? ''} onChange={(event) => setNotes({ ...notes, [key]: event.target.value })} />
              </label>
              <button type='button' onClick={() => void submit(item)} disabled={Boolean(savingKey)}>Submit correction</button>
            </li>
          })}
        </ul> : <p className='muted'>No correction returns are assigned to the local counselor queue.</p>}
        {message && <p role={message.startsWith('Correction submitted') ? 'status' : 'alert'}>{message}</p>}
      </div>
    </section>
  )
}
