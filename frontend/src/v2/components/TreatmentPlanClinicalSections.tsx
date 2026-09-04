import type { TreatmentPlanAggregate } from '../types/treatmentPlan'
import { formatDateTime24Hour } from './treatmentPlanFormatting'

function displayDate(value: string): string {
  return value && value !== 'Unknown' ? formatDateTime24Hour(value) : 'Unknown'
}

function diagnosisParts(value: string): { readonly code: string; readonly description: string } {
  const [possibleCode, ...description] = value.split(' ')
  if (/^[A-Z][0-9]/i.test(possibleCode) && description.length) {
    return { code: possibleCode, description: description.join(' ') }
  }
  return { code: '', description: value }
}

export function TreatmentPlanClinicalSections({ plan }: { readonly plan: TreatmentPlanAggregate }) {
  return <>
      <section className='panel content-panel clinical-document'>
        <p className='eyebrow'>Merged source content</p>
        <h2>Clinical overview</h2>
        <dl className='clinical-overview-grid'>
          <div><dt>Reason for admission</dt><dd>{displayOverviewValue(plan.reasonForAdmission, 'No reason-for-admission text returned.')}</dd></div>
          <div><dt>Initial client needs</dt><dd>{displayOverviewValue(plan.initialClientNeeds, 'No initial-needs text returned.')}</dd></div>
          <div><dt>Family education needs</dt><dd>{displayOverviewValue(plan.familyEducationNeeds, 'No family-education text returned.')}</dd></div>
        </dl>
        {plan.problems.map((problem) => (
          <article className='clinical-problem' key={`${problem.problemNumber}:${problem.description}`}>
            <header>
              <p className='eyebrow'>Problem {problem.problemNumber}</p>
              <h3>{problem.description || 'Description unavailable'}</h3>
            </header>
            {problem.diagnoses.length > 0 && <div className='clinical-subsection'>
              <h4>Diagnoses</h4>
              <ul className='clinical-list'>{problem.diagnoses.map((diagnosis) => {
                const parts = diagnosisParts(diagnosis)
                return <li key={diagnosis}>{parts.code && <code>{parts.code}</code>}<span>{parts.description}</span></li>
              })}</ul>
            </div>}
            {problem.behavioralDefinitions.length > 0 && <div className='clinical-subsection'>
              <h4>Behavioral definitions</h4>
              <ul className='clinical-list'>{problem.behavioralDefinitions.map((definition) => <li key={definition}>{definition}</li>)}</ul>
            </div>}
            {problem.goals.map((goal) => (
              <section className='clinical-goal' key={`${goal.goalNumber}:${goal.description}`}>
                <p className='eyebrow'>Goal {goal.goalNumber}</p>
                <h4>{goal.description || 'Description unavailable'}</h4>
                {goal.objectives.map((objective) => (
                  <div className='clinical-objective' key={`${objective.objectiveNumber}:${objective.description}`}>
                    <h5>Objective {objective.objectiveNumber}</h5>
                    <p>{objective.description || 'Description unavailable'}</p>
                    {objective.interventions.length > 0 && <>
                      <h6>Interventions</h6>
                      <ul className='clinical-list'>{objective.interventions.map((intervention) => <li key={intervention}>{intervention}</li>)}</ul>
                    </>}
                  </div>
                ))}
              </section>
            ))}
          </article>
        ))}
        {plan.problems.length === 0 && <p className='muted'>No structured problem, goal, objective, or intervention content was returned.</p>}
      </section>

      <section className='panel review-history-panel'>
        <p className='eyebrow'>Signatures and source reviews</p>
        <h2>Clinical review history</h2>
        <div className='review-history-grid'>
          <div>
            <h3>Signatures</h3>
            {plan.signatures.length > 0 ? <ul className='review-timeline'>{plan.signatures.map((signature) => (
              <li key={`${signature.signatureType}:${signature.signatureDatetime}`}>
                <dl className='review-metadata signature-metadata'>
                  <div><dt>Signature type</dt><dd>{displayMetadataValue(signature.signatureType)}</dd></div>
                  <div><dt>Signer role or type</dt><dd>{displayMetadataValue(signature.signerRoleOrType)}</dd></div>
                  <div><dt>Signature date</dt><dd><time dateTime={signature.signatureDatetime}>{displayDate(signature.signatureDatetime)}</time></dd></div>
                  <div><dt>Explanation</dt><dd>{displayMetadataValue(signature.signatureDataOmittedReason)}</dd></div>
                </dl>
              </li>
            ))}</ul> : <p className='muted'>No signature metadata was returned.</p>}
          </div>
          <div>
            <h3>Treatment reviews</h3>
            {plan.treatmentReviews.length > 0 ? <ul className='review-timeline'>{plan.treatmentReviews.map((review) => (
              <li key={`${review.reviewId}:${review.reviewDate}:${review.signatureDate}`}>
                <dl className='review-metadata'>
                  <div><dt>Review status</dt><dd>{displayMetadataValue(review.status)}</dd></div>
                  <div><dt>Review ID</dt><dd>{review.reviewId ? `Review ${review.reviewId}` : 'Not supplied'}</dd></div>
                  <div><dt>Review date</dt><dd><time dateTime={review.reviewDate}>{displayDate(review.reviewDate)}</time></dd></div>
                  <div><dt>Signature date</dt><dd>{review.signatureDate ? <time dateTime={review.signatureDate}>{displayDate(review.signatureDate)}</time> : 'Not supplied'}</dd></div>
                </dl>
              </li>
            ))}</ul> : <p className='muted'>No treatment-review records were returned for this plan.</p>}
          </div>
        </div>
      </section>
  </>
}

function displayOverviewValue(value: string, fallback: string): string {
  const normalized = value.trim()
  return !normalized || normalized === fallback || normalized === 'Unknown' ? 'Not supplied' : value
}

function displayMetadataValue(value: string): string {
  return value.trim() || 'Not supplied'
}
