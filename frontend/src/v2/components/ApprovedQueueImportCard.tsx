import { approvedImportBlockers } from '../api/apiReadiness'
import { getApprovedAllevaTreatmentPlanSyncJob, runApprovedAllevaTreatmentPlanSync } from '../api/allevaJobsClient'
import type { ApiConfiguration, ApiHarnessJob } from '../api/types'
import { useJobAction } from '../hooks/useJobAction'
import { JobStatusPanel } from './JobStatusPanel'

type Props = {
  readonly config: ApiConfiguration | null
  readonly token: string
  readonly onNavigate: (view: string) => void
  readonly onCompleted?: () => void
  readonly showOpenQueueButton?: boolean
  readonly buttonLabel?: string
}

export function ApprovedQueueImportCard({
  config,
  token,
  onNavigate,
  onCompleted,
  showOpenQueueButton = true,
  buttonLabel = 'Pull, evaluate, and populate queue',
}: Props) {
  const blockers = approvedImportBlockers(config)
  const action = useJobAction({
    start: () => runApprovedAllevaTreatmentPlanSync(token),
    poll: (jobId) => getApprovedAllevaTreatmentPlanSyncJob(token, jobId),
    onCompleted,
    failureMessage: 'Unable to pull and evaluate treatment plans. Review Settings and try again.',
    successMessage: queueCompletionMessage,
  })

  return (
    <section className='panel' aria-label='Treatment Plans queue import'>
      <p className='eyebrow'>Operational import</p>
      <h2>Populate and evaluate the Treatment Plans queue</h2>
      {blockers.length > 0 ? (
        <>
          <p className='error-banner'><strong>Queue import is blocked.</strong> Configure the saved Alleva connection before pulling live records.</p>
          <ul>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          <button type='button' className='secondary-button' onClick={() => onNavigate('Settings')}>Open Settings</button>
        </>
      ) : (
        <p>The built-in Alleva v1 mapping is applied automatically when the pull starts. Every returned treatment plan is normalized, evaluated, and added to the queue.</p>
      )}
      <button type='button' onClick={() => void action.run()} disabled={action.isActive || blockers.length > 0}>
        {action.isActive ? 'Pulling full treatment plans...' : buttonLabel}
      </button>
      <JobStatusPanel job={action.job} isActive={action.isActive} message={action.message} error={action.error} onRetry={() => void action.run()} />
      {showOpenQueueButton && (action.job?.status === 'completed' || action.job?.status === 'completed_with_warnings') && (
        <button type='button' className='secondary-button' onClick={() => onNavigate('Treatment Plans')}>Open Treatment Plans queue</button>
      )}
    </section>
  )
}

function queueCompletionMessage(job: ApiHarnessJob): string {
  if (job.recordsWritten === 0) return 'Queue refreshed. No new or changed treatment plans were written.'
  const summary = `Queue populated and deterministic evaluation completed for ${job.recordsWritten} treatment plan${job.recordsWritten === 1 ? '' : 's'}.`
  return job.status === 'completed_with_warnings' ? `${summary} Review ${job.warningsCount} warning${job.warningsCount === 1 ? '' : 's'}.` : summary
}
