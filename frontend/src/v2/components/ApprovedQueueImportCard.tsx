import { useState } from 'react'
import { getApprovedAllevaTreatmentPlanSyncJob, runApprovedAllevaTreatmentPlanSync } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, ApiHarnessJob } from '../api/types'

const MISSING_CONTRACT_BLOCKER = 'No approved Alleva v1 mapping is recorded. Complete the one-time mapping setup in the API Testing Harness.'

type Props = {
  readonly config: ApiConfiguration | null
  readonly token: string
  readonly onNavigate: (view: string) => void
  readonly onCompleted?: () => void
  readonly showOpenQueueButton?: boolean
  readonly buttonLabel?: string
}

export function ApprovedQueueImportCard({
  config,
  token,
  onNavigate,
  onCompleted,
  showOpenQueueButton = true,
  buttonLabel = 'Pull, evaluate, and populate queue',
}: Props) {
  const [job, setJob] = useState<ApiHarnessJob | null>(null)
  const [message, setMessage] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const blockers = importBlockers(config)

  async function runImport() {
    let keepLockedForActiveJob = false
    setIsRunning(true)
    setMessage('')
    try {
      let current = await runApprovedAllevaTreatmentPlanSync(token)
      setJob(current)
      for (let attempt = 0; attempt < 5_000 && !isTerminal(current.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 120))
        current = await getApprovedAllevaTreatmentPlanSyncJob(token, current.jobId)
        setJob(current)
      }
      if (current.status === 'completed' || current.status === 'completed_with_warnings') {
        setMessage(current.recordsWritten === 0
          ? 'Queue refreshed. No new or changed treatment plans were written.'
          : `Queue populated and deterministic evaluation completed for ${current.recordsWritten} treatment plan${current.recordsWritten === 1 ? '' : 's'}.`)
        onCompleted?.()
      } else {
        keepLockedForActiveJob = !isTerminal(current.status)
        setMessage(keepLockedForActiveJob
          ? `Queue import is still ${current.status}. This page will not start a second import.`
          : `Queue import ended with status: ${current.status}.`)
      }
    } catch (error) {
      setMessage(error instanceof ApiRequestError || error instanceof Error ? error.message : 'Unable to run the approved queue import.')
    } finally {
      if (!keepLockedForActiveJob) setIsRunning(false)
    }
  }

  return (
    <section className='panel' aria-label='Treatment Plans queue import'>
      <p className='eyebrow'>Operational import</p>
      <h2>Populate and evaluate the Treatment Plans queue</h2>
      {blockers.length > 0 ? (
        <>
          <p className='error-banner'><strong>Queue import is blocked.</strong> Configure and approve the operational import before pulling live records.</p>
          <ul>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          {blockers.some((blocker) => blocker !== MISSING_CONTRACT_BLOCKER) && (
            <button type='button' className='secondary-button' onClick={() => onNavigate('Settings')}>Open Settings</button>
          )}
          {!config?.activeContractVersion && (
            <>
              <p className='muted'>OAuth credentials authenticate the app. The one-time Alleva v1 mapping approval separately selects the patient, treatment-plan, diagnosis, and review fields that may be imported.</p>
              <button type='button' className='secondary-button' onClick={() => onNavigate('API Testing Harness')}>Open Alleva mapping setup</button>
            </>
          )}
        </>
      ) : (
        <p>Approved mapping {config?.activeContractVersion} is active. This import normalizes every returned treatment plan, runs the deterministic checklist, and adds results to the queue.</p>
      )}
      <button type='button' onClick={() => void runImport()} disabled={isRunning || blockers.length > 0}>
        {isRunning ? 'Pulling full treatment plans...' : buttonLabel}
      </button>
      {job && <p>Status: {job.status} | imported: {job.recordsWritten} | failed: {job.recordsFailed}</p>}
      {message && <p role='status'>{message}</p>}
      {showOpenQueueButton && (job?.status === 'completed' || job?.status === 'completed_with_warnings') && (
        <button type='button' className='secondary-button' onClick={() => onNavigate('Treatment Plans')}>Open Treatment Plans queue</button>
      )}
    </section>
  )
}

function importBlockers(config: ApiConfiguration | null): readonly string[] {
  if (!config) return ['Loading saved API and approval status.']
  const blockers: string[] = []
  if (!config.clientSecretConfigured) blockers.push('Save the Alleva client secret in Settings.')
  if (!config.apiEnabled) blockers.push('Enable API testing in Settings.')
  if (!config.treatmentPlanSyncEnabled) blockers.push('Enable treatment-plan sync in Settings.')
  if (!config.treatmentPlanSyncApproved || !config.treatmentPlanEndpointMappingValidated) blockers.push('Record R3/Alleva sync and endpoint-mapping approval in Settings.')
  if (!config.activeContractVersion) blockers.push(MISSING_CONTRACT_BLOCKER)
  return blockers
}

function isTerminal(status: string): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}
