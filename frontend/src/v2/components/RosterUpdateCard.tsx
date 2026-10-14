import { useEffect, useState } from 'react'
import { getApiConfiguration } from '../api/settingsClient'
import { getLatestRosterUpdate, runRosterUpdate } from '../api/allevaJobsClient'
import { cancelApiHarnessJob, getApiHarnessJob } from '../api/jobs'
import { approvedImportBlockers } from '../api/apiReadiness'
import { isTerminalJobStatus } from '../api/jobTypes'
import type { ApiConfiguration } from '../api/types'
import { useJobAction } from '../hooks/useJobAction'
import { JobStatusPanel } from './JobStatusPanel'
import { formatUtcEventDateTime } from './treatmentPlanFormatting'

type Props = { readonly token: string; readonly onCompleted: () => void; readonly onNavigate?: (view: string) => void }

export function RosterUpdateCard({ token, onCompleted, onNavigate }: Props) {
  const [config, setConfig] = useState<ApiConfiguration | null>(null)
  const [loadError, setLoadError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const action = useJobAction({
    start: () => runRosterUpdate(token), poll: (id) => getApiHarnessJob(token, id), onCompleted,
    failureMessage: 'Unable to start the update. Check Settings and whether another import is running.',
    successMessage: (job) => job.status === 'completed_with_warnings'
      ? 'Update completed with partial results. Review the stage and warnings before retrying.'
      : 'Patient roster and treatment plans are up to date for this pull.',
  })
  useEffect(() => {
    let stopped = false
    void Promise.all([getApiConfiguration(token), getLatestRosterUpdate(token)]).then(([saved, job]) => {
      if (!stopped) { setConfig(saved); action.setLastJob(job) }
    }).catch(() => { if (!stopped) setLoadError('Unable to load connection or update history. Reopen this page to retry.') })
    return () => { stopped = true }
  }, [token, action.setLastJob])
  const blockers = approvedImportBlockers(config)
  const running = action.job !== null && !isTerminalJobStatus(action.job.status)
  async function cancel() {
    if (!action.job) return
    setCancelling(true)
    try { action.setLastJob(await cancelApiHarnessJob(token, action.job.jobId)) }
    catch { setLoadError('Unable to request cancellation. The update may still be running.') }
    finally { setCancelling(false) }
  }
  return <section className='panel roster-update-card' aria-label='Update patients and treatment plans'>
    <h2>Bring records up to date</h2>
    <p>First update the patient roster, then pull and evaluate treatment plans. You can continue using the app during the update.</p>
    <div className='button-row'>
      <button type='button' disabled={action.isActive || running || blockers.length > 0 || !!loadError} onClick={() => void action.run()}>
        {running ? 'Updating records…' : 'Update patients and treatment plans'}
      </button>
      {running && <button type='button' className='secondary-button' disabled={cancelling || action.job?.cancelRequested} onClick={() => void cancel()}>
        {action.job?.cancelRequested ? 'Cancellation requested' : 'Cancel local update'}
      </button>}
    </div>
    {blockers.length > 0 && <details><summary>Update unavailable</summary><ul>{blockers.map((item) => <li key={item}>{item}</li>)}</ul>
      {onNavigate && <button type='button' className='secondary-button' onClick={() => onNavigate('Settings')}>Open Settings</button>}
    </details>}
    {loadError && <p role='alert'>{loadError}</p>}
    {action.job?.status === 'completed' && action.job.completedAt && <p className='muted'>Last successful two-stage pull: {formatUtcEventDateTime(action.job.completedAt)}.</p>}
    <JobStatusPanel job={action.job} isActive={action.isActive} message={action.message} error={action.error} onRetry={() => void action.run()} />
  </section>
}
