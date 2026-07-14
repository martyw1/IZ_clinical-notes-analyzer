import { useEffect, useMemo, useState } from 'react'
import { getApiConfiguration, getTreatmentPlanDetail, getTreatmentPlans, saveManagerAction } from '../api/client'
import { deleteTreatmentPlanSourceDocument, downloadChecklistEvidenceExport, downloadTreatmentPlanListExport, downloadTreatmentPlanSourceDocument } from '../api/downloads'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, ManagerActionPayload, TreatmentPlanListData, TreatmentPlanListItem, UserProfile } from '../api/types'
import { ApprovedQueueImportCard } from '../components/ApprovedQueueImportCard'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import { StatusBadge } from '../components/StatusBadge'
import type { TreatmentPlanAggregate, TreatmentPlanStatus } from '../types/treatmentPlan'
import { statusOrder as defaultStatusOrder } from '../types/treatmentPlan'

type TreatmentPlansPageProps = {
  readonly token: string
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

export function TreatmentPlansPage({ token, user, onNavigate }: TreatmentPlansPageProps) {
  const [listData, setListData] = useState<TreatmentPlanListData | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [apiConfigError, setApiConfigError] = useState('')
  const [selectedPlanKey, setSelectedPlanKey] = useState('')
  const [selectedPlan, setSelectedPlan] = useState<TreatmentPlanAggregate | null>(null)
  const [error, setError] = useState('')
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<TreatmentPlanStatus | null>(null)
  const [refreshNumber, setRefreshNumber] = useState(0)
  const statusOrder = listData?.statusOrder.length ? listData.statusOrder : defaultStatusOrder
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return (listData?.items ?? []).filter((item) => (
      (!statusFilter || item.status === statusFilter)
      && (!normalizedQuery
        || item.patientId.toLowerCase().includes(normalizedQuery)
        || item.treatmentPlanId.toLowerCase().includes(normalizedQuery)
        || item.status.toLowerCase().includes(normalizedQuery))
    ))
  }, [listData?.items, query, statusFilter])
  const selectedSummary = useMemo(
    () => visibleItems.find((item) => planKey(item) === selectedPlanKey) ?? visibleItems[0] ?? null,
    [selectedPlanKey, visibleItems],
  )

  useEffect(() => {
    if (!selectedSummary) {
      setSelectedPlan(null)
      return
    }
    const nextKey = planKey(selectedSummary)
    if (selectedPlanKey !== nextKey) setSelectedPlanKey(nextKey)
  }, [selectedPlanKey, selectedSummary])

  useEffect(() => {
    let cancelled = false
    async function loadList() {
      try {
        const payload = await getTreatmentPlans(token)
        if (cancelled) return
        setListData(payload)
        setSelectedPlanKey((current) => (
          payload.items.some((item) => planKey(item) === current)
            ? current
            : payload.items[0] ? planKey(payload.items[0]) : ''
        ))
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      }
    }
    void loadList()
    return () => {
      cancelled = true
    }
  }, [refreshNumber, token])

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

  useEffect(() => {
    if (!selectedSummary) return
    let cancelled = false
    async function loadDetail(summary: TreatmentPlanListItem) {
      setIsLoadingDetail(true)
      try {
        const payload = await getTreatmentPlanDetail(token, summary.patientId, summary.treatmentPlanId, summary.sourceMode)
        if (!cancelled) setSelectedPlan(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      } finally {
        if (!cancelled) setIsLoadingDetail(false)
      }
    }
    void loadDetail(selectedSummary)
    return () => {
      cancelled = true
    }
  }, [selectedSummary, token])

  async function handleManagerAction(payload: ManagerActionPayload) {
    if (!selectedPlan) return
    await saveManagerAction(token, selectedPlan.patientId, payload)
    const [detail, queue] = await Promise.all([
      getTreatmentPlanDetail(token, selectedPlan.patientId, selectedSummary?.treatmentPlanId, selectedSummary?.sourceMode),
      getTreatmentPlans(token),
    ])
    setSelectedPlan(detail)
    setListData(queue)
  }

  async function handleSourceDocumentDownload(sourceFileId: string) {
    if (!selectedPlan) return
    await downloadTreatmentPlanSourceDocument(token, selectedPlan.patientId, sourceFileId)
  }

  async function handleSourceDocumentDelete(sourceFileId: string) {
    if (!selectedPlan) return
    await deleteTreatmentPlanSourceDocument(token, selectedPlan.patientId, sourceFileId)
    setSelectedPlan(await getTreatmentPlanDetail(token, selectedPlan.patientId, selectedSummary?.treatmentPlanId, selectedSummary?.sourceMode))
  }

  async function handleChecklistEvidenceExport() {
    if (!selectedPlan) return
    await downloadChecklistEvidenceExport(token, selectedPlan.patientId)
  }

  async function handleTreatmentPlanListExport() {
    try {
      await downloadTreatmentPlanListExport(token)
    } catch (downloadError) {
      setError(messageForError(downloadError))
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
          <p className='eyebrow'>Treatment Plans Workbench</p>
          <h2>Focused V2 treatment-plan review queue</h2>
          <p className='muted'>Signed in as {user.fullName}</p>
        </div>
        <label>
          Search patient ID or status
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='Patient ID or status' />
        </label>
        <div className='button-row'>
          {(user.role === 'admin' || user.role === 'office_manager') && (
            <button type='button' className='secondary-button' onClick={() => void handleTreatmentPlanListExport()}>Export treatment plans and statuses</button>
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
                <tr key={planKey(item)}>
                  <td data-label='Patient ID'>{item.patientId}</td>
                  <td data-label='Treatment plan ID'>
                    <button
                      type='button'
                      className='link-button'
                      aria-pressed={selectedPlanKey === planKey(item)}
                      onClick={() => setSelectedPlanKey(planKey(item))}
                    >
                      <span>{item.treatmentPlanId}</span>
                      {selectedPlanKey === planKey(item) && <span className='selected-label'>Selected</span>}
                    </button>
                  </td>
                  <td data-label='Source'>{item.sourceMode}</td>
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
        {isLoadingDetail && <section className='panel muted'>Loading selected treatment-plan detail...</section>}
        {!isLoadingDetail && selectedPlan && (
          <TreatmentPlanDetailViewer
            plan={selectedPlan}
            canManage={user.role === 'admin' || user.role === 'office_manager'}
            onManagerAction={handleManagerAction}
            onExportChecklistEvidence={handleChecklistEvidenceExport}
            onDownloadSourceDocument={handleSourceDocumentDownload}
            onDeleteSourceDocument={handleSourceDocumentDelete}
          />
        )}
        {!isLoadingDetail && !selectedPlan && <section className='panel muted'>No treatment plans returned.</section>}
      </section>
    </div>
  )
}

function planKey(item: TreatmentPlanListItem): string {
  return `${item.patientId}:${item.sourceMode}:${item.treatmentPlanId}`
}
