import { useEffect, useMemo, useRef, useState } from 'react'
import type { ManagerActionPayload } from '../api/types'
import { EvidencePanel } from './EvidencePanel'
import { DataQualityWarningsPanel } from './DataQualityWarningsPanel'
import { RawFieldExplorer } from './RawFieldExplorer'
import { StatusBadge } from './StatusBadge'
import { SourceFileArchiveControls } from './SourceFileArchiveControls'
import { TreatmentPlanClinicalSections } from './TreatmentPlanClinicalSections'
import { planIdentityKey, sourceLabel } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'
import { formatDateTime24Hour, formatUtcEventDateTime } from './treatmentPlanFormatting'
import { TreatmentPlanReviewPanels } from './TreatmentPlanReviewPanels'
import type { ManagerReview, TreatmentPlanAggregate } from '../types/treatmentPlan'

type TreatmentPlanDetailViewerProps = {
  readonly plan: TreatmentPlanAggregate
  readonly canManage: boolean
  readonly onManagerAction: (payload: ManagerActionPayload) => Promise<void>
  readonly onExportChecklistEvidence: () => Promise<void>
  readonly onDownloadSourceDocument: (sourceFileId: string) => Promise<void>
  readonly onDeleteSourceDocument: (sourceFileId: string) => Promise<void>
  readonly isSessionCurrent?: SessionGuard
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


export function TreatmentPlanDetailViewer({
  plan,
  canManage,
  onManagerAction,
  onExportChecklistEvidence,
  onDownloadSourceDocument,
  onDeleteSourceDocument,
  isSessionCurrent,
}: TreatmentPlanDetailViewerProps) {
  const [query, setQuery] = useState('')
  const [selectedCriterionId, setSelectedCriterionId] = useState<string | null>(plan.criteria[0]?.criterionId ?? null)
  const [comment, setComment] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const previousQuery = useRef(query)
  const previousSelectedCriterionId = useRef(selectedCriterionId)
  const identityKey = planIdentityKey(plan)
  const capture = useRequestGeneration(identityKey, isSessionCurrent)
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
    setComment('')
    setOverrideReason('')
    setQuery('')
    setIsSaving(false)
  }, [identityKey])

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
    if (isSaving) return
    const isCurrent = capture()
    if (!isCurrent()) return
    setIsSaving(true)
    try {
      await onManagerAction(payload)
      if (isCurrent()) setActionMessage(successMessage)
    } catch (error) {
      if (isCurrent()) setActionMessage(messageForError(error))
    } finally {
      if (isCurrent()) setIsSaving(false)
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
          <div><dt>Source</dt><dd>{sourceLabel(plan.sourceMode)}</dd></div>
          <div><dt>Patient record</dt><dd>{plan.patientRecordId}</dd></div>
          <div><dt>Saved version ID</dt><dd>{plan.planVersionId}</dd></div>
          <div><dt>Original plan reference</dt><dd>{plan.originalPlanReference || 'Not supplied'}</dd></div>
          <div><dt>Service date</dt><dd>{plan.serviceDate ? formatDateTime24Hour(plan.serviceDate) : 'Not supplied'}</dd></div>
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

      <TreatmentPlanClinicalSections plan={plan} />

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

      <TreatmentPlanReviewPanels plan={plan} canManage={canManage} onExportChecklistEvidence={onExportChecklistEvidence} />

      <DataQualityWarningsPanel warnings={plan.dataQualityWarnings} />

      {canManage ? <SourceFileArchiveControls
        identity={plan}
        isSessionCurrent={isSessionCurrent}
        sourceDocuments={plan.sourceDocuments}
        onDownloadSourceDocument={onDownloadSourceDocument}
        onDeleteSourceDocument={onDeleteSourceDocument}
      /> : <section className='panel'><h2>Source File Archive</h2><p className='muted'>Source-file archive controls are available to manager and admin roles.</p></section>}

      {plan.unassignedManagerReviews.length > 0 && <section className='panel'><h2>Unassigned legacy manager history</h2><p className='muted'>These historical actions have no proven saved-version link and do not affect this selected plan.</p><ul>{plan.unassignedManagerReviews.map((review, index) => <li key={managerReviewKey(review, index)}>{review.managerStatus} · {formatUtcEventDateTime(review.createdAt)}{review.comment && <span> Comment: {review.comment}</span>}</li>)}</ul></section>}

      <RawFieldExplorer plan={plan} />
    </div>
  )
}
