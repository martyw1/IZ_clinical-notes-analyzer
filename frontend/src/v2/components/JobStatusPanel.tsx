import type { ApiHarnessJob } from '../api/jobTypes'
import { formatUtcEventDateTime } from './treatmentPlanFormatting'

type JobStatusPanelProps = {
  readonly job: ApiHarnessJob | null
  readonly isActive: boolean
  readonly message: string
  readonly error: string
  readonly onRetry?: () => void
}

export function JobStatusPanel({ job, isActive, message, error, onRetry }: JobStatusPanelProps) {
  if (!job && !message && !error) return null
  const determinate = job?.status === 'completed' || job?.status === 'completed_with_warnings' || job?.progressDeterminate === true
  const failure = error || (job?.status === 'failed'
    ? job.message || 'The sync failed. Check Forensic Logs for the cause, then resume the sync safely.'
    : '')
  return (
    <div className={`compact-job-status compact-job-status--${job?.status ?? 'idle'}`} aria-live='polite' aria-atomic='true' aria-busy={isActive}>
      {job && (
        <>
          <div className='compact-job-status__heading'>
            <strong>{job.stageNumber ? `Stage ${job.stageNumber} of 2 · ` : ''}{phaseLabel(job)}</strong>
            <span>{determinate ? `${job.progressPercent}%${isActive ? ' of phase' : ''}` : 'Working…'}</span>
          </div>
          <div className={`job-meter${determinate ? '' : ' job-meter--indeterminate'}`} role='progressbar' aria-label='Job progress' aria-valuemin={0} aria-valuemax={100} aria-valuenow={determinate ? job.progressPercent : undefined}>
            <span style={{ width: determinate ? `${job.progressPercent}%` : '35%' }} />
          </div>
          {!!job.phaseTotal && <p role='status'>{job.phaseCompleted ?? 0} of {job.phaseTotal} processed in this phase.</p>}
          {job.stageNumber === 1 && job.status === 'completed_with_warnings' && <p role='status'>Patient roster results are incomplete. Treatment-plan update was not started. Review warnings and retry.</p>}
          {job.message && !message && !failure && <p>{job.message}</p>}
          <dl className='compact-job-status__counts'>
            <div><dt>Seen</dt><dd>{job.recordsSeen}</dd></div>
            <div><dt>Updated</dt><dd>{job.recordsWritten}</dd></div>
            <div><dt>Warnings</dt><dd>{job.warningsCount}</dd></div>
            <div><dt>Failed records</dt><dd>{job.recordsFailed}</dd></div>
            <div><dt>Errors</dt><dd>{job.errorsCount}</dd></div>
          </dl>
          {job.completedAt && <p className='muted'>Last run completed {formatUtcEventDateTime(job.completedAt)}.</p>}
        </>
      )}
      {message && <p role='status'>{message}</p>}
      {failure && <p role='alert' className='error-banner'>{failure}</p>}
      {error && onRetry && <button type='button' className='secondary-button' onClick={onRetry}>Try again</button>}
    </div>
  )
}

function phaseLabel(job: ApiHarnessJob): string {
  if (job.phase.trim()) return job.phase.split('_').join(' ')
  switch (job.status) {
    case 'queued':
      return 'Queued'
    case 'running':
      return 'Pulling data'
    case 'writing':
      return 'Saving and evaluating'
    case 'completed':
      return 'Completed'
    case 'completed_with_warnings':
      return 'Completed with warnings'
    case 'failed':
      return 'Failed safely'
    case 'cancelled':
      return 'Cancelled'
    case 'stale_or_interrupted':
      return 'Interrupted'
  }
}
