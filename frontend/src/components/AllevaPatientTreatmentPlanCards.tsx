import type { AllevaTreatmentPlan, AllevaTreatmentPlanAggregate } from '../types/allevaTreatmentPlan'

export const REVIEW_DUE_DATE_UNAVAILABLE = 'Treatment review due date unavailable through REST without a known treatmentPlanReviewId'

type DisplayContentItem = {
  readonly kind?: string
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly redacted_text_sha256?: string
}

export function displayAllevaValue(value: string | number | boolean | null | undefined, fallback = 'Missing') {
  if (value === null || value === undefined) return fallback
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  const text = String(value).trim()
  return text || fallback
}

export function AllevaField({ label, value, fallback }: { readonly label: string; readonly value: string | number | boolean | null | undefined; readonly fallback?: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{displayAllevaValue(value, fallback)}</dd>
    </div>
  )
}

function contentItem(item: DisplayContentItem) {
  const hash = item.redacted_text_sha256 ? `redacted_text_sha256 ${item.redacted_text_sha256}` : ''
  return (
    <li key={`${item.kind || 'item'}-${item.source_path}-${item.label}`}>
      <strong>{item.label || item.kind || 'Content item'}</strong>
      <small>
        {item.source_path || 'source path pending'} - {item.text_present ? 'Text captured' : 'Text not present'}
        {hash ? ` - ${hash}` : ''}
      </small>
    </li>
  )
}

function contentList(title: string, items: readonly DisplayContentItem[]) {
  if (!items.length) return null
  return (
    <div>
      <strong>{title}</strong>
      <ul className='compact-list'>{items.map(contentItem)}</ul>
    </div>
  )
}

function planFields(plan: AllevaTreatmentPlan) {
  if (!plan.content_tree.plan_fields.length) return null
  return (
    <div>
      <strong>Plan fields</strong>
      <ul className='compact-list'>
        {plan.content_tree.plan_fields.map((field, index) => {
          const label = displayAllevaValue(
            typeof field.label === 'string' ? field.label : typeof field.kind === 'string' ? field.kind : `plan_field_${index + 1}`,
          )
          const textPresent = Boolean(field.text_present || field.text || field.redacted_text_sha256)
          const sourcePath = typeof field.source_path === 'string' ? field.source_path : 'source path pending'
          return (
            <li key={`${label}-${sourcePath}-${index}`}>
              <strong>{label}</strong>
              <small>
                {sourcePath} - {textPresent ? 'Text captured' : 'Text not present'}
              </small>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function problems(plan: AllevaTreatmentPlan) {
  if (!plan.content_tree.problems.length) return null
  return (
    <div className='finding-list'>
      {plan.content_tree.problems.map((problem) => (
        <article className='finding-card finding-card--compact' key={`${plan.treatment_plan_id}-${problem.source_path}`}>
          <div className='finding-card__header'>
            <div>
              <strong>{problem.label}</strong>
              <p>{problem.source_path || 'source path pending'} - {problem.text_present ? 'Text captured' : 'Text not present'}</p>
            </div>
            <span className='pill pill--neutral'>problem</span>
          </div>
          {contentList('Diagnoses', problem.diagnoses)}
          {contentList('Behavioral definitions', problem.behavioral_definitions)}
          {contentList('Goals', problem.goals)}
          {problem.goals.map((goal) => (
            <div key={`${goal.source_path}-objectives`}>
              {contentList('Objectives', goal.objectives)}
              {goal.objectives.map((objective) => (
                <div key={`${objective.source_path}-interventions`}>{contentList('Interventions', objective.interventions)}</div>
              ))}
            </div>
          ))}
        </article>
      ))}
    </div>
  )
}

function contentTree(plan: AllevaTreatmentPlan) {
  return (
    <section className='panel-subsection' aria-label={`Content tree for treatment plan ${plan.treatment_plan_id}`}>
      <h4>Nested content tree</h4>
      {planFields(plan)}
      {problems(plan)}
      {contentList('Top-level diagnoses', plan.content_tree.top_level_diagnoses)}
      {contentList('Top-level behavioral definitions', plan.content_tree.top_level_behavioral_definitions)}
      {contentList('Top-level goals', plan.content_tree.top_level_goals)}
      {contentList('Top-level objectives', plan.content_tree.top_level_objectives)}
      {contentList('Top-level interventions', plan.content_tree.top_level_interventions)}
    </section>
  )
}

function planCard(plan: AllevaTreatmentPlan, latestCreatedActivePlanId: string) {
  return (
    <article className='finding-card finding-card--compact' key={plan.treatment_plan_id} data-testid={`alleva-treatment-plan-${plan.treatment_plan_id}`}>
      <div className='finding-card__header'>
        <div>
          <strong>treatment_plan_id {plan.treatment_plan_id}</strong>
          <p>
            {plan.treatment_plan_id === latestCreatedActivePlanId ? 'Latest-created active plan' : 'Treatment plan'} - {plan.is_active ? 'active' : 'inactive'}
          </p>
        </div>
        <span className={`pill pill--${plan.join_validated ? 'success' : 'warning'}`}>join_validated {displayAllevaValue(plan.join_validated)}</span>
      </div>
      {!plan.join_validated || !plan.raw_client_ref ? (
        <div className='rule-alert'>
          <strong>Plan join not validated</strong>
          <p>{plan.join_warning || 'raw_client_ref did not validate back to the patient id.'}</p>
        </div>
      ) : null}
      <dl>
        <AllevaField label='raw_client_ref' value={plan.raw_client_ref} />
        <AllevaField label='extracted_patient_id' value={plan.extracted_patient_id} />
        <AllevaField label='plan_client_id' value={plan.plan_client_id} />
        <AllevaField label='start_date' value={plan.start_date} />
        <AllevaField label='end_date' value={plan.end_date} />
        <AllevaField label='created_date' value={plan.created_date} />
        <AllevaField label='last_modified' value={plan.last_modified} />
        <AllevaField label='is_active' value={plan.is_active} />
        <AllevaField label='is_complete' value={plan.is_complete} />
        <AllevaField label='is_initial_tp' value={plan.is_initial_tp} />
        <AllevaField label='is_wiley' value={plan.is_wiley} />
        <AllevaField label='has_reason_for_admission' value={plan.has_reason_for_admission} />
        <AllevaField label='has_initial_client_needs' value={plan.has_initial_client_needs} />
        <AllevaField label='has_family_education_needs' value={plan.has_family_education_needs} />
        <AllevaField label='problem_count' value={plan.problem_count} />
        <AllevaField label='diagnosis_count' value={plan.diagnosis_count} />
        <AllevaField label='behavioral_definition_count' value={plan.behavioral_definition_count} />
        <AllevaField label='goal_count' value={plan.goal_count} />
        <AllevaField label='objective_count' value={plan.objective_count} />
        <AllevaField label='intervention_count' value={plan.intervention_count} />
        <AllevaField label='content_value_status' value={plan.content_value_status} />
      </dl>
      {contentTree(plan)}
    </article>
  )
}

export function AllevaPatientTreatmentPlanAggregateCard({ aggregate }: { readonly aggregate: AllevaTreatmentPlanAggregate }) {
  return (
    <article className='finding-card' data-testid={`alleva-patient-aggregate-${aggregate.patient_id}`}>
      <div className='finding-card__header'>
        <div>
          <strong>patient_id {aggregate.patient_id}</strong>
          <p>
            status_label {displayAllevaValue(aggregate.status_label)} - status_scope {displayAllevaValue(aggregate.status_scope)}
          </p>
        </div>
        <span className={`pill pill--${aggregate.has_multiple_active_plans ? 'warning' : 'success'}`}>
          {aggregate.has_multiple_active_plans ? 'Multiple active treatment plans' : 'Single active treatment-plan set'}
        </span>
      </div>
      <dl>
        <AllevaField label='patient.status_id' value={aggregate.status_id} fallback='[blank]' />
        <AllevaField label='patient.admission_date' value={aggregate.patient.admission_date} />
        <AllevaField label='patient.planned_discharge_date (planned/scheduled)' value={aggregate.patient.planned_discharge_date} />
        <AllevaField label='patient.level_of_care' value={aggregate.patient.level_of_care} />
        <AllevaField label='patient.primary_clinician' value={aggregate.patient.primary_clinician} />
        <AllevaField label='total_plan_count' value={aggregate.total_plan_count} />
        <AllevaField label='active_plan_count' value={aggregate.active_plan_count} />
        <AllevaField label='has_multiple_active_plans' value={aggregate.has_multiple_active_plans} />
        <AllevaField label='treatment_plan_ids' value={aggregate.treatment_plan_ids.join(', ')} />
        <AllevaField label='active_treatment_plan_ids' value={aggregate.active_treatment_plan_ids.join(', ')} />
        <AllevaField label='latest_created_active_plan_id' value={aggregate.latest_created_active_plan_id} />
        <AllevaField label='review_data_status' value={aggregate.review_data_status} />
        <AllevaField label='next_review_due_source' value={aggregate.next_review_due_source} />
        <AllevaField label='review_due_date_status' value={REVIEW_DUE_DATE_UNAVAILABLE} />
        <AllevaField label='review_availability.message' value={aggregate.review_availability.message} />
      </dl>
      <p>{REVIEW_DUE_DATE_UNAVAILABLE}</p>
      <p>{aggregate.review_availability.message}</p>
      <div className='finding-list'>{aggregate.treatment_plans.map((plan) => planCard(plan, aggregate.latest_created_active_plan_id))}</div>
    </article>
  )
}
