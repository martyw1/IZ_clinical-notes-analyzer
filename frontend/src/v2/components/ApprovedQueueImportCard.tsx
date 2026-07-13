import { useState } from 'react'
import { getApprovedAllevaTreatmentPlanSyncJob, runApprovedAllevaTreatmentPlanSync } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, ApiHarnessJob } from '../api/types'

type Props = {
  readonly config: ApiConfiguration | null
  readonly token: string
  readonly onNavigate: (view: string) => void
}

export function ApprovedQueueImportCard({ config, token, onNavigate }: Props) {
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
        setMessage(`Queue populated and deterministic evaluation completed for ${current.recordsWritten} treatment plan${current.recordsWritten === 1 ? '' : 's'}.`)
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
          <p className='error-banner'><strong>Queue import is blocked.</strong> The diagnostic pull above can still be used.</p>
          <ul>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          {blockers.some((blocker) => !blocker.startsWith('No approved versioned')) && (
            <button type='button' className='secondary-button' onClick={() => onNavigate('Settings')}>Open Settings</button>
          )}
          {!config?.activeContractVersion && <p className='muted'>A versioned contract is recorded only after R3/Alleva approves the live endpoint mapping. Credentials alone cannot create that approval.</p>}
        </>
      ) : (
        <>
          <p>Approved contract {config?.activeContractVersion} is active. This import normalizes records, runs the deterministic checklist, and adds results to the queue.</p>
          <button type='button' onClick={() => void runImport()} disabled={isRunning}>
            {isRunning ? 'Pulling, evaluating, and populating queue...' : 'Pull, evaluate, and populate queue'}
          </button>
        </>
      )}
      {job && <p>Status: {job.status} | imported: {job.recordsWritten} | failed: {job.recordsFailed}</p>}
      {message && <p role='status'>{message}</p>}
      {(job?.status === 'completed' || job?.status === 'completed_with_warnings') && (
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
  if (!config.activeContractVersion) blockers.push('No approved versioned Alleva contract is recorded. A client ID and secret alone cannot safely map live patient records.')
  return blockers
}

function isTerminal(status: string): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}
