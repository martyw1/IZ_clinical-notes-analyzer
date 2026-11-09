import { Fragment } from 'react'
import { DeadlineIndicator } from '../components/DeadlineIndicator'
import { useEffect, useMemo, useState } from 'react'
import { getTreatmentPlanRoster } from '../api/client'
import { downloadTreatmentPlanListExport } from '../api/downloads'
import { ApiRequestError } from '../api/json'
import { getApiConfiguration } from '../api/settingsClient'
import type { ApiConfiguration, PatientSelection, TreatmentPlanRosterData, TreatmentPlanSelection, UserProfile } from '../api/types'
import { ApprovedQueueImportCard } from '../components/ApprovedQueueImportCard'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'
import { SourceFilterControl } from '../components/SourceFilterControl'
import { sourceLabel } from '../types/identity'
import type { SourceFilter } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type WorklistMode = 'All plans' | 'Overdue' | 'Due Soon' | 'Overdue by clinician'

type TreatmentPlansRosterPageProps = {
  readonly initialMode?: WorklistMode
  readonly token: string
  readonly user: UserProfile
  readonly onNavigate: (view: string) => void
  readonly onSelectPatient: (selection: PatientSelection) => void
  readonly onSelectTreatmentPlan: (selection: TreatmentPlanSelection) => void
  readonly isSessionCurrent?: SessionGuard
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the treatment plans roster.'
}

export function TreatmentPlansRosterPage({
  token,
  initialMode = 'All plans',
  user,
  onNavigate,
  onSelectPatient,
  onSelectTreatmentPlan,
  isSessionCurrent,
}: TreatmentPlansRosterPageProps) {
  const [roster, setRoster] = useState<TreatmentPlanRosterData | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [mode, setMode] = useState(initialMode)
  const [counselorQuery, setCounselorQuery] = useState('')
  const [counselorId, setCounselorId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [isExporting, setIsExporting] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [showReviewed, setShowReviewed] = useState(false)
  const [page, setPage] = useState(0)
  const pageSize = 75
  const sourceMode = sourceFilter === 'all' ? undefined : sourceFilter
  const capture = useRequestGeneration(`${token}:${sourceFilter}:${refreshNumber}`, isSessionCurrent)
  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    const matches = (roster?.items ?? []).filter((item) => (
      (mode === 'All plans' || item.deadlineStatus === (mode === 'Overdue by clinician' ? 'Overdue' : mode))
      && (!sourceMode || item.sourceMode === sourceMode) && (!normalized
      || item.mrn.toLowerCase().includes(normalized)
      || item.fullName.toLowerCase().includes(normalized)
      || item.treatmentPlanId.toLowerCase().includes(normalized)
      || item.originalPlanReference.toLowerCase().includes(normalized)
      || item.serviceDate.toLowerCase().includes(normalized)
      || item.previousTreatmentPlanId.toLowerCase().includes(normalized)
      || item.initialTreatmentPlanId.toLowerCase().includes(normalized)
      || (!item.linkedToMrn && 'not linked to an mrn'.includes(normalized)))
    ))
    if (mode === 'Overdue by clinician') return matches.sort((left, right) =>
      (left.primaryCounselorName || 'Unassigned').localeCompare(right.primaryCounselorName || 'Unassigned')
      || (left.primaryCounselorId ?? 0) - (right.primaryCounselorId ?? 0)
      || (right.daysOverdue ?? 0) - (left.daysOverdue ?? 0))
    if (mode === 'Overdue') return matches.sort((left, right) => (right.daysOverdue ?? 0) - (left.daysOverdue ?? 0))
    if (mode === 'Due Soon') return matches.sort((left, right) => (left.nextDueDate ?? '').localeCompare(right.nextDueDate ?? ''))
    return matches
  }, [mode, query, roster?.items, sourceMode])

  const groups = new Map<number, { name: string; count: number }>()
  if ((mode === 'Overdue' || mode === 'Overdue by clinician')) {
    for (const row of visibleItems) {
      const id = row.primaryCounselorId ?? 0
      const existing = groups.get(id)
      groups.set(id, { name: row.primaryCounselorName || 'Unassigned', count: (existing?.count ?? 0) + 1 })
    }
  }
  const groupRows = (mode === 'Overdue' || mode === 'Overdue by clinician') && counselorId !== null
    ? visibleItems.filter((item) => (item.primaryCounselorId ?? 0) === counselorId)
    : visibleItems
  const reviewedCount = (mode === 'Overdue' || mode === 'Overdue by clinician') ? groupRows.filter((item) => item.reviewedAtUtc).length : 0
  const worklistRows = (mode === 'Overdue' || mode === 'Overdue by clinician') && !showReviewed
    ? groupRows.filter((item) => !item.reviewedAtUtc)
    : groupRows

  useEffect(() => {
    const isCurrent = capture()
    setIsLoading(true)
    setError('')
    setIsExporting(false)
    void getTreatmentPlanRoster(token, sourceMode).then((result) => {
      if (isCurrent()) {
        setRoster(result)
        setPage(0)
      }
    }).catch((loadError: unknown) => {
      if (isCurrent()) setError(messageForError(loadError))
    }).finally(() => { if (isCurrent()) setIsLoading(false) })
  }, [refreshNumber, token, sourceMode, capture, isSessionCurrent])

  useEffect(() => {
    if (user.role !== 'admin') return
    let cancelled = false
    void getApiConfiguration(token).then((result) => {
      if (!cancelled) setApiConfig(result)
    }).catch((loadError: unknown) => {
      if (!cancelled) setError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [token, user.role])

  async function exportRoster() {
    if (isExporting) return
    const isCurrent = capture()
    if (!isCurrent()) return
    setIsExporting(true)
    try {
      await downloadTreatmentPlanListExport(token, { planVersionIds: worklistRows.map((item) => item.planVersionId), sourceMode, isCurrent })
    } catch (downloadError) {
      if (isCurrent()) setError(messageForError(downloadError))
    } finally {
      if (isCurrent()) setIsExporting(false)
    }
  }

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>

  return (
    <div className='treatment-workbench'>
      {user.role === 'admin' && (
        <ApprovedQueueImportCard
          config={apiConfig}
          token={token}
          onNavigate={onNavigate}
          onCompleted={() => setRefreshNumber((current) => current + 1)}
          showOpenQueueButton={false}
          buttonLabel='Pull full treatment plans'
        />
      )}
      {!roster ? <section className='panel muted'>Loading treatment plans roster...</section> : <section className='panel table-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Source-aware treatment plans</p>
            <h2>Treatment Plans Roster</h2>
            <p className='muted'>CSV exports all {worklistRows.length} filtered results, including rows outside the current viewport. Names and search text are excluded.</p>
            <p className='muted'>Latest saved Manual and Alleva plans, organized by exact patient record and plan lineage.</p>
          </div>
          <div className='button-row'>
            {(user.role === 'admin' || user.role === 'office_manager') && (
              <button type='button' className='secondary-button' disabled={isExporting} onClick={() => void exportRoster()}>Export treatment plans and statuses</button>
            )}
            <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh roster</button>
          </div>
        </div>
        <label>
          Search MRN, patient name, plan ID, reference, or service date
          <input value={query} onChange={(event) => { setQuery(event.currentTarget.value); setPage(0) }} placeholder='MRN, patient name, or treatment plan ID' />
        </label>
        <SourceFilterControl value={sourceFilter} onChange={(value) => { setSourceFilter(value); setPage(0) }} />
        <label>Worklist
          <select value={mode} onChange={(event) => { setMode(event.currentTarget.value as WorklistMode); setCounselorId(null); setShowReviewed(false); setPage(0) }}>
            <option>All plans</option>
            <option>Overdue</option>
            <option>Overdue by clinician</option>
            <option value='Due Soon'>Due soon</option>
          </select>
        </label>
        {(mode === 'Overdue' || mode === 'Overdue by clinician') && <section aria-label='Clinicians with overdue plans'>
          <label>Search overdue clinicians
            <input value={counselorQuery} onChange={(event) => setCounselorQuery(event.currentTarget.value)} />
          </label>
          <div className='button-row'>
            <button type='button' aria-pressed={counselorId === null}
              onClick={() => { setCounselorId(null); setPage(0) }}>All clinicians ({visibleItems.length})</button>
            {[...groups].filter(([, group]) => group.name.toLowerCase().includes(counselorQuery.trim().toLowerCase()))
              .sort((left, right) => left[1].name.localeCompare(right[1].name))
              .map(([id, group]) => <button type='button' key={id} aria-pressed={counselorId === id}
                onClick={() => { setCounselorId(id); setPage(0) }}>
                {group.name}{id > 0 && ` (#${id})`} ({group.count})
              </button>)}
          </div>
        </section>}
        {(mode === 'Overdue' || mode === 'Overdue by clinician') && <button type='button' aria-expanded={showReviewed}
          onClick={() => { setShowReviewed(!showReviewed); setPage(0) }}>
          Reviewed overdue ({reviewedCount})
        </button>}
        <table>
          <thead>
            <tr role='row'>
              <th id='plan-roster-id' role='columnheader'>Treatment Plan ID</th>
              <th id='plan-roster-mrn' role='columnheader'>MRN</th>
              <th id='plan-roster-counselor' role='columnheader'>Primary clinician</th>
              <th id='plan-roster-last-updated' role='columnheader'>Last Updated</th>
              <th id='plan-roster-due' role='columnheader'>Next due date</th>
              <th id='plan-roster-overdue' role='columnheader'>Days overdue</th>
              <th id='plan-roster-reviewed' role='columnheader'>Reviewed</th>
              <th id='plan-roster-previous-id' role='columnheader'>Previous Treatment Plan ID</th>
              <th id='plan-roster-initial' role='columnheader'>Initial Treatment Plan</th>
            </tr>
          </thead>
          <tbody>
            {worklistRows.slice(page * pageSize, (page + 1) * pageSize).map((item, index, pageRows) => (
              <Fragment key={item.planVersionId}>
              {mode === 'Overdue by clinician' && (index === 0 || pageRows[index - 1].primaryCounselorId !== item.primaryCounselorId) &&
                <tr className='clinician-group-heading'><th colSpan={9} scope='rowgroup'>{item.primaryCounselorName || 'Unassigned'} · most overdue first</th></tr>}
              <tr role='row' data-plan-version-id={item.planVersionId} data-patient-record-id={item.patientRecordId} data-source-mode={item.sourceMode}>
                <td role='cell' data-label='Treatment Plan ID' headers='plan-roster-id'>
                  <button
                    type='button'
                    className='link-button'
                    aria-label={item.linkedToMrn
                      ? `Open treatment plan ${item.treatmentPlanId} for MRN ${item.mrn}`
                      : `Open treatment plan ${item.treatmentPlanId}, not linked to an MRN`}
                    onClick={() => onSelectTreatmentPlan({
                      mrn: item.mrn,
                      patientKey: item.patientKey,
                      patientRecordId: item.patientRecordId,
                      planVersionId: item.planVersionId,
                      treatmentPlanId: item.treatmentPlanId,
                      sourceMode: item.sourceMode,
                    })}
                  >
                    {item.treatmentPlanId}
                  </button>
                  <div>{sourceLabel(item.sourceMode)} · record {item.patientRecordId} · version {item.versionOrdinal} (#{item.planVersionId})</div>
                  <div>Reference: {item.originalPlanReference || 'Not supplied'}</div>
                  <div>Service date: {item.serviceDate ? formatDateTime24Hour(item.serviceDate) : 'Not supplied'}</div>
                </td>
                <td role='cell' data-label='MRN' headers='plan-roster-mrn'>
                  {item.linkedToMrn ? (
                    <span className='patient-identity'>
                      <button
                        type='button'
                        className='link-button patient-record-link'
                        aria-label={`Open patient record for ${item.fullName || 'Name unavailable'}, MRN ${item.mrn}`}
                        onClick={() => onSelectPatient({ mrn: item.mrn, patientKey: item.patientKey, patientRecordId: item.patientRecordId, sourceMode: item.sourceMode })}
                      >
                        {item.mrn}
                      </button>
                      <span className='patient-name-secondary'>{item.fullName || 'Name unavailable'}</span>
                    </span>
                  ) : <strong>Not linked to an MRN</strong>}
                </td>
                <td role='cell' data-label='Primary clinician' headers='plan-roster-counselor'>{item.primaryCounselorName || 'Unassigned'}</td>
                <td role='cell' data-label='Last Updated' headers='plan-roster-last-updated'><time dateTime={item.lastUpdated}>{formatDateTime24Hour(item.lastUpdated)}</time></td>
                <td role='cell' data-label='Next due date' headers='plan-roster-due'>
                  <DeadlineIndicator dueDate={item.nextDueDate} status={item.deadlineStatus} />
                </td>
                <td role='cell' data-label='Days overdue' headers='plan-roster-overdue'>{item.daysOverdue || '—'}</td>
                <td role='cell' data-label='Reviewed' headers='plan-roster-reviewed'>{item.reviewedAtUtc ? 'Yes' : 'No'}</td>
                <td role='cell' data-label='Previous Treatment Plan ID' headers='plan-roster-previous-id'>{item.previousTreatmentPlanId || 'Initial plan'}</td>
                <td role='cell' data-label='Initial Treatment Plan' headers='plan-roster-initial'>{`(#${item.initialTreatmentPlanId}) ${formatDateTime24Hour(item.initialTreatmentPlanDate)}`}</td>
              </tr>
              </Fragment>
            ))}
            {worklistRows.length === 0 && <tr role='row'><td role='cell' colSpan={9} className='muted'>No treatment plans match the current worklist and filters.</td></tr>}
          </tbody>
        </table>
        {isLoading && <p className='muted'>Loading treatment plans roster...</p>}
        {worklistRows.length > pageSize && <nav className='button-row' aria-label='Treatment plan roster pages'>
          <button type='button' disabled={page === 0} onClick={() => setPage((value) => value - 1)}>Previous</button>
          <span>Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, worklistRows.length)} of {worklistRows.length}</span>
          <button type='button' disabled={(page + 1) * pageSize >= worklistRows.length} onClick={() => setPage((value) => value + 1)}>Next</button>
        </nav>}
      </section>}
    </div>
  )
}
