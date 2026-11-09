// Display policy only: wire values and stored timestamps remain canonical UTC.
const eastern = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short',
})

export function formatDateTime24Hour(value: string): string {
  if (!value) return 'Unknown'
  // Calendar dates are not instants. Converting midnight UTC would change their day.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  // SQLite/API event timestamps can omit the UTC suffix; do not use browser local time.
  const naiveUtc = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?$/.test(value)
  const normalized = naiveUtc ? `${value.replace(' ', 'T')}Z` : value
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) return value
  const parts = Object.fromEntries(eastern.formatToParts(parsed).map(({ type, value: part }) => [type, part]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} ${parts.timeZoneName}`
}

// Retain the event-contract entry point for existing audit/job/history consumers.
export function formatUtcEventDateTime(value: string): string {
  return formatDateTime24Hour(value)
}
