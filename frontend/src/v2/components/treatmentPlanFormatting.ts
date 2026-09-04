export function formatDateTime24Hour(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value || 'Unknown'
  const year = parsed.getUTCFullYear()
  const month = twoDigits(parsed.getUTCMonth() + 1)
  const day = twoDigits(parsed.getUTCDate())
  const hour = twoDigits(parsed.getUTCHours())
  const minute = twoDigits(parsed.getUTCMinutes())
  return `${year}-${month}-${day} ${hour}:${minute} UTC`
}

function twoDigits(value: number): string {
  return value.toString().padStart(2, '0')
}

export function formatUtcEventDateTime(value: string): string {
  const naiveUtcEvent = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/.test(value)
  const normalized = naiveUtcEvent ? `${value.replace(' ', 'T')}Z` : value
  if (Number.isNaN(new Date(normalized).getTime())) return value || 'Unknown'
  return formatDateTime24Hour(normalized)
}
