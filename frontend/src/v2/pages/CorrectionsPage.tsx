import { useEffect, useState } from 'react'
import { getCorrectionQueue, submitCorrection } from '../api/correctionsClient'
import { ApiRequestError } from '../api/json'
import type { CorrectionQueueItem } from '../api/types'

type CorrectionsPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the correction queue.'
}

function correctionKey(item: CorrectionQueueItem): string {
  return `${item.workItemId}:${item.patientId}:${item.criterionId}`
}

export function CorrectionsPage({ token }: CorrectionsPageProps) {
  const [items, setItems] = useState<readonly CorrectionQueueItem[] | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [savingKey, setSavingKey] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    void getCorrectionQueue(token).then(
      (queue) => { if (!cancelled) setItems(queue) },
      (error: unknown) => { if (!cancelled) setMessage(messageForError(error)) },
    )
    return () => { cancelled = true }
  }, [token])

  async function submit(item: CorrectionQueueItem) {
    const key = correctionKey(item)
    const comment = notes[key]?.trim() ?? ''
    if (!comment) {
      setMessage('Add a resolution note before submitting a correction.')
      return
    }
    setSavingKey(key)
    setMessage('')
    try {
      await submitCorrection(token, item.patientId, { workItemId: item.workItemId, criterionId: item.criterionId, comment })
      setItems((current) => current?.filter((candidate) => correctionKey(candidate) !== key) ?? [])
      setMessage('Correction submitted for manager review.')
    } catch (error) {
      setMessage(messageForError(error))
    } finally {
      setSavingKey('')
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
            return <li key={key}>
              <strong>MRN {item.patientId}</strong> <span>on {item.criterionTitle}</span>
              <span> Returned by {item.returnedByUsername} at {item.returnedAt}</span>
              <p>Manager note: {item.returnComment}</p>
              <label>
                Resolution note
                <textarea value={notes[key] ?? ''} onChange={(event) => setNotes({ ...notes, [key]: event.target.value })} />
              </label>
              <button type='button' onClick={() => void submit(item)} disabled={savingKey === key}>Submit correction</button>
            </li>
          })}
        </ul> : <p className='muted'>No correction returns are assigned to the local counselor queue.</p>}
        {message && <p role={message.startsWith('Correction submitted') ? 'status' : 'alert'}>{message}</p>}
      </div>
    </section>
  )
}
