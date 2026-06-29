import { contentItemMetadataSummary, contentStatusLabel, safeContentItems } from '../treatmentPlanContentSafety'

type TreatmentPlanContent = {
  id: number
  plan_kind: string
  document_date?: string | null
  source_section?: string | null
  problem_count?: number | null
  diagnosis_count?: number | null
  goal_count?: number | null
  objective_count?: number | null
  intervention_count?: number | null
  has_guardian_signature?: boolean | null
  alleva_is_active?: boolean | null
  alleva_is_complete?: boolean | null
  alleva_is_initial_tp?: boolean | null
  alleva_start_date?: string | null
  alleva_end_date?: string | null
  alleva_last_modified?: string | null
  detail_fetched?: boolean | null
  detail_fetched_at?: string | null
  content_source?: string | null
  content_items?: Array<{
    kind: string
    label: string
    source_path: string
    text_present?: boolean
    metadata?: Record<string, unknown>
  }> | null
  content_capture_status?: string | null
  content_capture_warnings?: string | null
  is_current?: boolean | null
}

type TreatmentPlanContentSummaryProps = {
  plans: TreatmentPlanContent[]
  currentPlanRecordId?: number | null
}

function planKindLabel(kind: string) {
  if (kind === 'initial') return 'Initial'
  if (kind === 'master') return 'Master'
  if (kind === 'review') return 'Review'
  if (kind === 'loc_update') return 'LOC update'
  return kind || 'Plan'
}

function countValue(value: number | null | undefined) {
  return typeof value === 'number' ? value : 0
}

function contentTotal(plan?: TreatmentPlanContent) {
  if (!plan) return 0
  return (
    countValue(plan.problem_count) +
    countValue(plan.diagnosis_count) +
    countValue(plan.goal_count) +
    countValue(plan.objective_count) +
    countValue(plan.intervention_count)
  )
}

export function TreatmentPlanContentSummary({ plans, currentPlanRecordId }: TreatmentPlanContentSummaryProps) {
  const currentPlan = plans.find((plan) => plan.is_current) || plans.find((plan) => currentPlanRecordId != null && plan.id === currentPlanRecordId)
  const detailStatus = currentPlan?.detail_fetched ? 'Detail loaded' : currentPlan ? 'Detail pending' : 'Not selected'
  const detailTone = currentPlan?.detail_fetched ? 'success' : currentPlan ? 'warning' : 'missing-data'
  const contentCounts: Array<[string, number | null | undefined]> = [
    ['Problems', currentPlan?.problem_count],
    ['Diagnoses', currentPlan?.diagnosis_count],
    ['Goals', currentPlan?.goal_count],
    ['Objectives', currentPlan?.objective_count],
    ['Interventions', currentPlan?.intervention_count],
  ]
  const contentItems = safeContentItems(currentPlan?.content_items)

  return (
    <section className='treatment-plan-content-summary' aria-label='Current treatment-plan content summary'>
      <div className='treatment-plan-content-summary__header'>
        <div>
          <h3>Current treatment-plan content</h3>
          <p>{currentPlan ? `${planKindLabel(currentPlan.plan_kind)} plan from ${currentPlan.source_section || currentPlan.content_source || 'Alleva'}` : 'No current plan selected yet.'}</p>
        </div>
        <span className={`pill pill--${detailTone}`}>{detailStatus}</span>
      </div>
      <div className='treatment-plan-content-summary__grid'>
        <div className='treatment-plan-content-summary__primary'>
          <span>Clinical content elements</span>
          <strong>{contentTotal(currentPlan)}</strong>
          <small>{currentPlan?.alleva_is_complete === false ? 'Alleva marks plan incomplete' : currentPlan?.alleva_is_complete ? 'Alleva marks plan complete' : 'Completeness flag not loaded'}</small>
          <small>{contentStatusLabel(currentPlan?.content_capture_status)}</small>
        </div>
        <dl>
          {contentCounts.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{countValue(value)}</dd>
            </div>
          ))}
          <div>
            <dt>Guardian signature</dt>
            <dd>{currentPlan?.has_guardian_signature ? 'Present' : 'Not recorded'}</dd>
          </div>
          <div>
            <dt>Lifecycle</dt>
            <dd>{currentPlan?.alleva_is_active ? 'Active' : currentPlan?.alleva_end_date ? 'Ended' : 'Unknown'}</dd>
          </div>
          <div>
            <dt>Captured facts</dt>
            <dd>{contentItems.length}</dd>
          </div>
        </dl>
      </div>
      {contentItems.length ? (
        <div className='treatment-plan-content-summary__facts'>
          {contentItems.map((item) => (
            <div key={`${item.kind}-${item.source_path}-${item.label}`}>
              <strong>{item.label}</strong>
              <span>{contentItemMetadataSummary(item)}</span>
              <small>{item.source_path}</small>
            </div>
          ))}
        </div>
      ) : null}
      {currentPlan?.content_capture_warnings ? <p className='treatment-plan-content-summary__warning'>{currentPlan.content_capture_warnings}</p> : null}
    </section>
  )
}
