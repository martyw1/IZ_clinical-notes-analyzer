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
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
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
          <strong>Treatment Plan ID (Alleva TPId): {plan.treatment_plan_id}</strong>
          <p>
            {plan.treatment_plan_id === latestCreatedActivePlanId ? 'Latest-created active plan' : 'Treatment plan'} - {plan.is_active ? 'active' : 'inactive'}
          </p>
        </div>
        <span className={`pill pill--${plan.join_validated ? 'success' : 'warning'}`}>Patient join {plan.join_validated ? 'validated' : 'needs review'}</span>
      </div>
      {!plan.join_validated || !plan.raw_client_ref ? (
        <div className='rule-alert'>
          <strong>Plan join not validated</strong>
          <p>{plan.join_warning || 'Plan client reference did not validate back to the Patient ID.'}</p>
        </div>
      ) : null}
      <dl>
        <AllevaField label='Plan client reference (/clients/{id})' value={plan.raw_client_ref} />
        <AllevaField label='Extracted Patient ID' value={plan.extracted_patient_id} />
        <AllevaField label='Patient ID used for ClientId' value={plan.plan_client_id} />
        <AllevaField label='Plan start date' value={plan.start_date} />
        <AllevaField label='Plan end date' value={plan.end_date} />
        <AllevaField label='Plan created date' value={plan.created_date} />
        <AllevaField label='Last modified in Alleva' value={plan.last_modified} />
        <AllevaField label='Active plan (isActive)' value={plan.is_active} />
        <AllevaField label='Complete/submitted in Alleva (isComplete)' value={plan.is_complete} />
        <AllevaField label='Initial treatment plan (isInitialTP)' value={plan.is_initial_tp} />
        <AllevaField label='Wiley template plan' value={plan.is_wiley} />
        <AllevaField label='Reason for admission captured' value={plan.has_reason_for_admission} />
        <AllevaField label='Initial client needs captured' value={plan.has_initial_client_needs} />
        <AllevaField label='Family education needs captured' value={plan.has_family_education_needs} />
        <AllevaField label='Problems' value={plan.problem_count} />
        <AllevaField label='Diagnoses' value={plan.diagnosis_count} />
        <AllevaField label='Behavioral definitions' value={plan.behavioral_definition_count} />
        <AllevaField label='Goals' value={plan.goal_count} />
        <AllevaField label='Objectives' value={plan.objective_count} />
        <AllevaField label='Interventions' value={plan.intervention_count} />
        <AllevaField label='Content value status' value={plan.content_value_status} />
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
          <strong>Patient ID (/clients.id / LeadId): {aggregate.patient_id}</strong>
          <p>
            Patient status {displayAllevaValue(aggregate.status_label)} - {displayAllevaValue(aggregate.status_scope)}
          </p>
        </div>
        <span className={`pill pill--${aggregate.has_multiple_active_plans ? 'warning' : 'success'}`}>
          {aggregate.has_multiple_active_plans ? 'Multiple active treatment plans' : 'Single active treatment-plan set'}
        </span>
      </div>
      <dl>
        <AllevaField label='Alleva status ID' value={aggregate.status_id} fallback='[blank]' />
        <AllevaField label='Admission date' value={aggregate.patient.admission_date} />
        <AllevaField label='Planned discharge date (not actual discharge)' value={aggregate.patient.planned_discharge_date} />
        <AllevaField label='Level of care' value={aggregate.patient.level_of_care} />
        <AllevaField label='Primary clinician' value={aggregate.patient.primary_clinician} />
        <AllevaField label='Total treatment plans' value={aggregate.total_plan_count} />
        <AllevaField label='Active treatment plans' value={aggregate.active_plan_count} />
        <AllevaField label='Multiple active plans present' value={aggregate.has_multiple_active_plans} />
        <AllevaField label='All Treatment Plan IDs' value={aggregate.treatment_plan_ids.join(', ')} />
        <AllevaField label='Active Treatment Plan IDs' value={aggregate.active_treatment_plan_ids.join(', ')} />
        <AllevaField label='Latest-created active Treatment Plan ID' value={aggregate.latest_created_active_plan_id} />
        <AllevaField label='Review data status' value={aggregate.review_data_status} />
        <AllevaField label='Next review due source' value={aggregate.next_review_due_source} />
        <AllevaField label='Review due date status' value={REVIEW_DUE_DATE_UNAVAILABLE} />
        <AllevaField label='Review availability message' value={aggregate.review_availability.message} />
      </dl>
      <p>{REVIEW_DUE_DATE_UNAVAILABLE}</p>
      <p>{aggregate.review_availability.message}</p>
      <div className='finding-list'>{aggregate.treatment_plans.map((plan) => planCard(plan, aggregate.latest_created_active_plan_id))}</div>
    </article>
  )
}
