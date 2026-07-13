import { useEffect, useMemo, useState } from 'react'
import type { ManagerActionPayload } from '../api/types'
import { EvidencePanel } from './EvidencePanel'
import { DataQualityWarningsPanel } from './DataQualityWarningsPanel'
import { RawFieldExplorer } from './RawFieldExplorer'
import { StatusBadge } from './StatusBadge'
import { SourceFileArchiveControls } from './SourceFileArchiveControls'
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
  const filteredCriteria = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return plan.criteria
    return plan.criteria.filter((criterion) => criterion.title.toLowerCase().includes(normalized))
  }, [plan.criteria, query])
  const selectedCriterion = plan.criteria.find((criterion) => criterion.criterionId === selectedCriterionId) ?? plan.criteria[0] ?? null

  useEffect(() => {
    setSelectedCriterionId(plan.criteria[0]?.criterionId ?? null)
    setActionMessage('')
  }, [plan.treatmentPlanId])

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

  return (
    <div className='detail-grid'>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Selected Treatment Plan Detail</p>
            <h2>Treatment Plan ID {plan.treatmentPlanId}</h2>
            <p className='muted'>Patient ID {plan.patientId}</p>
          </div>
          <StatusBadge status={plan.status} />
        </div>
        <div className='summary-grid'>
          <span>Current LOC: {plan.currentLevelOfCare}</span>
          <span>Admission: <time dateTime={plan.admissionDate}>{plan.admissionDate}</time></span>
          <span>Next due: <time dateTime={plan.dueDate}>{plan.dueDate}</time></span>
          <span>Source due: {plan.sourceDueDate}</span>
          <span className='summary-grid__item--wrappable'>LOC-change clock: {plan.locChangeDueDate}</span>
          <span>Evaluated: {plan.evaluationDate} ({plan.facilityTimezone})</span>
          <span>Checklist/rules: {plan.checklistVersion} / {plan.rulesVersion}</span>
          <span>Source: {plan.sourceMode}</span>
        </div>
        <label>
          Search treatment-plan content
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search criteria and evidence' />
        </label>
      </section>

      <section className='panel content-panel'>
        <h2>Clinical Content</h2>
        <p><strong>Reason for admission:</strong> {plan.reasonForAdmission}</p>
        <p><strong>Initial client needs:</strong> {plan.initialClientNeeds}</p>
        <p><strong>Family education needs:</strong> {plan.familyEducationNeeds}</p>
        {plan.problems.map((problem) => (
          <details key={problem.problemNumber} open>
            <summary>Problem {problem.problemNumber}: {problem.description}</summary>
            <h3>Diagnoses</h3>
            <ul>{problem.diagnoses.map((diagnosis) => <li key={diagnosis}>{diagnosis}</li>)}</ul>
            <h3>Behavioral Definitions</h3>
            <ul>{problem.behavioralDefinitions.map((definition) => <li key={definition}>{definition}</li>)}</ul>
            <h3>Goals</h3>
            {problem.goals.map((goal) => (
              <details key={goal.goalNumber} open>
                <summary>Goal {goal.goalNumber}: {goal.description}</summary>
                {goal.objectives.map((objective) => (
                  <details key={objective.objectiveNumber} open>
                    <summary>Objective {objective.objectiveNumber}: {objective.description}</summary>
                    <h4>Interventions</h4>
                    <ul>{objective.interventions.map((intervention) => <li key={intervention}>{intervention}</li>)}</ul>
                  </details>
                ))}
              </details>
            ))}
          </details>
        ))}
      </section>

      <section className='panel'>
        <h2>Signatures</h2>
        {plan.signatures.map((signature) => (
          <dl key={signature.signatureType} className='signature-grid'>
            <div><dt>Type</dt><dd>{signature.signatureType}</dd></div>
            <div><dt>Signer role</dt><dd>{signature.signerRoleOrType}</dd></div>
            <div><dt>Signed</dt><dd>{signature.signatureDatetime}</dd></div>
            <div><dt>Image/base64</dt><dd>{signature.signatureDataOmittedReason}</dd></div>
          </dl>
        ))}
      </section>

      <section className='panel checklist-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>42-step checklist</p>
            <h2>Checklist Evidence</h2>
          </div>
          <span>{plan.criteria.length} criteria</span>
        </div>
        <div className='criterion-list'>
          {filteredCriteria.map((criterion) => (
            <button key={criterion.criterionId} type='button' className='criterion-row' onClick={() => setSelectedCriterionId(criterion.criterionId)}>
              <span>{criterion.title}</span>
              <StatusBadge status={criterion.status} />
            </button>
          ))}
        </div>
        {selectedCriterion ? <EvidencePanel criterion={selectedCriterion} /> : <p className='muted'>No checklist criteria returned for this plan.</p>}
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
            <button type='button' onClick={saveReturn} disabled={isSaving || !selectedCriterion}>Return for correction</button>
            <button type='button' className='secondary-button' onClick={saveOverride} disabled={isSaving || !selectedCriterion}>Save override</button>
          </div>
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
                {review.createdAt && <> at {review.createdAt}</>}
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
        <div className='summary-grid'>
          <span>Criteria total: {plan.evidenceCoverageSummary.criteriaTotal}</span>
          <span>With evidence: {plan.evidenceCoverageSummary.criteriaWithEvidence}</span>
          <span>Missing evidence: {plan.evidenceCoverageSummary.criteriaMissingEvidence}</span>
          <span>Conflicting evidence: {plan.evidenceCoverageSummary.criteriaConflicting}</span>
          <span>Runtime-only fields: {plan.evidenceCoverageSummary.runtimeOnlyFields.length}</span>
        </div>
        <p>Used, missing, unmapped, and unused content are separated so managers can see what the checklist did and did not evaluate.</p>
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
