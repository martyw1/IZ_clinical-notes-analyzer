import { useEffect, useMemo, useState } from 'react'
import { getPatientRoster } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { PatientRosterData } from '../api/types'

type PatientRosterPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the patient roster.'
}

export function PatientRosterPage({ token }: PatientRosterPageProps) {
  const [roster, setRoster] = useState<PatientRosterData | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return (roster?.items ?? []).filter((item) => (
      !normalizedQuery
      || item.patientId.toLowerCase().includes(normalizedQuery)
      || item.treatmentPlanId.toLowerCase().includes(normalizedQuery)
      || item.treatmentPlanStatus.toLowerCase().includes(normalizedQuery)
    ))
  }, [query, roster?.items])

  useEffect(() => {
    let cancelled = false
    void getPatientRoster(token).then((result) => {
      if (!cancelled) setRoster(result)
    }).catch((loadError: unknown) => {
      if (!cancelled) setError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [refreshNumber, token])

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (!roster) return <section className='panel muted'>Loading patient roster...</section>

  return (
    <section className='panel table-panel'>
      <div className='section-heading'>
        <div>
          <p className='eyebrow'>Patient Roster</p>
          <h2>Patient roster</h2>
          <p className='muted'>Identifiers and workflow state only. Patient names are excluded.</p>
        </div>
        <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh roster</button>
      </div>
      <label>
        Search patient ID, treatment plan ID, or status
        <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='Patient ID, plan ID, or status' />
      </label>
      <table>
        <thead><tr><th>Patient ID</th><th>Treatment plan ID</th><th>Status</th><th>Lifecycle</th><th>LOC</th><th>Source</th><th>Last seen</th></tr></thead>
        <tbody>
          {visibleItems.map((item) => (
            <tr key={item.patientId}>
              <td data-label='Patient ID'>{item.patientId}</td>
              <td data-label='Treatment plan ID'>{item.treatmentPlanId}</td>
              <td data-label='Status'>{item.treatmentPlanStatus}</td>
              <td data-label='Lifecycle'>{item.lifecycleState}</td>
              <td data-label='LOC'>{item.currentLevelOfCare}</td>
              <td data-label='Source'>{item.sourceMode}</td>
              <td data-label='Last seen'>{item.lastSeenAt}</td>
            </tr>
          ))}
          {visibleItems.length === 0 && <tr><td colSpan={7} className='muted'>No roster entries match the current search.</td></tr>}
        </tbody>
      </table>
    </section>
  )
}
