import { useEffect } from 'react'
import { approvedImportBlockers } from '../api/apiReadiness'
import { getActivePatientRosterJob, getLatestActivePatientRosterJob, runActivePatientRosterPull } from '../api/allevaJobsClient'
import type { ApiConfiguration } from '../api/configurationTypes'
import { ApiRequestError } from '../api/json'
import { useJobAction } from '../hooks/useJobAction'
import { JobStatusPanel } from './JobStatusPanel'

type PatientRosterPullCardProps = {
  readonly config: ApiConfiguration | null
  readonly token: string
  readonly onNavigate: (view: string) => void
  readonly onCompleted: () => void
}

export function PatientRosterPullCard({ config, token, onNavigate, onCompleted }: PatientRosterPullCardProps) {
  const blockers = approvedImportBlockers(config)
  const action = useJobAction({
    start: () => runActivePatientRosterPull(token),
    poll: (jobId) => getActivePatientRosterJob(token, jobId),
    onCompleted,
    failureMessage: 'Unable to pull the active patient roster. Review Settings and try again.',
  })

  useEffect(() => {
    let active = true
    void getLatestActivePatientRosterJob(token).then((job) => {
      if (active) action.setLastJob(job)
    }).catch((error: unknown) => {
      if (!(error instanceof ApiRequestError && error.status === 404)) throw error
    })
    return () => { active = false }
  }, [action.setLastJob, token])

  return (
    <section className='panel' aria-label='Active patient roster pull'>
      <p className='eyebrow'>Patient data</p>
      <h2>Refresh the patient roster</h2>
      <p>Pulls every available client into the MRN-first roster with authorized full-name display. Treatment plans are not required for a patient to appear.</p>
      {blockers.length > 0 && (
        <div className='preflight-blockers'>
          <p><strong>Roster pull is blocked.</strong></p>
          <ul>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          <button type='button' className='secondary-button' onClick={() => onNavigate('Settings')}>Open Settings</button>
        </div>
      )}
      <button type='button' onClick={() => void action.run()} disabled={action.isActive || blockers.length > 0}>
        {action.isActive ? 'Pulling patient roster...' : 'Pull patient roster'}
      </button>
      <JobStatusPanel job={action.job} isActive={action.isActive} message={action.message} error={action.error} onRetry={() => void action.run()} />
    </section>
  )
}
