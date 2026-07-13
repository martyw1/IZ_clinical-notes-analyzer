import { useState } from 'react'
import { approvePublishedAllevaV1Contract } from '../api/contractClient'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration } from '../api/types'

type Props = {
  readonly config: ApiConfiguration | null
  readonly token: string
  readonly onApproved: (contractVersion: string) => void
}

export function ApprovedContractSetupCard({ config, token, onApproved }: Props) {
  const [contractVersion, setContractVersion] = useState(`alleva-rest-v1-${new Date().toISOString().slice(0, 10)}`)
  const [testPopulationReference, setTestPopulationReference] = useState('')
  const [maximumRequestsPerMinute, setMaximumRequestsPerMinute] = useState(0)
  const [confirmed, setConfirmed] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')

  if (!config) return <section className='panel muted'>Loading approved-mapping status...</section>
  if (config.activeContractVersion) {
    return (
      <section className='panel' aria-label='Alleva import mapping setup'>
        <p className='eyebrow'>Approved import mapping</p>
        <h2>Alleva v1 mapping is active</h2>
        <p>Contract <strong>{config.activeContractVersion}</strong> binds the saved OAuth profile to the approved endpoint and field mappings.</p>
      </section>
    )
  }

  const prerequisitesReady = config.clientSecretConfigured
    && config.apiEnabled
    && config.treatmentPlanSyncEnabled
    && config.treatmentPlanSyncApproved
    && config.treatmentPlanEndpointMappingValidated
  const canSubmit = prerequisitesReady
    && contractVersion.trim().length > 0
    && testPopulationReference.trim().length > 0
    && maximumRequestsPerMinute > 0
    && confirmed
    && !isSaving

  async function recordContract() {
    if (!config || !canSubmit) return
    setIsSaving(true)
    setMessage('')
    try {
      const result = await approvePublishedAllevaV1Contract(token, config, {
        contractVersion,
        testPopulationReference,
        maximumRequestsPerMinute,
        retryAfterSeconds: 2,
      })
      setMessage(`Approved mapping ${result.contractVersion} recorded.`)
      onApproved(result.contractVersion)
    } catch (error) {
      setMessage(error instanceof ApiRequestError || error instanceof Error
        ? error.message
        : 'Unable to record the approved Alleva mapping.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className='panel' aria-label='Alleva import mapping setup'>
      <p className='eyebrow'>One-time operational approval</p>
      <h2>Approve the published Alleva v1 import mapping</h2>
      <p>Your client ID and secret authenticate the app. This step separately records which published endpoints and fields may populate the local patient roster and Treatment Plans queue.</p>
      <p className='muted'>Template: <code>/clients</code>, <code>/treatment-plans</code>, plan detail, diagnosis, and treatment-review endpoints from the saved v1 OpenAPI definition. Patient names and attachment bodies are not imported.</p>
      {!prerequisitesReady && <p className='error-banner'>Save the secret and enable all four API/sync approval controls in Settings before recording this mapping.</p>}
      <div className='form-grid'>
        <label>
          Mapping version
          <input value={contractVersion} onChange={(event) => setContractVersion(event.target.value)} />
        </label>
        <label>
          Non-PHI test population reference
          <input value={testPopulationReference} onChange={(event) => setTestPopulationReference(event.target.value)} placeholder='Alleva sandbox cohort validated YYYY-MM-DD' />
        </label>
        <label>
          Vendor-approved maximum requests per minute
          <input type='number' min='1' max='10000' value={maximumRequestsPerMinute || ''} onChange={(event) => setMaximumRequestsPerMinute(Number(event.target.value))} />
        </label>
      </div>
      <label className='checkbox-row'>
        <input type='checkbox' checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
        I confirm this endpoint mapping, pagination, rate limit, and non-PHI test population were validated for R3's Alleva tenant.
      </label>
      <button type='button' onClick={() => void recordContract()} disabled={!canSubmit}>
        {isSaving ? 'Recording approved mapping...' : 'Record approved Alleva v1 mapping'}
      </button>
      {message && <p role='status'>{message}</p>}
    </section>
  )
}
