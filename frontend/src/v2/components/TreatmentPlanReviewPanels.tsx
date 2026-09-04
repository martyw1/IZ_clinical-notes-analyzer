import type { CriterionResult, ManagerReview, TreatmentPlanAggregate } from '../types/treatmentPlan'
import { formatUtcEventDateTime } from './treatmentPlanFormatting'

type Props = {
  readonly plan: TreatmentPlanAggregate
  readonly canManage: boolean
  readonly onExportChecklistEvidence: () => Promise<void>
}

function managerReviewKey(review: ManagerReview, index: number): string {
  return `${review.criterionId}-${review.action}-${review.createdAt}-${index}`
}

function countCriteriaByStatus(criteria: readonly CriterionResult[], status: CriterionResult['status']): number {
  return criteria.filter((criterion) => criterion.status === status).length
}

export function TreatmentPlanReviewPanels({ plan, canManage, onExportChecklistEvidence }: Props) {
  return <>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Manager review history</p>
            <h2>Persisted manager actions</h2>
          </div>
          <span>{plan.managerReviews.length} saved</span>
        </div>
        {plan.managerReviews.length ? (
          <ul className='artifact-list'>
            {plan.managerReviews.map((review, index) => (
              <li key={managerReviewKey(review, index)}>
                <strong>{review.managerStatus}</strong> on <code>{review.criterionId}</code>
                {review.actorUsername && <> by {review.actorUsername}</>}
                {review.createdAt && <> at {formatUtcEventDateTime(review.createdAt)}</>}
                {review.comment && <span> Comment: {review.comment}</span>}
                {review.overrideReason && <span> Override reason: {review.overrideReason}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className='muted'>No persisted manager actions yet.</p>
        )}
      </section>

      <section className='panel'>
        {canManage && <div className='button-row'><button type='button' className='secondary-button' onClick={() => void onExportChecklistEvidence()}>Export minimum-necessary checklist evidence</button></div>}
        <h2>Evidence Coverage Map</h2>
        <p className='muted evidence-coverage-note'>Source support is reported separately from checklist result statuses. A criterion may have observed evidence and still be Missing Data, Conflicting Evidence, or Unable to Evaluate. These displayed subtotals can overlap and do not partition the 42 criteria; unknown and Not Applicable outcomes remain distinct.</p>
        <div className='summary-grid evidence-coverage-summary'>
          <span className='evidence-coverage-metric'><span>Checklist criteria total</span> <span>{plan.evidenceCoverageSummary.criteriaTotal}</span></span>
          <span className='evidence-coverage-metric'><span>Source support: observed evidence</span> <span>{plan.evidenceCoverageSummary.criteriaWithEvidence}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Missing Data</span> <span>{plan.evidenceCoverageSummary.criteriaMissingEvidence}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Conflicting Evidence</span> <span>{plan.evidenceCoverageSummary.criteriaConflicting}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Unable to Evaluate</span> <span>{countCriteriaByStatus(plan.criteria, 'Unable to Evaluate')}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Not Applicable</span> <span>{countCriteriaByStatus(plan.criteria, 'Not Applicable')}</span></span>
          <span className='evidence-coverage-metric'><span>Runtime-only fields</span> <span>{plan.evidenceCoverageSummary.runtimeOnlyFields.length}</span></span>
        </div>
        <p className='muted'>Runtime-only fields are source values outside the checklist. Their count is not a checklist result and is not added to the 42-criterion total.</p>
      </section>
  </>
}
