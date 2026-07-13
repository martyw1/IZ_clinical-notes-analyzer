import { useEffect, useState } from 'react'
import { getApiConfiguration } from '../api/client'
import { testSavedOAuthConnectivity } from '../api/connectivityClient'
import { ApiRequestError } from '../api/json'
import { pullOpenApiDefinition } from '../api/openapiClient'
import { testReadOnlyOperation } from '../api/operationClient'
import { JobProgressCard } from '../components/JobProgressCard'
import { ApprovedQueueImportCard } from '../components/ApprovedQueueImportCard'
import { ApprovedContractSetupCard } from '../components/ApprovedContractSetupCard'
import type { ApiConfiguration } from '../api/types'

type ApiHarnessPageProps = {
  readonly token: string
  readonly onNavigate: (view: string) => void
}

export function ApiHarnessPage({ token, onNavigate }: ApiHarnessPageProps) {
  const [config, setConfig] = useState<ApiConfiguration | null>(null)
  const [configError, setConfigError] = useState('')
  const [path, setPath] = useState('/clients')
  const [authenticationMessage, setAuthenticationMessage] = useState('')
  const [definitionMessage, setDefinitionMessage] = useState('')
  const [operationMessage, setOperationMessage] = useState('')
  const [isTestingAuthentication, setIsTestingAuthentication] = useState(false)
  const [isLoadingDefinition, setIsLoadingDefinition] = useState(false)
  const [isTesting, setIsTesting] = useState(false)

  useEffect(() => {
    let cancelled = false
    void getApiConfiguration(token).then((result) => {
      if (!cancelled) setConfig(result)
    }).catch((error: unknown) => {
      if (!cancelled) setConfigError(messageForError(error, 'Unable to load saved API and approval status. Refresh the page to retry.'))
    })
    return () => { cancelled = true }
  }, [token])

  async function testAuthentication() {
    setIsTestingAuthentication(true)
    setAuthenticationMessage('')
    try {
      const result = await testSavedOAuthConnectivity(token)
      setAuthenticationMessage(result.message)
    } catch (error) {
      setAuthenticationMessage(messageForError(error, 'Unable to test saved OAuth credentials.'))
    } finally {
      setIsTestingAuthentication(false)
    }
  }

  async function loadDefinition() {
    setIsLoadingDefinition(true)
    setDefinitionMessage('')
    try {
      const result = await pullOpenApiDefinition(token)
      setDefinitionMessage(`${result.title}: ${result.operationCount} operations available.`)
    } catch (error) {
      setDefinitionMessage(messageForError(error, 'Unable to load the saved OpenAPI definition.'))
    } finally {
      setIsLoadingDefinition(false)
    }
  }

  async function runOperationTest() {
    setIsTesting(true)
    try {
      const result = await testReadOnlyOperation(token, path)
      setOperationMessage(`${result.message} ${result.statusCode ?? 'No status'} | ${result.contentType || 'unknown content type'} | ${result.responseBytes} bytes${result.responseTruncated ? ' (truncated)' : ''}.`)
    } catch (error) {
      setOperationMessage(messageForError(error, 'Unable to test the saved API operation.'))
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <div className='api-harness-page'>
      {configError && <p role='alert' className='error-banner'>{configError}</p>}
      <div className='api-harness-column'>
        <div className='api-diagnostic-slot'><JobProgressCard token={token} /></div>
        <div className='api-queue-slot'><ApprovedQueueImportCard config={config} token={token} onNavigate={onNavigate} /></div>
      </div>
      <div className='api-harness-column'>
        <div className='api-contract-slot'>
          <ApprovedContractSetupCard
            config={config}
            token={token}
            onApproved={(contractVersion) => setConfig((current) => current ? { ...current, activeContractVersion: contractVersion } : current)}
          />
        </div>
        <div className='api-tests-slot'>
          <section className='panel'>
            <p className='eyebrow'>API Testing Harness</p>
            <h2>Alleva/OpenAPI testing</h2>
            <p className='muted'>Every control below uses the encrypted profile saved in Settings. Credentials and response bodies never appear in this page.</p>
            <div className='harness-grid'>
              <article>
                <h3>OAuth authentication</h3>
                <p>Obtains a client-credentials token and immediately discards it after verification.</p>
                <p className='muted'>Alleva read-only scope: <code>https://authorization.allevasoft.com/api:read</code></p>
                <button type='button' onClick={() => void testAuthentication()} disabled={isTestingAuthentication}>
                  {isTestingAuthentication ? 'Testing saved OAuth credentials...' : 'Test saved OAuth credentials'}
                </button>
                {authenticationMessage && <p role='status'>{authenticationMessage}</p>}
              </article>
              <article>
                <h3>OpenAPI definition</h3>
                <p>Loads the saved definition URL and returns only its title and bounded operation count.</p>
                <button type='button' onClick={() => void loadDefinition()} disabled={isLoadingDefinition}>
                  {isLoadingDefinition ? 'Loading saved OpenAPI definition...' : 'Load saved OpenAPI definition'}
                </button>
                {definitionMessage && <p role='status'>{definitionMessage}</p>}
              </article>
              <article className='harness-operation-card'>
                <h3>Read-only operation</h3>
                <p>Runs one saved-profile GET request and reports status, content type, and bounded response size without returning the body.</p>
                <label>
                  Read-only operation path
                  <input value={path} onChange={(event) => setPath(event.target.value)} placeholder='/clients' />
                </label>
                <button type='button' onClick={() => void runOperationTest()} disabled={isTesting}>
                  {isTesting ? 'Testing operation...' : 'Test read-only operation'}
                </button>
                {operationMessage && <p role='status'>{operationMessage}</p>}
              </article>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function messageForError(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return fallback
}
