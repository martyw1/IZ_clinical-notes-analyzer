import { ClinicianAssignmentForm } from '../components/ClinicianAssignmentForm'
import { ClinicianPullCard } from '../components/ClinicianPullCard'
import { formatUtcEventDateTime } from '../components/treatmentPlanFormatting'
import { useEffect, useState } from 'react'
import { getClinicianDirectory } from '../api/rosterClient'
import { getPatientRoster, getTreatmentPlanRoster } from '../api/client'
import type { PatientRosterItem, TreatmentPlanRosterItem, TreatmentPlanSelection } from '../api/types'
import { DeadlineIndicator } from '../components/DeadlineIndicator'
import { useRequestGeneration, type SessionGuard } from '../hooks/useRequestGeneration'

type Props = {
  canManageAssignments?: boolean
  isAdmin?: boolean
  token: string
  isSessionCurrent: SessionGuard
  onNavigate?: (view: string) => void
  onSelectTreatmentPlan: (selection: TreatmentPlanSelection) => void
}

export function CounselorsPage({ canManageAssignments = false, isAdmin = false, token, isSessionCurrent, onSelectTreatmentPlan, onNavigate }: Props) {
  const [showLinkForm,setShowLinkForm]=useState(false)
  const [patients, setPatients] = useState<readonly PatientRosterItem[]>([])
  const [clinicians, setClinicians] = useState<readonly { id: number; name: string; sourceRole: string; facilityStatus: string }[]>([])
  const [directoryConnected, setDirectoryConnected] = useState(false)
  const [overdueOnly, setOverdueOnly] = useState(false)
  const [plans, setPlans] = useState<readonly TreatmentPlanRosterItem[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [directoryLoaded, setDirectoryLoaded] = useState(false)
  const [lastImport, setLastImport] = useState<Awaited<ReturnType<typeof getClinicianDirectory>>['lastImport']>(null)
  const [caseloadLoading, setCaseloadLoading] = useState(false)
  const [caseloadLoaded, setCaseloadLoaded] = useState(false)
  const [caseloadError, setCaseloadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshNumber, setRefreshNumber] = useState(0)
  const capture = useRequestGeneration(`${token}:${refreshNumber}`, isSessionCurrent)

  const caseloadCapture = useRequestGeneration(`${token}:${refreshNumber}:${selected}`, isSessionCurrent)
  useEffect(() => {
    const current = capture()
    let active = true
    setLoading(true); setError(''); setDirectoryLoaded(false)
    const timeout = window.setTimeout(() => {
      if (active && current()) { setLoading(false); setError('The directory request has not finished. Its contents are unknown. Use Refresh clinicians to retry. No new Alleva pull is started by Refresh.') }
    }, 30000)
    void getClinicianDirectory(token).then((data) => {
      if (!active || !current()) return
      setClinicians(data.items); setDirectoryConnected(data.connected); setLastImport(data.lastImport)
      setDirectoryLoaded(true); setError('')
    }).catch(() => {
      if (active && current()) setError('The clinician directory could not be loaded. This is not an empty pull result. Use Refresh clinicians to retry.')
    }).finally(() => { if (active && current()) { window.clearTimeout(timeout); setLoading(false) } })
    return () => { active = false; window.clearTimeout(timeout) }
  }, [token, capture, refreshNumber])

  useEffect(() => {
    if (selected === null) return
    const current = caseloadCapture()
    let active = true
    setCaseloadLoading(true); setCaseloadLoaded(false); setCaseloadError(''); setPatients([]); setPlans([])
    const timeout = window.setTimeout(() => {
      if (active && current()) { setCaseloadLoading(false); setCaseloadError('This caseload request is still pending. Counts are unavailable; they are not zero.') }
    }, 30000)
    void Promise.all([getPatientRoster(token, undefined, selected), getTreatmentPlanRoster(token, undefined, selected)])
      .then(([roster, saved]) => {
        if (active && current()) { setPatients(roster.items); setPlans(saved.items); setCaseloadLoaded(true); setCaseloadError('') }
      }).catch(() => { if (active && current()) setCaseloadError('Unable to load the selected clinician caseload. Counts are unavailable.') })
      .finally(() => { if (active && current()) { window.clearTimeout(timeout); setCaseloadLoading(false) } })
    return () => { active = false; window.clearTimeout(timeout) }
  }, [token, selected, refreshNumber, caseloadCapture])

  const names = new Map(clinicians.map(({ id, name }) => [id, name]))
  patients.forEach((patient) => {
    if (patient.primaryCounselorId && patient.primaryCounselorName) names.set(patient.primaryCounselorId, patient.primaryCounselorName)
  })
  const roles = new Map(clinicians.map(({ id, sourceRole }) => [id, sourceRole]))
  const facilityStates = new Map(clinicians.map(({ id, facilityStatus }) => [id, facilityStatus]))
  const directory = [...names].filter(([id, name]) => `${name} ${roles.get(id) || ''}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((left, right) => left[1].localeCompare(right[1]))
  const currentPlans = new Map(plans.filter((plan) => plan.deadlineStatus && plan.deadlineStatus !== 'Outside current tracking')
    .map((plan) => [plan.patientRecordId, plan] as const))
  const rows = patients.filter((patient) => patient.trackingEligible && (patient.primaryCounselorId ?? 0) === selected)
    .map((patient) => ({ patient, plan: currentPlans.get(patient.patientRecordId) }))
    .sort((left, right) => (left.plan?.nextDueDate || '9999').localeCompare(right.plan?.nextDueDate || '9999'))

  return <section className='panel table-panel'>
    <h2>Clinicians</h2>
    {canManageAssignments&&<button type='button' aria-expanded={showLinkForm} onClick={()=>setShowLinkForm(!showLinkForm)}>{showLinkForm?'Close clinician linking':'Link clinician to patient'}</button>}
    {canManageAssignments&&showLinkForm&&<ClinicianAssignmentForm token={token} clinicians={clinicians} isSessionCurrent={isSessionCurrent} onCompleted={()=>setRefreshNumber((value)=>value+1)}/>}

    {isAdmin && <ClinicianPullCard token={token} onCompleted={() => { if (isSessionCurrent()) setRefreshNumber((value) => value + 1) }} />}
    <button type='button' onClick={() => setRefreshNumber((value) => value + 1)}>Refresh clinicians</button>

    {loading && <p role='status'>Loading saved clinician directory...</p>}
    {error && <p role='alert'>{error}</p>}
    <label>Search clinicians <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} /></label>
    <p>Imported clinician directory (counselors / therapists). {directoryConnected
      ? 'Staff pulled from Alleva, including incomplete records and staff without a current caseload. Missing facilities are noted; no facility assignment is guessed. The source role is shown without assuming every staff member is a clinician. Primary clinician assignments come from the client record.'
      : directoryLoaded ? 'No mapped staff directory is saved for your facility yet. Pull clinicians imports staff and primary clinician relationships.' : 'Directory status is not yet known.'}</p>
    <p>Refresh reads saved local data. Administrators can fetch from Alleva with Pull clinicians above.</p>
    {lastImport && <section aria-label='Last clinician pull'>
      <p>Last clinician pull: {lastImport.state} at {formatUtcEventDateTime(lastImport.at)}.</p>
      {lastImport.state === 'completed' && <p>{lastImport.returned} staff returned; {lastImport.imported} saved; {lastImport.unmapped} saved with facility not linked; {lastImport.linked} primary assignments linked.</p>}
      {lastImport.state === 'completed' && lastImport.multipleNames > 0 &&
        <p>Patients with multiple clinician names to review: {lastImport.multipleNames}.</p>}
      {lastImport.state === 'failed' && <p>The staff pull failed{lastImport.httpStatus > 0 ? ` (HTTP ${lastImport.httpStatus})` : ''}. Check Forensic Logs for the clinician pull failure.</p>}
      {onNavigate && <button type='button' onClick={() => onNavigate('Forensic Logs')}>Open pull logs</button>}
    </section>}
    {directoryLoaded && !lastImport && <p>No clinician-specific pull log is available here. Older pulls may predate this logging change.</p>}
    <table aria-label='Clinician directory'>
      <thead><tr><th>Clinician</th><th>Source facility</th><th>Alleva staff role</th><th>Active assigned clients</th><th>Overdue plans</th></tr></thead>
      <tbody>{directory.map(([id, name]) => <tr key={id}>
        <td><button type='button' className='link-button' onClick={() => { setSelected(id); setOverdueOnly(false) }}>{name} (#{id})</button></td>
        <td>{facilityStates.get(id) === 'missing' ? 'Missing in source' : facilityStates.get(id) === 'unmapped' ? 'Not linked to a local facility' : facilityStates.get(id) === 'mapped' ? 'Mapped' : 'Not supplied'}</td>
        <td>{roles.get(id) || 'Not supplied'}</td>
        <td>{!caseloadLoaded || selected !== id ? 'Select clinician to load' : patients.filter((patient) => patient.trackingEligible && patient.primaryCounselorId === id).length}</td>
        <td>{!caseloadLoaded || selected !== id ? 'Select clinician to load' : plans.filter((plan) => plan.primaryCounselorId === id && plan.deadlineStatus === 'Overdue').length}</td>
      </tr>)}</tbody>
    </table>
    {directoryLoaded && !names.size && <p>No verified clinician assignments have been imported. Use Pull clinicians to import the Alleva staff directory and explicit primary clinician assignments.</p>}
    {directoryLoaded && names.size > 0 && !directory.length && <p>No clinicians match your search.</p>}
    <button type='button' aria-pressed={selected === 0} onClick={() => { setSelected(0); setOverdueOnly(false) }}>Unassigned</button>
    <p>Unassigned means there is no verified current clinician assignment in the imported evidence.</p>
    {selected !== null && <>
      <h3>{selected === 0 ? 'Unassigned' : names.get(selected)} caseload</h3>
      {caseloadLoading && <p role='status'>Loading this clinician’s caseload...</p>}
      {caseloadError && <p role='alert'>{caseloadError}</p>}
      {caseloadLoaded && <p>{rows.length} active clients · <button type='button' className='link-button' aria-pressed={overdueOnly}
        onClick={() => setOverdueOnly(!overdueOnly)}>
        Currently overdue ({rows.filter(({ plan }) => plan?.deadlineStatus === 'Overdue').length})
      </button></p>}
      <p className='muted'>Historical completion counts require verified completion dates and clinician assignments.</p>
      <table aria-label="Clinician caseload">
        <thead><tr><th>Client</th><th>Current LOC</th><th>Next due date</th><th>Saved plan</th></tr></thead>
        <tbody>{rows.filter(({ plan }) => !overdueOnly || plan?.deadlineStatus === 'Overdue').map(({ patient, plan }) => <tr key={patient.patientRecordId}>
          <td>{patient.fullName || patient.mrn}</td>
          <td>{patient.currentLevelOfCare}</td>
          <td><DeadlineIndicator dueDate={plan?.nextDueDate} status={plan?.deadlineStatus} /></td>
          <td>{plan ? <button type='button' className='link-button' onClick={() => onSelectTreatmentPlan(plan)}>
            {plan.treatmentPlanId}
          </button> : patient.treatmentPlans.length ? 'Current plan unavailable' : 'No plan found'}</td>
        </tr>)}</tbody>
      </table>
    </>}
  </section>
}
