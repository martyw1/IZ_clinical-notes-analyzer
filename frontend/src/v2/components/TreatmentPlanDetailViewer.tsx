import { useEffect, useMemo, useRef, useState } from 'react'
import type { ManagerActionPayload } from '../api/types'
import { EvidencePanel } from './EvidencePanel'
import { DataQualityWarningsPanel } from './DataQualityWarningsPanel'
import { RawFieldExplorer } from './RawFieldExplorer'
import { StatusBadge } from './StatusBadge'
import { SourceFileArchiveControls } from './SourceFileArchiveControls'
import { formatDateTime24Hour, formatUtcEventDateTime } from './treatmentPlanFormatting'
import type { CriterionResult, ManagerReview, TreatmentPlanAggregate } from '../types/treatmentPlan'

type TreatmentPlanDetailViewerProps = {
  readonly plan: TreatmentPlanAggregate
  readonly canManage: boolean
  readonly onManagerAction: (payload: ManagerActionPayload) => Promise<void>
  readonly onExportChecklistEvidence: () => Promise<void>
  readonly onDownloadSourceDocument: (sourceFileId: string) => Promise<void>
  readonly onDeleteSourceDocument: (sourceFileId: string) => Promise<void>
}

function messageForError(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Unable to save manager action.'
}

function managerReviewKey(review: ManagerReview, index: number): string {
  return `${review.criterionId}-${review.action}-${review.createdAt}-${index}`
}

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

export function TreatmentPlanDetailViewer({
  plan,
  canManage,
  onManagerAction,
  onExportChecklistEvidence,
  onDownloadSourceDocument,
  onDeleteSourceDocument,
}: TreatmentPlanDetailViewerProps) {
  const [query, setQuery] = useState('')
  const [selectedCriterionId, setSelectedCriterionId] = useState<string | null>(plan.criteria[0]?.criterionId ?? null)
  const [comment, setComment] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const previousQuery = useRef(query)
  const previousSelectedCriterionId = useRef(selectedCriterionId)
  const filteredCriteria = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return plan.criteria
    return plan.criteria.filter((criterion) => [
      criterion.title,
      criterion.finding,
      criterion.safePreview,
      criterion.sourcePath,
    ].some((value) => value.toLowerCase().includes(normalized)))
  }, [plan.criteria, query])
  const selectedCriterion = filteredCriteria.find((criterion) => criterion.criterionId === selectedCriterionId) ?? filteredCriteria[0] ?? null

  useEffect(() => {
    setSelectedCriterionId(plan.criteria[0]?.criterionId ?? null)
    setActionMessage('')
  }, [plan.treatmentPlanId])

  useEffect(() => {
    const nextSelection = filteredCriteria.some((criterion) => criterion.criterionId === selectedCriterionId)
      ? selectedCriterionId
      : filteredCriteria[0]?.criterionId ?? null
    if (nextSelection !== selectedCriterionId) setSelectedCriterionId(nextSelection)
  }, [filteredCriteria, selectedCriterionId])

  useEffect(() => {
    const queryChanged = previousQuery.current !== query
    const selectionChanged = previousSelectedCriterionId.current !== selectedCriterionId
    if (queryChanged || selectionChanged) setActionMessage('')
    previousQuery.current = query
    previousSelectedCriterionId.current = selectedCriterionId
  }, [query, selectedCriterionId])

  const saveReturn = async () => {
    if (!selectedCriterion) return
    if (!comment.trim()) {
      setActionMessage('Add a comment before returning a criterion.')
      return
    }
    await saveAction({
      criterionId: selectedCriterion.criterionId,
      action: 'return_for_correction',
      comment,
      overrideReason: '',
    }, 'Criterion returned for correction with manager comment.')
  }

  const saveOverride = async () => {
    if (!selectedCriterion) return
    if (!overrideReason.trim()) {
      setActionMessage('Override reason is required.')
      return
    }
    await saveAction({
      criterionId: selectedCriterion.criterionId,
      action: 'override',
      comment,
      overrideReason,
    }, 'Override saved with required reason and audit event.')
  }

  const saveApproval = async () => {
    if (!selectedCriterion) return
    await saveAction({ criterionId: selectedCriterion.criterionId, action: 'approve', comment, overrideReason: '' }, 'Approval saved as a manager disposition.')
  }

  const saveComment = async () => {
    if (!selectedCriterion || !comment.trim()) {
      setActionMessage('Add a comment before saving it.')
      return
    }
    await saveAction({ criterionId: selectedCriterion.criterionId, action: 'comment', comment, overrideReason: '' }, 'Manager comment saved without changing deterministic results.')
  }

  async function saveAction(payload: ManagerActionPayload, successMessage: string) {
    setIsSaving(true)
    try {
      await onManagerAction(payload)
      setActionMessage(successMessage)
    } catch (error) {
      setActionMessage(messageForError(error))
    } finally {
      setIsSaving(false)
    }
  }

  const selectedPlanHistory = plan.planHistory[0]

  return (
    <div className='detail-grid treatment-plan-document'>
      <section className='panel detail-identity-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Selected Treatment Plan Detail</p>
            <h2>Treatment Plan ID {plan.treatmentPlanId}</h2>
            {plan.patientFullName && <p className='patient-full-name'>{plan.patientFullName}</p>}
            <p className='muted'>{plan.patientDisplayLabel}</p>
          </div>
          <StatusBadge status={plan.status} />
        </div>
        <dl className='plan-fact-grid'>
          <div><dt>Level of care</dt><dd>{plan.currentLevelOfCare}</dd></div>
          <div><dt>Source</dt><dd>{plan.sourceMode}</dd></div>
          <div><dt>Last updated</dt><dd>{displayDate(plan.lastUpdated)}</dd></div>
          <div><dt>Evaluation</dt><dd>{displayDate(plan.evaluationDate)} · {plan.facilityTimezone}</dd></div>
        </dl>
        <label>
          Search checklist evidence
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search criteria and evidence' />
        </label>
      </section>

      <section className='panel plan-timeline-panel'>
        <p className='eyebrow'>Dates and source comparison</p>
        <h2>Plan timeline</h2>
        <ol className='plan-timeline'>
          <li><span>Admission</span><time dateTime={plan.admissionDate}>{displayDate(plan.admissionDate)}</time></li>
          <li><span>Plan created</span><time dateTime={selectedPlanHistory?.planDate || selectedPlanHistory?.createdDate}>{displayDate(selectedPlanHistory?.planDate || selectedPlanHistory?.createdDate || 'Unknown')}</time></li>
          <li><span>Source last updated</span><time dateTime={plan.lastUpdated}>{displayDate(plan.lastUpdated)}</time></li>
        </ol>
        <dl className='source-comparison-grid'>
          <div><dt>Source due date</dt><dd>{displayDate(plan.sourceDueDate)}</dd></div>
          <div><dt>Computed due date</dt><dd>{displayDate(plan.dueDate)}</dd></div>
          <div><dt>LOC-change clock</dt><dd>{plan.locChangeDueDate}</dd></div>
          <div><dt>Checklist / rules</dt><dd>{plan.checklistVersion} / {plan.rulesVersion}</dd></div>
        </dl>
      </section>

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

      <section className='panel checklist-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>42-step checklist</p>
            <h2>Checklist Evidence</h2>
          </div>
          <span>{plan.criteria.length} criteria</span>
        </div>
        <div className='criterion-list' aria-label='Checklist criteria'>
          {filteredCriteria.map((criterion) => (
            <button
              key={criterion.criterionId}
              type='button'
              className='criterion-row'
              aria-pressed={criterion.criterionId === selectedCriterion?.criterionId}
              onClick={() => setSelectedCriterionId(criterion.criterionId)}
            >
              <span>{criterion.title}</span>
              <StatusBadge status={criterion.status} />
            </button>
          ))}
        </div>
        {filteredCriteria.length === 0 && <p className='muted' role='status'>{query.trim() ? `No checklist evidence matches “${query.trim()}”.` : 'No checklist criteria returned for this plan.'}</p>}
        {selectedCriterion && <EvidencePanel criterion={selectedCriterion} />}
        {canManage ? <div className='manager-actions'>
          <label>
            Manager comment
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
          <label>
            Override reason
            <input value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} />
          </label>
          <div className='button-row'>
            <button type='button' className='secondary-button' onClick={saveApproval} disabled={isSaving || !selectedCriterion}>Approve criterion</button>
            <button type='button' className='secondary-button' onClick={saveComment} disabled={isSaving || !selectedCriterion}>Save comment</button>
            <button type='button' className='secondary-button' onClick={saveReturn} disabled={isSaving || !selectedCriterion}>Return for correction</button>
            <button type='button' className='secondary-button' onClick={saveOverride} disabled={isSaving || !selectedCriterion}>Save override</button>
          </div>
          {!selectedCriterion && <p className='muted'>Manager actions are disabled until a matching checklist criterion is selected.</p>}
          {actionMessage && <p role='status'>{actionMessage}</p>}
        </div> : <p className='muted'>Manager review actions are available to manager and admin roles.</p>}
      </section>

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
          <span className='evidence-coverage-metric'><span>Source support: missing evidence</span> <span>{plan.evidenceCoverageSummary.criteriaMissingEvidence}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Conflicting Evidence</span> <span>{plan.evidenceCoverageSummary.criteriaConflicting}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Unable to Evaluate</span> <span>{countCriteriaByStatus(plan.criteria, 'Unable to Evaluate')}</span></span>
          <span className='evidence-coverage-metric'><span>Result status: Not Applicable</span> <span>{countCriteriaByStatus(plan.criteria, 'Not Applicable')}</span></span>
          <span className='evidence-coverage-metric'><span>Runtime-only fields</span> <span>{plan.evidenceCoverageSummary.runtimeOnlyFields.length}</span></span>
        </div>
        <p className='muted'>Runtime-only fields are source values outside the checklist. Their count is not a checklist result and is not added to the 42-criterion total.</p>
      </section>

      <DataQualityWarningsPanel warnings={plan.dataQualityWarnings} />

      {canManage ? <SourceFileArchiveControls
        patientId={plan.patientId}
        sourceDocuments={plan.sourceDocuments}
        onDownloadSourceDocument={onDownloadSourceDocument}
        onDeleteSourceDocument={onDeleteSourceDocument}
      /> : <section className='panel'><h2>Source File Archive</h2><p className='muted'>Source-file archive controls are available to manager and admin roles.</p></section>}

      <RawFieldExplorer plan={plan} />
    </div>
  )
}

function displayOverviewValue(value: string, fallback: string): string {
  const normalized = value.trim()
  return !normalized || normalized === fallback || normalized === 'Unknown' ? 'Not supplied' : value
}

function displayMetadataValue(value: string): string {
  return value.trim() || 'Not supplied'
}

function countCriteriaByStatus(criteria: readonly CriterionResult[], status: CriterionResult['status']): number {
  return criteria.filter((criterion) => criterion.status === status).length
}
