import { useEffect, useState } from 'react'
import { getApiConfiguration, getApprovedAllevaTreatmentPlanSyncJob, getSettings, runApprovedAllevaTreatmentPlanSync, saveApiConfiguration, saveSettings } from '../api/client'
import { pullOpenApiDefinition } from '../api/openapiClient'
import { testSavedOAuthConnectivity } from '../api/connectivityClient'
import { cancelApiHarnessJob } from '../api/jobs'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, ApiHarnessJob, AppSettings } from '../api/types'

type SettingsPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load settings.'
}

export function SettingsPage({ token }: SettingsPageProps) {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [clientSecret, setClientSecret] = useState('')
  const [message, setMessage] = useState('')
  const [definitionSummary, setDefinitionSummary] = useState('')
  const [isPullingDefinition, setIsPullingDefinition] = useState(false)
  const [isTestingConnectivity, setIsTestingConnectivity] = useState(false)
  const [isRunningSync, setIsRunningSync] = useState(false)
  const [syncJob, setSyncJob] = useState<ApiHarnessJob | null>(null)
  const [connectivityStatus, setConnectivityStatus] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadSettings() {
      try {
        const [loadedSettings, loadedApiConfig] = await Promise.all([getSettings(token), getApiConfiguration(token)])
        if (!cancelled) {
          setSettings(loadedSettings)
          setApiConfig(loadedApiConfig)
        }
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      }
    }
    void loadSettings()
    return () => {
      cancelled = true
    }
  }, [token])

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (!settings || !apiConfig) return <section className='panel muted'>Loading settings...</section>

  async function handleSaveSettings() {
    if (!settings) return
    setSettings(await saveSettings(token, settings))
    setMessage('Settings saved.')
  }

  async function handleSaveApiConfiguration() {
    if (!apiConfig) return
    setApiConfig(await saveApiConfiguration(token, apiConfig, clientSecret))
    setClientSecret('')
    setMessage('API configuration saved; client secret configured.')
  }

  async function handlePullDefinition() {
    setIsPullingDefinition(true)
    setMessage('')
    try {
      const summary = await pullOpenApiDefinition(token)
      setDefinitionSummary(`${summary.title}: ${summary.operationCount} operations available.`)
    } catch (pullError) {
      setMessage(messageForError(pullError))
    } finally {
      setIsPullingDefinition(false)
    }
  }

  async function handleTestConnectivity() {
    setIsTestingConnectivity(true)
    setMessage('')
    try {
      const result = await testSavedOAuthConnectivity(token)
      setConnectivityStatus(result.message)
    } catch (connectivityError) {
      setMessage(messageForError(connectivityError))
    } finally {
      setIsTestingConnectivity(false)
    }
  }

  const syncReady = apiConfig.apiEnabled
    && apiConfig.treatmentPlanSyncEnabled
    && apiConfig.clientSecretConfigured
    && Boolean(apiConfig.activeContractVersion)
  const syncActive = syncJob !== null && !isTerminalSyncStatus(syncJob.status)

  async function handleRunSync() {
    setIsRunningSync(true)
    setMessage('')
    setSyncJob(null)
    try {
      const started = await runApprovedAllevaTreatmentPlanSync(token)
      setSyncJob(started)
      const completed = await pollSyncJob(started)
      setSyncJob(completed)
      if (isTerminalSyncStatus(completed.status)) {
        setMessage(`Treatment-plan sync ${completed.status}: ${completed.recordsWritten} imported, ${completed.recordsFailed} skipped.`)
      } else {
        setMessage('Treatment-plan sync is still running. Cancel it if you need to stop the approved read-only import.')
      }
    } catch (syncError) {
      setMessage(messageForError(syncError))
    } finally {
      setIsRunningSync(false)
    }
  }

  async function handleCancelSync() {
    if (!syncJob) return
    try {
      setSyncJob(await cancelApiHarnessJob(token, syncJob.jobId))
      setMessage('Treatment-plan sync cancellation requested.')
    } catch (cancelError) {
      setMessage(messageForError(cancelError))
    }
  }

  async function pollSyncJob(started: ApiHarnessJob): Promise<ApiHarnessJob> {
    let current = started
    for (let attempt = 0; attempt < 240 && !isTerminalSyncStatus(current.status); attempt += 1) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, 250))
      current = await getApprovedAllevaTreatmentPlanSyncJob(token, current.jobId)
      setSyncJob(current)
    }
    return current
  }

  return (
    <div className='page-grid'>
      <section className='panel settings-form'>
        <p className='eyebrow'>Settings</p>
        <h2>Local V2 controls</h2>
        <div className='warning-band'>
          LOC-change update window remains unvalidated by R3/Marleigh. Keep this configurable until the blocker is resolved.
        </div>
        <label>
          Organization
          <input value={settings.organizationName} onChange={(event) => setSettings({ ...settings, organizationName: event.target.value })} />
        </label>
        <label>
          Facility timezone
          <input value={settings.facilityTimezone} onChange={(event) => setSettings({ ...settings, facilityTimezone: event.target.value })} />
        </label>
        <label>
          LOC-change window days
          <input
            type='number'
            value={settings.treatmentPlanLocChangeWindowDays ?? ''}
            onChange={(event) => setSettings({ ...settings, treatmentPlanLocChangeWindowDays: Number(event.target.value) })}
          />
        </label>
        <label className='checkbox-row'>
          <input
            type='checkbox'
            checked={settings.treatmentPlanLocChangeWindowValidated}
            onChange={(event) => setSettings({ ...settings, treatmentPlanLocChangeWindowValidated: event.target.checked })}
          />
          LOC-change window validated
        </label>
        <button type='button' onClick={handleSaveSettings}>Save settings</button>
      </section>

      <section className='panel settings-form'>
        <p className='eyebrow'>API Configuration</p>
        <h2>Alleva readiness profile</h2>
        <label>
          Vendor
          <input value={apiConfig.vendorName} onChange={(event) => setApiConfig({ ...apiConfig, vendorName: event.target.value })} />
        </label>
        <label>
          API base URL
          <input value={apiConfig.apiBaseUrl} onChange={(event) => setApiConfig({ ...apiConfig, apiBaseUrl: event.target.value })} />
        </label>
        <label>
          OpenAPI URL
          <input value={apiConfig.openapiUrl} onChange={(event) => setApiConfig({ ...apiConfig, openapiUrl: event.target.value })} />
        </label>
        <label>
          OAuth token URL
          <input value={apiConfig.tokenUrl} onChange={(event) => setApiConfig({ ...apiConfig, tokenUrl: event.target.value })} />
        </label>
        <label>
          Client ID
          <input value={apiConfig.clientId} onChange={(event) => setApiConfig({ ...apiConfig, clientId: event.target.value })} />
        </label>
        <label>
          Client secret
          <input value={clientSecret} type='password' autoComplete='new-password' onChange={(event) => setClientSecret(event.target.value)} />
        </label>
        <label>
          OAuth auth style
          <select value={apiConfig.tokenAuthStyle} onChange={(event) => setApiConfig({ ...apiConfig, tokenAuthStyle: event.target.value })}>
            <option value='body'>Credentials in request body</option>
            <option value='basic'>HTTP Basic</option>
          </select>
        </label>
        <label>
          OAuth scopes
          <input value={apiConfig.scopes} onChange={(event) => setApiConfig({ ...apiConfig, scopes: event.target.value })} />
        </label>
        <label>
          Request timeout seconds
          <input type='number' min='1' max='60' value={apiConfig.timeoutSeconds} onChange={(event) => setApiConfig({ ...apiConfig, timeoutSeconds: Number(event.target.value) })} />
        </label>
        <label>
          API pagination limit
          <input type='number' min='1' max='5000' value={apiConfig.paginationLimit} onChange={(event) => setApiConfig({ ...apiConfig, paginationLimit: Number(event.target.value) })} />
        </label>
        <label>
          Treatment-plan sync limit
          <input type='number' min='1' max='5000' value={apiConfig.syncLimit} onChange={(event) => setApiConfig({ ...apiConfig, syncLimit: Number(event.target.value) })} />
        </label>
        <label className='checkbox-row'>
          <input type='checkbox' checked={apiConfig.apiEnabled} onChange={(event) => setApiConfig({ ...apiConfig, apiEnabled: event.target.checked })} />
          Enable API testing
        </label>
        <label className='checkbox-row'>
          <input type='checkbox' checked={apiConfig.treatmentPlanSyncEnabled} onChange={(event) => setApiConfig({ ...apiConfig, treatmentPlanSyncEnabled: event.target.checked })} />
          Enable treatment-plan sync
        </label>
        <label className='checkbox-row'>
          <input type='checkbox' checked={apiConfig.treatmentPlanSyncApproved} onChange={(event) => setApiConfig({ ...apiConfig, treatmentPlanSyncApproved: event.target.checked })} />
          Sync intent recorded (does not authorize execution)
        </label>
        <label className='checkbox-row'>
          <input type='checkbox' checked={apiConfig.treatmentPlanEndpointMappingValidated} onChange={(event) => setApiConfig({ ...apiConfig, treatmentPlanEndpointMappingValidated: event.target.checked })} />
          Mapping intent recorded (does not authorize execution)
        </label>
        <dl className='summary-grid'>
          <div><dt>API key</dt><dd>{apiConfig.apiKeyConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>Client secret</dt><dd>{apiConfig.clientSecretConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>API testing</dt><dd>{apiConfig.apiEnabled ? 'enabled' : 'disabled'}</dd></div>
          <div><dt>Approved contract</dt><dd>{apiConfig.activeContractVersion || 'not recorded'}</dd></div>
          <div><dt>Approved sync</dt><dd>{syncReady ? 'ready to run' : 'gated'}</dd></div>
        </dl>
        <p className='muted'>A versioned contract with all six endpoint mappings, OAuth, pagination, rate-limit, attachment, vendor-documentation, test-population, approver, and effective-date evidence is required. These checkboxes are intent only.</p>
        <button type='button' onClick={handleSaveApiConfiguration}>Save API configuration</button>
        <button type='button' className='secondary-button' onClick={handlePullDefinition} disabled={isPullingDefinition}>
          {isPullingDefinition ? 'Pulling OpenAPI definition...' : 'Pull OpenAPI definition'}
        </button>
        <button type='button' className='secondary-button' onClick={handleTestConnectivity} disabled={isTestingConnectivity}>
          {isTestingConnectivity ? 'Testing OAuth connectivity...' : 'Test saved OAuth connectivity'}
        </button>
        <button type='button' className='secondary-button' onClick={handleRunSync} disabled={!syncReady || isRunningSync || syncActive} title={syncReady ? 'Run approved read-only treatment-plan sync' : 'A saved encrypted secret, explicit enablement, and an effective versioned approval contract are required before sync can run.'}>
          {isRunningSync ? 'Running treatment-plan sync...' : 'Run approved treatment-plan sync'}
        </button>
        {syncJob && !isTerminalSyncStatus(syncJob.status) && (
          <button type='button' className='secondary-button' onClick={handleCancelSync}>
            Cancel treatment-plan sync
          </button>
        )}
        {definitionSummary && <p role='status'>{definitionSummary}</p>}
        {connectivityStatus && <p role='status'>{connectivityStatus}</p>}
        {message && <p role='status'>{message}</p>}
      </section>
    </div>
  )
}

function isTerminalSyncStatus(status: string): boolean {
  return ['completed', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}
