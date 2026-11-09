import { useRef, useState } from 'react'
import { searchAssignmentPatients, saveClinicianAssignment } from '../api/clinicianAssignmentClient'
import type { AssignmentPatient } from '../api/clinicianAssignmentClient'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type Props = {token: string; clinicians: readonly {id:number;name:string}[]; isSessionCurrent: SessionGuard; onCompleted:()=>void}
export function ClinicianAssignmentForm({token,clinicians,isSessionCurrent,onCompleted}:Props) {
  const [query,setQuery]=useState('')
  const [patients,setPatients]=useState<AssignmentPatient[]>([])
  const [patientId,setPatientId]=useState('')
  const [clinicianId,setClinicianId]=useState('')
  const [hasMore,setHasMore]=useState(false)
  const [searched,setSearched]=useState(false)
  const [loading,setLoading]=useState(false)
  const [busy,setBusy]=useState(false)
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const attempts=useRef(0)
  const pending=useRef(false)
  const capture=useRequestGeneration(token,isSessionCurrent)
  const selected=patients.find((row)=>String(row.patientRecordId)===patientId)
  async function search(event: React.FormEvent) {
    event.preventDefault()
    const current=capture(); const attempt=++attempts.current
    setLoading(true);setError('');setMessage('');setPatientId('');setClinicianId('');setPatients([])
    try { const result=await searchAssignmentPatients(token,query)
      if(current()&&attempts.current===attempt){setPatients(result.items);setHasMore(result.hasMore);setSearched(true)}
    } catch(err) {if(current()&&attempts.current===attempt)setError(err instanceof Error?err.message:'Patient search failed.')}
    finally {if(current()&&attempts.current===attempt)setLoading(false)}
  }
  async function save(mode:'local'|'source',id:number|null) {
    if(!selected||pending.current)return
    const current=capture();pending.current=true;setBusy(true);setError('');setMessage('')
    try {const updated=await saveClinicianAssignment(token,selected,mode,id)
      if(current()) {
        setPatients((rows)=>rows.map((row)=>row.patientRecordId===updated.patientRecordId?{...row,...updated}:row))
        setClinicianId(updated.clinicianId===null?'':String(updated.clinicianId))
        setMessage(mode==='source'?'Alleva assignment restored.':id===null?'Patient marked unassigned locally.':'Local clinician link saved. This patient’s treatment plans now use this clinician.')
        onCompleted()
      }
    } catch(err) {if(current())setError(err instanceof Error?err.message:'Unable to save clinician link.')}
    finally {pending.current=false;if(current())setBusy(false)}
  }
  return <section className='panel settings-form' aria-label='Link clinician to patient'>
    <h3>Link clinician to patient</h3>
    <p>This sets the current clinician for the exact patient record and its treatment plans, including the overdue-by-clinician view. It is a local assignment, retained across Alleva pulls. It does not change Alleva or app login permissions.</p>
    <form onSubmit={(event)=>void search(event)}>
      <label>Patient name or MRN<input value={query} onChange={(event)=>setQuery(event.currentTarget.value)} disabled={busy} maxLength={120}/></label>
      <button type='submit' disabled={busy||loading}>{loading?'Searching patients...':'Search patients'}</button>
    </form>
    {searched&&!loading&&!error&&!patients.length&&<p>No patient records match your search.</p>}
    {hasMore&&<p>Showing the first 25 matches. Narrow your search to find the exact patient.</p>}
    <label>Patient record to link<select value={patientId} disabled={busy||loading} onChange={(event)=>{
      const id=event.currentTarget.value;setPatientId(id);setMessage('');setError('')
      const patient=patients.find((row)=>String(row.patientRecordId)===id)
      setClinicianId(patient?.clinicianId?String(patient.clinicianId):'')
    }}><option value=''>Select a patient record</option>{patients.map((patient)=><option key={patient.patientRecordId} value={patient.patientRecordId}>
      {patient.mrn} · {patient.fullName||'Name unavailable'} · {patient.sourceMode} · record {patient.patientRecordId}
    </option>)}</select></label>
    {selected&&<p>Current clinician: {selected.clinicianName||'Unassigned'} · {selected.origin==='local'?'Local assignment':selected.origin==='source'?'Alleva assignment':'No assignment'}</p>}
    {selected?.origin==='local'&&<p>Alleva assignment: {selected.sourceClinicianName||'Not provided'}.</p>}
    <label>Clinician to link<select value={clinicianId} disabled={busy} onChange={(event)=>setClinicianId(event.currentTarget.value)}>
      <option value=''>Select a clinician</option>{clinicians.map((clinician)=><option key={clinician.id} value={clinician.id}>{clinician.name} (#{clinician.id})</option>)}
    </select></label>
    <div className='button-row'>
      <button type='button' disabled={busy||!selected||!clinicianId} onClick={()=>void save('local',Number(clinicianId))}>{busy?'Saving clinician link...':'Save clinician link'}</button>
      <button type='button' className='secondary-button' disabled={busy||!selected} onClick={()=>void save('local',null)}>Mark unassigned locally</button>
      {selected?.origin==='local'&&<button type='button' className='secondary-button' disabled={busy} onClick={()=>void save('source',null)}>Use Alleva assignment</button>}
    </div>
    {message&&<p role='status'>{message}</p>}{error&&<p role='alert'>{error}</p>}
  </section>
}
