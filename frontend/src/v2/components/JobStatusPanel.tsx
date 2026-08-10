import type { ApiHarnessJob } from '../api/jobTypes'
import { formatDateTime24Hour } from './treatmentPlanFormatting'

type JobStatusPanelProps = {
  readonly job: ApiHarnessJob | null
  readonly isActive: boolean
  readonly message: string
  readonly error: string
  readonly onRetry?: () => void
}

export function JobStatusPanel({ job, isActive, message, error, onRetry }: JobStatusPanelProps) {
  if (!job && !message && !error) return null
  return (
    <div className={`compact-job-status compact-job-status--${job?.status ?? 'idle'}`} aria-live='polite' aria-atomic='true' aria-busy={isActive}>
      {job && (
        <>
          <div className='compact-job-status__heading'>
            <strong>{phaseLabel(job)}</strong>
            <span>{job.progressPercent}%</span>
          </div>
          <div className='job-meter' role='progressbar' aria-label='Job progress' aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progressPercent}>
            <span style={{ width: `${job.progressPercent}%` }} />
          </div>
          <dl className='compact-job-status__counts'>
            <div><dt>Seen</dt><dd>{job.recordsSeen}</dd></div>
            <div><dt>Updated</dt><dd>{job.recordsWritten}</dd></div>
            <div><dt>Warnings</dt><dd>{job.warningsCount}</dd></div>
            <div><dt>Failed</dt><dd>{job.recordsFailed}</dd></div>
          </dl>
          {job.completedAt && <p className='muted'>Last run completed {formatDateTime24Hour(job.completedAt)}.</p>}
        </>
      )}
      {message && <p role='status'>{message}</p>}
      {error && <p role='alert' className='error-banner'>{error}</p>}
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
