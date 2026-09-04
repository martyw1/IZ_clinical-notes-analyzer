import { useEffect, useState } from 'react'
import { getTreatmentPlanDetail, getTreatmentPlans, saveManagerAction } from '../api/client'
import {
  deleteTreatmentPlanSourceDocument,
  downloadChecklistEvidenceExport,
  downloadTreatmentPlanSourceDocument,
} from '../api/downloads'
import { ApiRequestError } from '../api/json'
import type { ManagerActionPayload, TreatmentPlanListItem, TreatmentPlanSelection, UserProfile } from '../api/types'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import type { TreatmentPlanAggregate } from '../types/treatmentPlan'
import { planIdentityKey, sourceLabel } from '../types/identity'
import { useRequestGeneration } from '../hooks/useRequestGeneration'
import type { SessionGuard } from '../hooks/useRequestGeneration'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'

type TreatmentPlanDetailPageProps = {
  readonly token: string
  readonly user: UserProfile
  readonly selection: TreatmentPlanSelection | null
  readonly onNavigate: (view: string) => void
  readonly onSelectTreatmentPlan?: (selection: TreatmentPlanSelection) => void
  readonly isSessionCurrent?: SessionGuard
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load treatment-plan detail.'
}

export function TreatmentPlanDetailPage({ token, user, selection, onNavigate, onSelectTreatmentPlan, isSessionCurrent }: TreatmentPlanDetailPageProps) {
  const [plan, setPlan] = useState<TreatmentPlanAggregate | null>(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [versions, setVersions] = useState<readonly TreatmentPlanListItem[]>([])
  const [versionRefresh, setVersionRefresh] = useState(0)
  const selectionKey = selection ? planIdentityKey(selection) : ''
  const capture = useRequestGeneration(`${token}:${selectionKey}`, isSessionCurrent)

  useEffect(() => {
    if (!selection) {
      setPlan(null)
      setError('')
      return
    }
    const isCurrent = capture()
    setIsLoading(true)
    setPlan(null)
    setError('')
    void loadSelectedPlan(token, selection).then((result) => {
      if (isCurrent()) setPlan(result)
    }).catch((loadError: unknown) => {
      if (isCurrent()) setError(messageForError(loadError))
    }).finally(() => {
      if (isCurrent()) setIsLoading(false)
    })
  }, [selectionKey, token, isSessionCurrent, capture])

  useEffect(() => {
    if (!selection) { setVersions([]); return }
    let cancelled = false
    const isCurrent = capture()
    void getTreatmentPlans(token, { ...selection, includeHistory: true }).then((result) => {
      if (!cancelled && isCurrent()) setVersions(result.items)
    }).catch((loadError: unknown) => {
      if (!cancelled && isCurrent()) setError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [selectionKey, token, isSessionCurrent, capture, versionRefresh])

  async function refreshPlan(): Promise<TreatmentPlanAggregate | null> {
    if (!selection) return null
    const isCurrent = capture()
    const refreshed = await loadSelectedPlan(token, selection)
    if (isCurrent()) setPlan(refreshed)
    return refreshed
  }

  async function handleManagerAction(payload: ManagerActionPayload) {
    if (!selection) return
    const isCurrent = capture()
    if (!isCurrent()) return
    await saveManagerAction(token, selection, payload)
    if (isCurrent()) await refreshPlan()
  }

  async function handleSourceDocumentDownload(sourceFileId: string) {
    if (!selection) return
    await downloadTreatmentPlanSourceDocument(token, { ...selection, isCurrent: capture() }, sourceFileId)
  }

  async function handleSourceDocumentDelete(sourceFileId: string) {
    if (!selection) return
    const isCurrent = capture()
    if (!isCurrent()) return
    await deleteTreatmentPlanSourceDocument(token, selection, sourceFileId)
    if (isCurrent()) await refreshPlan()
  }

  async function handleChecklistEvidenceExport() {
    if (!selection) return
    const isCurrent = capture()
    if (!isCurrent()) return
    try {
      await downloadChecklistEvidenceExport(token, { ...selection, isCurrent })
    } catch (downloadError) {
      if (isCurrent()) setError(messageForError(downloadError))
    }
  }

  if (!selection) {
    return (
      <section className='panel empty-detail-state'>
        <p className='eyebrow'>Treatment Plan Detail</p>
        <h2>Select a treatment plan</h2>
        <p className='muted'>Choose a source-specific plan by MRN from either roster, then select its saved version.</p>
        <div className='button-row'>
          <button type='button' onClick={() => onNavigate('Patient Roster')}>Open Patient Roster</button>
          <button type='button' className='secondary-button' onClick={() => onNavigate('Treatment Plans Roster')}>Open Treatment Plans Roster</button>
        </div>
      </section>
    )
  }

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (isLoading || !plan || planIdentityKey(plan) !== selectionKey) return <section className='panel muted'>Loading selected treatment-plan detail...</section>

  return (
    <>
      <section className='panel'>
        <label>Saved treatment-plan version
          <select aria-label='Saved treatment-plan version' value={String(selection.planVersionId)} onChange={(event) => {
            const version = versions.find((item) => String(item.planVersionId) === event.currentTarget.value)
            if (version) onSelectTreatmentPlan?.({ ...selection, ...version })
          }} disabled={!onSelectTreatmentPlan || versions.length === 0}>
            {!versions.some((version) => version.planVersionId === selection.planVersionId) && <option value={selection.planVersionId}>Selected version #{selection.planVersionId}</option>}
            {versions.map((version) => <option key={version.planVersionId} value={version.planVersionId}>{`${sourceLabel(version.sourceMode)} · record ${version.patientRecordId} · version ${version.versionOrdinal} (#${version.planVersionId})${version.isCurrent ? ' · current' : ' · historical'} · ${formatDateTime24Hour(version.lastUpdated)}`}</option>)}
          </select>
        </label>
        <button type='button' className='secondary-button' onClick={() => setVersionRefresh((value) => value + 1)}>Refresh saved versions</button>
        <p className='muted'>New imports do not change the selected saved version.</p>
      </section>
      <TreatmentPlanDetailViewer
      key={`${token}:${selectionKey}`}
      plan={plan}
      isSessionCurrent={isSessionCurrent}
      canManage={user.role === 'admin' || user.role === 'office_manager'}
      onManagerAction={handleManagerAction}
      onExportChecklistEvidence={handleChecklistEvidenceExport}
      onDownloadSourceDocument={handleSourceDocumentDownload}
      onDeleteSourceDocument={handleSourceDocumentDelete}
    />
    </>
  )
}

function loadSelectedPlan(token: string, selection: TreatmentPlanSelection): Promise<TreatmentPlanAggregate> {
  return getTreatmentPlanDetail(token, selection)
}
