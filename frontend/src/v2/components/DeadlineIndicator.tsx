import { formatDateTime24Hour } from './treatmentPlanFormatting'
import { StatusBadge } from './StatusBadge'

export function DeadlineIndicator({ dueDate, status }: { dueDate?: string; status?: string }) {
  if (status === 'Patient in Case Management, no next due date') {
    return <span className='deadline-indicator'><StatusBadge status={status} /></span>
  }
  return <span className='deadline-indicator'>
    {dueDate && dueDate !== 'Unknown' ? <time dateTime={dueDate}>{formatDateTime24Hour(dueDate)}</time> : 'Due date unavailable'}
    {status && <> <StatusBadge status={status} /></>}
  </span>
}
