import { useEffect, useMemo, useState } from 'react'
import { getTreatmentPlans } from '../api/client'
import { getApiConfiguration } from '../api/settingsClient'
import { downloadTreatmentPlanListExport } from '../api/downloads'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, TreatmentPlanListData, TreatmentPlanListItem, TreatmentPlanSelection, UserProfile } from '../api/types'
import { ApprovedQueueImportCard } from '../components/ApprovedQueueImportCard'
import { TreatmentPlanDetailPage } from './TreatmentPlanDetailPage'
import { SourceFilterControl } from '../components/SourceFilterControl'
import { planIdentityKey, sourceLabel } from '../types/identity'
import type { SourceFilter } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'
import { StatusBadge } from '../components/StatusBadge'
import type { TreatmentPlanStatus } from '../types/treatmentPlan'
import { statusOrder as defaultStatusOrder } from '../types/treatmentPlan'

type TreatmentPlansPageProps = {
  readonly token: string
  readonly isSessionCurrent?: SessionGuard
  readonly user: UserProfile
  readonly onNavigate: (view: string) => void
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load treatment-plan data.'
}

function countStatus(items: readonly TreatmentPlanListItem[], status: TreatmentPlanStatus): number {
  return items.filter((item) => item.status === status).length
}

export function TreatmentPlansPage({ token, user, onNavigate, isSessionCurrent }: TreatmentPlansPageProps) {
  const [listData, setListData] = useState<TreatmentPlanListData | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [apiConfigError, setApiConfigError] = useState('')
  const [selection, setSelection] = useState<TreatmentPlanSelection | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<TreatmentPlanStatus | null>(null)
  const [refreshNumber, setRefreshNumber] = useState(0)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [isExporting, setIsExporting] = useState(false)
  const sourceMode = sourceFilter === 'all' ? undefined : sourceFilter
  const capture = useRequestGeneration(`${token}:${sourceFilter}:${refreshNumber}`, isSessionCurrent)
  const selectedPlanKey = selection ? planIdentityKey(selection) : ''
  const statusOrder = listData?.statusOrder.length ? listData.statusOrder : defaultStatusOrder
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return (listData?.items ?? []).filter((item) => (
      (!sourceMode || item.sourceMode === sourceMode)
      && (!statusFilter || item.status === statusFilter)
      && (!normalizedQuery
        || item.patientId.toLowerCase().includes(normalizedQuery)
        || item.treatmentPlanId.toLowerCase().includes(normalizedQuery)
        || item.fullName.toLowerCase().includes(normalizedQuery)
        || item.originalPlanReference.toLowerCase().includes(normalizedQuery)
        || item.serviceDate.toLowerCase().includes(normalizedQuery)
        || item.status.toLowerCase().includes(normalizedQuery))
    ))
  }, [listData?.items, query, statusFilter, sourceMode])
  useEffect(() => {
    const isCurrent = capture()
    setError('')
    setIsExporting(false)
    async function loadList() {
      try {
        const payload = await getTreatmentPlans(token, { sourceMode })
        if (!isCurrent()) return
        setListData(payload)
      } catch (loadError) {
        if (isCurrent()) setError(messageForError(loadError))
      }
    }
    void loadList()
  }, [refreshNumber, token, sourceMode, capture, isSessionCurrent])

  useEffect(() => {
    if (user.role !== 'admin') return
    let cancelled = false
    void getApiConfiguration(token).then((config) => {
      if (!cancelled) setApiConfig(config)
    }).catch((loadError: unknown) => {
      if (!cancelled) setApiConfigError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [token, user.role])

  async function handleTreatmentPlanListExport() {
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

  if (error) {
    return <section className='panel error-banner' role='alert'>{error}</section>
  }

  if (!listData) {
    return <section className='panel muted'>Loading treatment-plan queue...</section>
  }

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
      {apiConfigError && <p role='alert' className='error-banner'>{apiConfigError}</p>}
      <section className='sticky-toolbar'>
        <div>
          <p className='eyebrow'>Operational review queue</p>
          <h2>Treatment Plan Workbench</h2>
          <p className='muted'>Focused V2 review · Signed in as {user.fullName}</p>
        </div>
        <label>
          Search MRN, patient name, plan ID, original reference, or status
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='Patient ID or status' />
        </label>
        <SourceFilterControl value={sourceFilter} onChange={setSourceFilter} />
        <div className='button-row'>
          {(user.role === 'admin' || user.role === 'office_manager') && (
            <button type='button' className='secondary-button' onClick={() => void handleTreatmentPlanListExport()} disabled={isExporting}>Export treatment plans and statuses</button>
          )}
          <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh queue</button>
        </div>
      </section>
      <section className='status-strip' aria-label='Treatment Plans status strip'>
        {statusOrder.map((status) => (
          <button key={status} type='button' className='status-segment' aria-pressed={statusFilter === status} onClick={() => setStatusFilter((current) => current === status ? null : status)}>
            <StatusBadge status={status} />
            <span>{countStatus(listData.items, status)}</span>
          </button>
        ))}
      </section>
      <section className='queue-and-detail'>
        <article className='panel queue-panel'>
          <h2>Queue</h2>
          <table>
            <thead>
              <tr>
                <th>Patient</th>
                <th>Treatment plan ID</th>
                <th>Source</th>
                <th>LOC</th>
                <th>Next due</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => (
                <tr key={planIdentityKey(item)} data-plan-version-id={item.planVersionId} data-patient-record-id={item.patientRecordId} data-source-mode={item.sourceMode}>
                  <td data-label='Patient ID'>{item.patientId}<span className='patient-name-secondary'>{item.fullName || 'Name unavailable'}</span></td>
                  <td data-label='Treatment plan ID'>
                    <button
                      type='button'
                      className='link-button'
                      aria-pressed={selectedPlanKey === planIdentityKey(item)}
                      onClick={() => setSelection({ ...item, mrn: item.patientId, patientKey: item.patientId })}
                    >
                      <span>{item.treatmentPlanId}</span>
                      {selectedPlanKey === planIdentityKey(item) && <span className='selected-label'>Selected</span>}
                    </button>
                  </td>
                  <td data-label='Source'>{sourceLabel(item.sourceMode)} · record {item.patientRecordId} · version {item.versionOrdinal} (#{item.planVersionId})<br />Reference: {item.originalPlanReference || 'Not supplied'}<br />Service date: {item.serviceDate ? formatDateTime24Hour(item.serviceDate) : 'Not supplied'}</td>
                  <td data-label='LOC'>{item.currentLevelOfCare}</td>
                  <td data-label='Next due'>{item.nextDueDate}</td>
                  <td data-label='Status'><StatusBadge status={item.status} /></td>
                </tr>
              ))}
              {visibleItems.length === 0 && (
                <tr><td colSpan={6} className='muted'>No treatment plans match the current filters.</td></tr>
              )}
            </tbody>
          </table>
        </article>
        <TreatmentPlanDetailPage token={token} user={user} selection={selection} onNavigate={onNavigate} onSelectTreatmentPlan={setSelection} isSessionCurrent={isSessionCurrent} />
      </section>
    </div>
  )
}
