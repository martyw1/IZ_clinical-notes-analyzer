import { useEffect, useState } from 'react'
import { getTreatmentPlanDetail, saveManagerAction } from '../api/client'
import {
  deleteTreatmentPlanSourceDocument,
  downloadChecklistEvidenceExport,
  downloadTreatmentPlanSourceDocument,
} from '../api/downloads'
import { ApiRequestError } from '../api/json'
import type { ManagerActionPayload, TreatmentPlanSelection, UserProfile } from '../api/types'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import type { TreatmentPlanAggregate } from '../types/treatmentPlan'

type TreatmentPlanDetailPageProps = {
  readonly token: string
  readonly user: UserProfile
  readonly selection: TreatmentPlanSelection | null
  readonly onNavigate: (view: string) => void
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load treatment-plan detail.'
}

export function TreatmentPlanDetailPage({ token, user, selection, onNavigate }: TreatmentPlanDetailPageProps) {
  const [plan, setPlan] = useState<TreatmentPlanAggregate | null>(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!selection) {
      setPlan(null)
      setError('')
      return
    }
    let cancelled = false
    setIsLoading(true)
    setError('')
    void loadSelectedPlan(token, selection).then((result) => {
      if (!cancelled) setPlan(result)
    }).catch((loadError: unknown) => {
      if (!cancelled) setError(messageForError(loadError))
    }).finally(() => {
      if (!cancelled) setIsLoading(false)
    })
    return () => { cancelled = true }
  }, [selection, token])

  async function refreshPlan(): Promise<TreatmentPlanAggregate | null> {
    if (!selection) return null
    const refreshed = await loadSelectedPlan(token, selection)
    setPlan(refreshed)
    return refreshed
  }

  async function handleManagerAction(payload: ManagerActionPayload) {
    if (!selection) return
    await saveManagerAction(token, selection.mrn, payload)
    await refreshPlan()
  }

  async function handleSourceDocumentDownload(sourceFileId: string) {
    if (!selection) return
    await downloadTreatmentPlanSourceDocument(token, selection.mrn, sourceFileId)
  }

  async function handleSourceDocumentDelete(sourceFileId: string) {
    if (!selection) return
    await deleteTreatmentPlanSourceDocument(token, selection.mrn, sourceFileId)
    await refreshPlan()
  }

  async function handleChecklistEvidenceExport() {
    if (!selection) return
    await downloadChecklistEvidenceExport(token, selection.mrn)
  }

  if (!selection) {
    return (
      <section className='panel empty-detail-state'>
        <p className='eyebrow'>Treatment Plan Detail</p>
        <h2>Select a treatment plan</h2>
        <p className='muted'>Choose a plan by MRN from the Patient Roster or browse synchronized Alleva records in the Treatment Plans Roster.</p>
        <div className='button-row'>
          <button type='button' onClick={() => onNavigate('Patient Roster')}>Open Patient Roster</button>
          <button type='button' className='secondary-button' onClick={() => onNavigate('Treatment Plans Roster')}>Open Treatment Plans Roster</button>
        </div>
      </section>
    )
  }

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (isLoading || !plan) return <section className='panel muted'>Loading selected treatment-plan detail...</section>

  return (
    <TreatmentPlanDetailViewer
      plan={plan}
      canManage={user.role === 'admin' || user.role === 'office_manager'}
      onManagerAction={handleManagerAction}
      onExportChecklistEvidence={handleChecklistEvidenceExport}
      onDownloadSourceDocument={handleSourceDocumentDownload}
      onDeleteSourceDocument={handleSourceDocumentDelete}
    />
  )
}

function loadSelectedPlan(token: string, selection: TreatmentPlanSelection): Promise<TreatmentPlanAggregate> {
  return getTreatmentPlanDetail(token, selection.mrn, selection.treatmentPlanId, selection.sourceMode)
}
