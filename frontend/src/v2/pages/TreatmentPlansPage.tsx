import { useEffect, useMemo, useState } from 'react'
import { getTreatmentPlanDetail, getTreatmentPlans, saveManagerAction } from '../api/client'
import { deleteTreatmentPlanSourceDocument, downloadTreatmentPlanSourceDocument } from '../api/downloads'
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
  const statusOrder = listData?.statusOrder.length ? listData.statusOrder : defaultStatusOrder
  const selectedSummary = useMemo(
    () => listData?.items.find((item) => item.patientId === selectedPatientId) ?? listData?.items[0] ?? null,
    [listData, selectedPatientId],
  )

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
  }, [token])

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
          Evaluation date
          <input type='date' defaultValue='2026-07-08' />
        </label>
        <label>
          Search
          <input placeholder='Patient ID or status' />
        </label>
        <button type='button' onClick={() => setSelectedPatientId(listData.items[0]?.patientId ?? '')}>Refresh</button>
        <button type='button' className='secondary-button' disabled>Manual upload sync pending</button>
      </section>
      <section className='status-strip' aria-label='Treatment Plans status strip'>
        {statusOrder.map((status) => (
          <button key={status} type='button' className='status-segment'>
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
              {listData.items.map((item) => (
                <tr key={item.patientId}>
                  <td data-label='Patient'><button type='button' className='link-button' onClick={() => setSelectedPatientId(item.patientId)}>{item.patientDisplayLabel}</button></td>
                  <td data-label='LOC'>{item.currentLevelOfCare}</td>
                  <td data-label='Next due'>{item.nextDueDate}</td>
                  <td data-label='Status'><StatusBadge status={item.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
        {isLoadingDetail && <section className='panel muted'>Loading selected treatment-plan detail...</section>}
        {!isLoadingDetail && selectedPlan && (
          <TreatmentPlanDetailViewer
            plan={selectedPlan}
            canManage={user.role === 'admin' || user.role === 'office_manager'}
            onManagerAction={handleManagerAction}
            onDownloadSourceDocument={handleSourceDocumentDownload}
            onDeleteSourceDocument={handleSourceDocumentDelete}
          />
        )}
        {!isLoadingDetail && !selectedPlan && <section className='panel muted'>No treatment plans returned.</section>}
      </section>
    </div>
  )
}
