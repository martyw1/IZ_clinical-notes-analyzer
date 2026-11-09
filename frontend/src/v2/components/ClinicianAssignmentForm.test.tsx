import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react'
import {afterEach,expect,test,vi} from 'vitest'
import {ClinicianAssignmentForm} from './ClinicianAssignmentForm'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
test('links an exact patient locally, marks unassigned, and restores source with revision checks',async()=>{
  let revision=0
  const fetcher=vi.fn(async(url:string,options?:RequestInit)=>{
    if(url.endsWith('/search'))return new Response(JSON.stringify({items:[{patient_record_id:9,mrn:'SYNTHETIC-MRN',full_name:'Synthetic Patient',source_mode:'manual_upload',clinician_id:null,origin:'unassigned',revision:0}]}))
    const body=JSON.parse(String(options?.body));expect(body.expected_revision).toBe(revision)
    revision++
    return new Response(JSON.stringify({patient_record_id:9,clinician_id:body.clinician_id,clinician_name:body.clinician_id?'Synthetic Clinician':'',origin:body.mode==='local'?'local':'unassigned',revision}))
  })
  vi.stubGlobal('fetch',fetcher)
  const completed=vi.fn()
  render(<ClinicianAssignmentForm token='synthetic' clinicians={[{id:7,name:'Synthetic Clinician'}]} isSessionCurrent={()=>true} onCompleted={completed}/>)
  fireEvent.change(screen.getByLabelText('Patient name or MRN'),{target:{value:'SYNTHETIC-MRN'}})
  fireEvent.click(screen.getByRole('button',{name:'Search patients'}))
  await screen.findByRole('option',{name:/SYNTHETIC-MRN/})
  fireEvent.change(screen.getByLabelText('Patient record to link'),{target:{value:'9'}})
  fireEvent.change(screen.getByLabelText('Clinician to link'),{target:{value:'7'}})
  fireEvent.click(screen.getByRole('button',{name:'Save clinician link'}))
  expect(await screen.findByRole('status')).toHaveTextContent('Local clinician link saved')
  expect(fetcher.mock.calls[1][0]).toBe('/api/v2/patient-records/9/clinician-assignment')
  fireEvent.click(screen.getByRole('button',{name:'Mark unassigned locally'}))
  await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('marked unassigned locally'))
  fireEvent.click(screen.getByRole('button',{name:'Use Alleva assignment'}))
  await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('Alleva assignment restored'))
  expect(completed).toHaveBeenCalledTimes(3)
})

test('a stale assignment reports the conflict instead of claiming a saved link',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.endsWith('/search')?new Response(JSON.stringify({items:[{patient_record_id:1,mrn:'SYNTHETIC',revision:0}]})):new Response(JSON.stringify({detail:'This assignment changed. Refresh before saving.'}),{status:409})))
 render(<ClinicianAssignmentForm token='synthetic' clinicians={[{id:7,name:'Synthetic Clinician'}]} isSessionCurrent={()=>true} onCompleted={vi.fn()}/>)
 fireEvent.click(screen.getByRole('button',{name:'Search patients'}));await screen.findByRole('option',{name:/SYNTHETIC/})
 fireEvent.change(screen.getByLabelText('Patient record to link'),{target:{value:'1'}})
 fireEvent.change(screen.getByLabelText('Clinician to link'),{target:{value:'7'}})
 fireEvent.click(screen.getByRole('button',{name:'Save clinician link'}))
 expect(await screen.findByRole('alert')).toHaveTextContent('Refresh before saving')
 expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
