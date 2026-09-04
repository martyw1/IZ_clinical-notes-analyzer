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

type TreatmentPlansRosterPageProps = {
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
  user,
  onNavigate,
  onSelectPatient,
  onSelectTreatmentPlan,
  isSessionCurrent,
}: TreatmentPlansRosterPageProps) {
  const [roster, setRoster] = useState<TreatmentPlanRosterData | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [isExporting, setIsExporting] = useState(false)
  const sourceMode = sourceFilter === 'all' ? undefined : sourceFilter
  const capture = useRequestGeneration(`${token}:${sourceFilter}:${refreshNumber}`, isSessionCurrent)
  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return (roster?.items ?? []).filter((item) => (
      (!sourceMode || item.sourceMode === sourceMode) && (!normalized
      || item.mrn.toLowerCase().includes(normalized)
      || item.fullName.toLowerCase().includes(normalized)
      || item.treatmentPlanId.toLowerCase().includes(normalized)
      || item.originalPlanReference.toLowerCase().includes(normalized)
      || item.serviceDate.toLowerCase().includes(normalized)
      || item.previousTreatmentPlanId.toLowerCase().includes(normalized)
      || item.initialTreatmentPlanId.toLowerCase().includes(normalized)
      || (!item.linkedToMrn && 'not linked to an mrn'.includes(normalized)))
    ))
  }, [query, roster?.items, sourceMode])

  useEffect(() => {
    const isCurrent = capture()
    setRoster(null)
    setError('')
    setIsExporting(false)
    void getTreatmentPlanRoster(token, sourceMode).then((result) => {
      if (isCurrent()) setRoster(result)
    }).catch((loadError: unknown) => {
      if (isCurrent()) setError(messageForError(loadError))
    })
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
      await downloadTreatmentPlanListExport(token, { planVersionIds: visibleItems.map((item) => item.planVersionId), sourceMode, isCurrent })
    } catch (downloadError) {
      if (isCurrent()) setError(messageForError(downloadError))
    } finally {
      if (isCurrent()) setIsExporting(false)
    }
  }

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (!roster) return <section className='panel muted'>Loading treatment plans roster...</section>

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
      <section className='panel table-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Source-aware treatment plans</p>
            <h2>Treatment Plans Roster</h2>
            <p className='muted'>CSV exports all {visibleItems.length} filtered results, including rows outside the current viewport. Names and search text are excluded.</p>
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
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='MRN, patient name, or treatment plan ID' />
        </label>
        <SourceFilterControl value={sourceFilter} onChange={setSourceFilter} />
        <table>
          <thead>
            <tr role='row'>
              <th id='plan-roster-id' role='columnheader'>Treatment Plan ID</th>
              <th id='plan-roster-mrn' role='columnheader'>MRN</th>
              <th id='plan-roster-last-updated' role='columnheader'>Last Updated</th>
              <th id='plan-roster-previous-id' role='columnheader'>Previous Treatment Plan ID</th>
              <th id='plan-roster-initial' role='columnheader'>Initial Treatment Plan</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={item.planVersionId} role='row' data-plan-version-id={item.planVersionId} data-patient-record-id={item.patientRecordId} data-source-mode={item.sourceMode}>
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
                  <div>Service date: {item.serviceDate || 'Not supplied'}</div>
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
                <td role='cell' data-label='Last Updated' headers='plan-roster-last-updated'><time dateTime={item.lastUpdated}>{formatDateTime24Hour(item.lastUpdated)}</time></td>
                <td role='cell' data-label='Previous Treatment Plan ID' headers='plan-roster-previous-id'>{item.previousTreatmentPlanId || 'Initial plan'}</td>
                <td role='cell' data-label='Initial Treatment Plan' headers='plan-roster-initial'>{`(#${item.initialTreatmentPlanId}) ${item.initialTreatmentPlanDate}`}</td>
              </tr>
            ))}
            {visibleItems.length === 0 && <tr role='row'><td role='cell' colSpan={5} className='muted'>No treatment plans match the current source and search filters.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}
