import { useEffect, useMemo, useState } from 'react'
import { getTreatmentPlanDetail, getTreatmentPlans, saveManagerAction } from '../api/client'
import { deleteTreatmentPlanSourceDocument, downloadChecklistEvidenceExport, downloadTreatmentPlanSourceDocument } from '../api/downloads'
import { ApiRequestError } from '../api/json'
import type { ManagerActionPayload, TreatmentPlanListData, TreatmentPlanListItem, UserProfile } from '../api/types'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import { StatusBadge } from '../components/StatusBadge'
import type { TreatmentPlanAggregate, TreatmentPlanStatus } from '../types/treatmentPlan'
import { statusOrder as defaultStatusOrder } from '../types/treatmentPlan'

type TreatmentPlansPageProps = {
  readonly token: string
  readonly user: UserProfile
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load treatment-plan data.'
}

function countStatus(items: readonly TreatmentPlanListItem[], status: TreatmentPlanStatus): number {
  return items.filter((item) => item.status === status).length
}

export function TreatmentPlansPage({ token, user }: TreatmentPlansPageProps) {
  const [listData, setListData] = useState<TreatmentPlanListData | null>(null)
  const [selectedPatientId, setSelectedPatientId] = useState('')
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
      && (!normalizedQuery || item.patientId.toLowerCase().includes(normalizedQuery) || item.status.toLowerCase().includes(normalizedQuery))
    ))
  }, [listData?.items, query, statusFilter])
  const selectedSummary = useMemo(
    () => visibleItems.find((item) => item.patientId === selectedPatientId) ?? visibleItems[0] ?? null,
    [selectedPatientId, visibleItems],
  )

  useEffect(() => {
    if (!selectedSummary) {
      setSelectedPlan(null)
      return
    }
    if (selectedPatientId !== selectedSummary.patientId) setSelectedPatientId(selectedSummary.patientId)
  }, [selectedPatientId, selectedSummary])

  useEffect(() => {
    let cancelled = false
    async function loadList() {
      try {
        const payload = await getTreatmentPlans(token)
        if (cancelled) return
        setListData(payload)
        setSelectedPatientId(payload.items[0]?.patientId ?? '')
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
    if (!selectedSummary) return
    let cancelled = false
    async function loadDetail(summary: TreatmentPlanListItem) {
      setIsLoadingDetail(true)
      try {
        const payload = await getTreatmentPlanDetail(token, summary.patientId)
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
      getTreatmentPlanDetail(token, selectedPlan.patientId),
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
    setSelectedPlan(await getTreatmentPlanDetail(token, selectedPlan.patientId))
  }

  async function handleChecklistEvidenceExport() {
    if (!selectedPlan) return
    await downloadChecklistEvidenceExport(token, selectedPlan.patientId)
  }

  if (error) {
    return <section className='panel error-banner' role='alert'>{error}</section>
  }

  if (!listData) {
    return <section className='panel muted'>Loading treatment-plan queue...</section>
  }

  return (
    <div className='treatment-workbench'>
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
        <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh queue</button>
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
                <th>LOC</th>
                <th>Next due</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => (
                <tr key={item.patientId}>
                  <td data-label='Patient ID'><button type='button' className='link-button' onClick={() => setSelectedPatientId(item.patientId)}>{item.patientId}</button></td>
                  <td data-label='LOC'>{item.currentLevelOfCare}</td>
                  <td data-label='Next due'>{item.nextDueDate}</td>
                  <td data-label='Status'><StatusBadge status={item.status} /></td>
                </tr>
              ))}
              {visibleItems.length === 0 && (
                <tr><td colSpan={4} className='muted'>No treatment plans match the current filters.</td></tr>
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
