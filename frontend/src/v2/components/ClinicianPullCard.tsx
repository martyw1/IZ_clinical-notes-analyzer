import { useEffect, useState } from 'react'
import { getApiConfiguration } from '../api/settingsClient'
import { approvedImportBlockers } from '../api/apiReadiness'
import { pullClinicians, getClinicianPull, getLatestClinicianPull } from '../api/allevaJobsClient'
import type { ApiConfiguration } from '../api/types'
import { useJobAction } from '../hooks/useJobAction'
import { JobStatusPanel } from './JobStatusPanel'

export function ClinicianPullCard({ token, onCompleted }: { token: string; onCompleted: () => void }) {
  const [config, setConfig] = useState<ApiConfiguration | null>(null)
  const [error, setError] = useState('')
  const action = useJobAction({ start: () => pullClinicians(token), poll: (id) => getClinicianPull(token, id),
    onCompleted, failureMessage: 'Unable to pull clinicians. Check the saved Alleva connection and pull logs.',
    successMessage: (job) => job.message || 'Clinician directory refreshed.' })
  useEffect(() => {
    let active = true
    void getApiConfiguration(token).then((value) => { if (active) setConfig(value) })
      .catch(() => { if (active) setError('Unable to read the saved connection readiness. Reopen this tab to retry.') })
    void getLatestClinicianPull(token).then((job) => { if (active) action.setLastJob(job) }).catch(() => null)
    return () => { active = false }
  }, [token, action.setLastJob])
  const blockers = approvedImportBlockers(config)
  return <section aria-label='Clinician pull' className='panel'>
    <button type='button' onClick={() => void action.run()} disabled={action.isActive || blockers.length > 0 || !!error}>
      {action.isActive ? 'Pulling clinicians...' : 'Pull clinicians'}
    </button>
    <p>Fetch staff names and current primary-clinician links from Alleva. This reads staff and client relationship context; it does not download or evaluate treatment plans.</p>
    {blockers.length > 0 && <p>Uses the saved approved Alleva connection. {blockers.join(' ')}</p>}
    {error && <p role='alert'>{error}</p>}
    <JobStatusPanel job={action.job} isActive={action.isActive} message={action.message} error={action.error} onRetry={() => void action.run()} />
  </section>
}
