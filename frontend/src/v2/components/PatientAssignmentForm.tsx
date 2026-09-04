import { useEffect, useState } from 'react'
import { assignPatient, getPatientRoster } from '../api/client'
import type { PatientRosterItem, UserProfile } from '../api/types'
import { patientIdentityKey, sourceLabel } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type Props = {
  readonly token: string
  readonly users: readonly UserProfile[]
  readonly isSessionCurrent?: SessionGuard
}

export function PatientAssignmentForm({ token, users, isSessionCurrent }: Props) {
  const [patients, setPatients] = useState<readonly PatientRosterItem[]>([])
  const [patientKey, setPatientKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const capture = useRequestGeneration(token, isSessionCurrent)
  const selected = patients.find((item) => patientIdentityKey(item) === patientKey)

  useEffect(() => {
    const isCurrent = capture()
    setPatients([])
    setPatientKey('')
    setBusy(false)
    setMessage('')
    void getPatientRoster(token).then((result) => {
      if (isCurrent()) setPatients(result.items)
    }).catch((error: unknown) => {
      if (isCurrent()) setMessage(error instanceof Error ? error.message : 'Unable to load patient assignments.')
    })
  }, [token, capture, isSessionCurrent])

  async function assign(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || busy) return
    const counselor = String(new FormData(event.currentTarget).get('counselorUsername') ?? '')
    if (!counselor) return
    const isCurrent = capture()
    if (!isCurrent()) return
    setBusy(true)
    setMessage('')
    try {
      await assignPatient(token, { ...selected, patientKey: selected.mrn }, counselor)
      if (isCurrent()) setMessage('Patient assigned to counselor.')
    } catch (error) {
      if (isCurrent()) setMessage(error instanceof Error ? error.message : 'Unable to assign this patient record.')
    } finally {
      if (isCurrent()) setBusy(false)
    }
  }

  return <form onSubmit={assign} className='settings-form'>
    <h3>Patient assignment</h3>
    <p className='muted'>Choose the exact patient record. The counselor must already belong to its facility; assigning a patient does not grant facility membership.</p>
    <label>Patient record assignment<select name='patientRecord' value={patientKey} disabled={busy} onChange={(event) => { setPatientKey(event.currentTarget.value); setMessage('') }}>
      <option value=''>Select a patient record</option>
      {patients.map((patient) => <option key={patientIdentityKey(patient)} value={patientIdentityKey(patient)}>{patient.mrn} · {patient.fullName || 'Name unavailable'} · {sourceLabel(patient.sourceMode)} · record {patient.patientRecordId}</option>)}
    </select></label>
    <label>Counselor assignment<select name='counselorUsername' disabled={busy}>{users.filter((user) => user.role === 'counselor').map((user) => <option key={user.id} value={user.username}>{user.username}</option>)}</select></label>
    <div className='button-row settings-actions'><button type='submit' disabled={busy || !selected}>Assign patient</button></div>
    {message && <p role={message === 'Patient assigned to counselor.' ? 'status' : 'alert'}>{message}</p>}
  </form>
}
