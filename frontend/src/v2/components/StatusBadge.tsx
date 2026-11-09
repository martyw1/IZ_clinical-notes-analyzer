type StatusBadgeProps = {
  readonly status: string
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const token = status.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  return <span className={`status-badge status-badge--${token}`}>{status}</span>
}
