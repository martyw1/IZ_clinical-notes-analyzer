import { useEffect, useState } from 'react'
import { getApprovedAllevaTreatmentPlanSyncJob, getLatestApprovedAllevaTreatmentPlanSyncJob, resumeApprovedAllevaTreatmentPlanSync, runApprovedAllevaTreatmentPlanSync } from '../api/allevaJobsClient'
import { approvedImportBlockers } from '../api/apiReadiness'
import { getApiConfiguration, getSettings, saveApiConfiguration, saveSettings } from '../api/settingsClient'
import { pullOpenApiDefinition } from '../api/openapiClient'
import { testSavedOAuthConnectivity } from '../api/connectivityClient'
import { cancelApiHarnessJob } from '../api/jobs'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, ApiHarnessJob, AppSettings } from '../api/types'
import { JobStatusPanel } from '../components/JobStatusPanel'

type SettingsPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.status >= 500
    ? 'The local service could not complete the request. Restart the app and try again.'
    : error.message
  if (error instanceof Error) return error.message
  return 'Unable to load settings.'
}

export function SettingsPage({ token }: SettingsPageProps) {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [message, setMessage] = useState('')
  const [definitionSummary, setDefinitionSummary] = useState('')
  const [isPullingDefinition, setIsPullingDefinition] = useState(false)
  const [isTestingConnectivity, setIsTestingConnectivity] = useState(false)
  const [isSavingApiConfiguration, setIsSavingApiConfiguration] = useState(false)
  const [isRunningSync, setIsRunningSync] = useState(false)
  const [syncJob, setSyncJob] = useState<ApiHarnessJob | null>(null)
  const [connectivityStatus, setConnectivityStatus] = useState('')
  const [apiSaveError, setApiSaveError] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadSettings() {
      try {
        const [loadedSettings, loadedApiConfig, latestSync] = await Promise.all([
          getSettings(token),
          getApiConfiguration(token),
          getLatestApprovedAllevaTreatmentPlanSyncJob(token),
        ])
        if (!cancelled) {
          setSettings(loadedSettings)
          setApiConfig(loadedApiConfig)
          setSyncJob(latestSync)
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
    setIsSavingApiConfiguration(true)
    setApiSaveError('')
    setMessage('')
    try {
      const saved = await saveApiConfiguration(token, apiConfig, clientId, clientSecret)
      setApiConfig(saved)
      setClientId('')
      setClientSecret('')
      setMessage(saved.clientSecretConfigured
        ? 'API configuration saved. The client secret is saved in encrypted local storage and remains hidden.'
        : 'API configuration saved, but a client secret is still required before OAuth testing can run.')
    } catch (saveError) {
      setApiSaveError(messageForError(saveError))
    } finally {
      setIsSavingApiConfiguration(false)
    }
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

  const syncBlockers = approvedImportBlockers(apiConfig)
  const syncReady = syncBlockers.length === 0
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
        setApiConfig(await getApiConfiguration(token))
      } else {
        setMessage('Treatment-plan sync is still running. Cancel it if you need to stop the read-only import.')
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

  async function handleResumeSync() {
    if (!syncJob) return
    setIsRunningSync(true)
    setMessage('')
    try {
      const resumed = await resumeApprovedAllevaTreatmentPlanSync(token, syncJob.jobId)
      setSyncJob(resumed)
      const completed = await pollSyncJob(resumed)
      setSyncJob(completed)
      setMessage(`Treatment-plan sync ${completed.status}: ${completed.recordsWritten} imported, ${completed.recordsFailed} skipped.`)
    } catch (resumeError) {
      setMessage(messageForError(resumeError))
    } finally {
      setIsRunningSync(false)
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
        <div className='button-row settings-actions'>
          <button type='button' onClick={handleSaveSettings}>Save settings</button>
        </div>
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
          <input aria-describedby='client-id-help' value={clientId} autoComplete='off' onChange={(event) => setClientId(event.target.value)} />
          <span id='client-id-help' className='muted'>{apiConfig.clientIdConfigured ? 'A client ID is configured. Enter a new value only to replace it.' : 'Enter the Alleva OAuth client ID.'}</span>
        </label>
        <label>
          Client secret
          <input aria-describedby='client-secret-help' value={clientSecret} type='password' autoComplete='new-password' onChange={(event) => setClientSecret(event.target.value)} />
          <span id='client-secret-help' className='muted'>Enter a new value to replace the saved secret. Leave blank to keep the encrypted secret already stored on this computer.</span>
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
        <label>
          Request ceiling per minute
          <input type='number' min='1' max='10000' value={apiConfig.requestsPerMinute} onChange={(event) => setApiConfig({ ...apiConfig, requestsPerMinute: Number(event.target.value) })} />
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
          Authorize live read-only treatment-plan import for this tenant
        </label>
        <dl className='summary-grid'>
          <div><dt>API key</dt><dd>{apiConfig.apiKeyConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>Client ID</dt><dd>{apiConfig.clientIdConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>Client secret</dt><dd>{apiConfig.clientSecretConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>API testing</dt><dd>{apiConfig.apiEnabled ? 'enabled' : 'disabled'}</dd></div>
          <div><dt>Import mapping</dt><dd>built-in Alleva v1</dd></div>
          <div><dt>Treatment-plan sync</dt><dd>{syncReady ? 'ready to run' : 'not ready'}</dd></div>
        </dl>
        <p className='muted'>The published Alleva v1 patient and treatment-plan mapping is applied automatically at pull time. The request ceiling is an application throttle and can be lowered to match Alleva tenant guidance. The internal version and checksum are retained for audit provenance.</p>
        <div className='button-row settings-actions'>
          <button type='button' onClick={handleSaveApiConfiguration} disabled={isSavingApiConfiguration}>
            {isSavingApiConfiguration ? 'Saving API configuration...' : 'Save API configuration'}
          </button>
          <button type='button' className='secondary-button' onClick={handlePullDefinition} disabled={isPullingDefinition}>
            {isPullingDefinition ? 'Pulling OpenAPI definition...' : 'Pull OpenAPI definition'}
          </button>
          <button type='button' className='secondary-button' onClick={handleTestConnectivity} disabled={isTestingConnectivity}>
            {isTestingConnectivity ? 'Testing OAuth connectivity...' : 'Test saved OAuth connectivity'}
          </button>
          <button type='button' className='secondary-button' onClick={handleRunSync} disabled={!syncReady || isRunningSync || syncActive} title={syncReady ? 'Run read-only treatment-plan sync' : 'A client ID, saved encrypted secret, API and sync enablement, and explicit tenant import authorization are required before sync can run.'}>
            {isRunningSync ? 'Running treatment-plan sync...' : 'Run treatment-plan sync'}
          </button>
        </div>
        {syncBlockers.length > 0 && <ul className='preflight-blockers' aria-label='Treatment-plan sync requirements'>{syncBlockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
        {(syncJob && !isTerminalSyncStatus(syncJob.status)) || (syncJob && ['failed', 'cancelled', 'stale_or_interrupted'].includes(syncJob.status)) ? <div className='button-row settings-actions'>
          {syncJob && !isTerminalSyncStatus(syncJob.status) && (
            <button type='button' className='secondary-button' onClick={handleCancelSync}>
              Cancel treatment-plan sync
            </button>
          )}
          {syncJob && ['failed', 'cancelled', 'stale_or_interrupted'].includes(syncJob.status) && (
            <button type='button' className='secondary-button' onClick={handleResumeSync} disabled={isRunningSync}>
              Resume treatment-plan sync safely
            </button>
          )}
        </div> : null}
        {definitionSummary && <p role='status'>{definitionSummary}</p>}
        {connectivityStatus && <p role='status'>{connectivityStatus}</p>}
        {apiSaveError && <p role='alert' className='error-banner'>{apiSaveError}</p>}
        <JobStatusPanel job={syncJob} isActive={isRunningSync || syncActive} message={message} error='' onRetry={syncReady ? () => void handleRunSync() : undefined} />
      </section>
    </div>
  )
}

function isTerminalSyncStatus(status: string): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}
