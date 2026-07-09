import { useEffect, useState } from 'react'
import { getApiConfiguration, getSettings, saveApiConfiguration, saveSettings } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, AppSettings } from '../api/types'

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
          Client ID
          <input value={apiConfig.clientId} onChange={(event) => setApiConfig({ ...apiConfig, clientId: event.target.value })} />
        </label>
        <label>
          Client secret
          <input value={clientSecret} type='password' autoComplete='new-password' onChange={(event) => setClientSecret(event.target.value)} />
        </label>
        <dl className='summary-grid'>
          <div><dt>API key</dt><dd>{apiConfig.apiKeyConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>Client secret</dt><dd>{apiConfig.clientSecretConfigured ? 'configured' : 'not configured'}</dd></div>
          <div><dt>Live sync</dt><dd>{apiConfig.apiEnabled ? 'enabled for testing' : 'disabled by default'}</dd></div>
        </dl>
        <button type='button' onClick={handleSaveApiConfiguration}>Save API configuration</button>
        {message && <p role='status'>{message}</p>}
      </section>
    </div>
  )
}
