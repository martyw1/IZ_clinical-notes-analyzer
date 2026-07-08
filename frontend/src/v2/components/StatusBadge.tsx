import type { TreatmentPlanStatus } from '../types/treatmentPlan'

type StatusBadgeProps = {
  readonly status: TreatmentPlanStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const token = status.toLowerCase().replace(/\s+/g, '-')
  return <span className={`status-badge status-badge--${token}`}>{status}</span>
}
