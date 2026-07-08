export const OPERATIONAL_STATUS_CONFIG = [
  {
    status: 'Overdue',
    label: 'Overdue',
    tone: 'overdue',
    helper: 'Past the required treatment-plan update window.',
  },
  {
    status: 'Urgent',
    label: 'Urgent',
    tone: 'urgent',
    helper: 'Needs action before the next required deadline.',
  },
  {
    status: 'Due Soon',
    label: 'Due soon',
    tone: 'due-soon',
    helper: 'Upcoming treatment-plan deadline.',
  },
  {
    status: 'Returned for Correction',
    label: 'Returned',
    tone: 'returned',
    helper: 'Returned to counselor for correction or follow-up.',
  },
  {
    status: 'Needs Review',
    label: 'Needs review',
    tone: 'needs-review',
    helper: 'Requires manager or reviewer attention.',
  },
  {
    status: 'Missing Data',
    label: 'Missing data',
    tone: 'missing-data',
    helper: 'Required evidence is missing.',
  },
  {
    status: 'Conflicting Evidence',
    label: 'Conflicting',
    tone: 'conflicting',
    helper: 'Source dates or evidence disagree.',
  },
  {
    status: 'Unable to Evaluate',
    label: 'Unable',
    tone: 'unable',
    helper: 'The app cannot evaluate with the available evidence.',
  },
  {
    status: 'Compliant',
    label: 'Compliant',
    tone: 'compliant',
    helper: 'No action is currently required.',
  },
] as const

export type OperationalStatus = (typeof OPERATIONAL_STATUS_CONFIG)[number]['status']
export type TimelinessStatusValue = OperationalStatus | 'Approved'
export type OperationalFilter = 'All' | OperationalStatus

export type StatusSummary = {
  readonly status: OperationalStatus
  readonly label: string
  readonly tone: string
  readonly helper: string
  readonly count: number
}

export type OperationalQueueItem = {
  readonly status: TimelinessStatusValue
  readonly next_due_date: string | null
  readonly days_until_due: number | null
}

export type OperationalQueueGroup<TItem extends OperationalQueueItem> = {
  readonly status: OperationalStatus
  readonly label: string
  readonly items: readonly TItem[]
}

export function statusToOperationalStatus(status: TimelinessStatusValue): OperationalStatus {
  return status === 'Approved' ? 'Compliant' : status
}

export function buildStatusSummaries(counts: Partial<Record<OperationalStatus, number>>): StatusSummary[] {
  return OPERATIONAL_STATUS_CONFIG.map((config) => ({
    status: config.status,
    label: config.label,
    tone: config.tone,
    helper: config.helper,
    count: counts[config.status] ?? 0,
  }))
}

export function formatDueDelta(status: TimelinessStatusValue, daysUntilDue: number | null): string {
  if (daysUntilDue == null) return 'Days unavailable'
  if (daysUntilDue === 0) return 'Due today'
  if (daysUntilDue < 0 || statusToOperationalStatus(status) === 'Overdue') return `${Math.abs(daysUntilDue)} days overdue`
  return `${daysUntilDue} days remaining`
}

function dateSortValue(value: string | null): number {
  if (!value) return Number.MAX_SAFE_INTEGER
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time
}

function dueSortValue(item: OperationalQueueItem): number {
  if (item.days_until_due != null) return item.days_until_due
  return dateSortValue(item.next_due_date)
}

function compareQueueItems(left: OperationalQueueItem, right: OperationalQueueItem): number {
  const leftDue = dueSortValue(left)
  const rightDue = dueSortValue(right)
  if (leftDue !== rightDue) return leftDue - rightDue
  return dateSortValue(left.next_due_date) - dateSortValue(right.next_due_date)
}

export function groupOperationalQueueItems<TItem extends OperationalQueueItem>(
  items: readonly TItem[],
): OperationalQueueGroup<TItem>[] {
  return OPERATIONAL_STATUS_CONFIG.map((config) => {
    const groupItems = items.filter((item) => statusToOperationalStatus(item.status) === config.status)
    return {
      status: config.status,
      label: config.label,
      items: [...groupItems].sort(compareQueueItems),
    }
  }).filter((group) => group.items.length > 0)
}
