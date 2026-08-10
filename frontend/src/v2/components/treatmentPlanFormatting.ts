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
