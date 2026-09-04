import { useEffect, useState } from 'react'
import { listAuditLogs, verifyAuditLogs } from '../api/auditClient'
import { ApiRequestError } from '../api/json'
import { formatUtcEventDateTime } from '../components/treatmentPlanFormatting'
import type { AuditLogItem } from '../api/types'

type ForensicLogsPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load audit logs.'
}

export function ForensicLogsPage({ token }: ForensicLogsPageProps) {
  const [logs, setLogs] = useState<readonly AuditLogItem[]>([])
  const [error, setError] = useState('')
  const [verification, setVerification] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [isVerifying, setIsVerifying] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function loadLogs() {
      setIsLoading(true)
      setError('')
      try {
        const payload = await listAuditLogs(token)
        if (!cancelled) setLogs(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void loadLogs()
    return () => {
      cancelled = true
    }
  }, [reloadKey, token])

  async function verifyChain() {
    setIsVerifying(true)
    try {
      const result = await verifyAuditLogs(token)
      if (!result.valid) {
        setVerification(`Current-format hash chain verification failed at audit record ${result.firstInvalidId ?? 'unknown'}.`)
      } else if (result.legacyEventCount > 0) {
        setVerification(`Current-format hash chain verified across ${result.verifiedEventCount} events. ${result.legacyEventCount} earlier-format events remain available but are outside this verifier. Privacy: ${result.privacyMode}; retention hook: ${result.retentionHook}.`)
      } else {
        setVerification(`Hash chain verified across ${result.eventCount} events. Privacy: ${result.privacyMode}; retention hook: ${result.retentionHook}.`)
      }
    } catch (verifyError) {
      setVerification(messageForError(verifyError))
    } finally {
      setIsVerifying(false)
    }
  }

  return (
    <section className='panel table-panel'>
      <p className='eyebrow'>Forensic Logs</p>
      <h2>Redacted audit events</h2>
      <div className='summary-grid'>
        <span>Hash chain: verify on demand</span>
        <span>Patient names: excluded</span>
        <span>Clinical narrative: not logged</span>
        <span>Vendor secrets: configured flags only</span>
      </div>
      <div className='button-row'>
        <button type='button' className='secondary-button' onClick={() => setReloadKey((value) => value + 1)} disabled={isLoading}>{isLoading ? 'Loading logs...' : 'Refresh logs'}</button>
        <button type='button' className='secondary-button' onClick={() => void verifyChain()} disabled={isVerifying}>{isVerifying ? 'Verifying hash chain...' : 'Verify hash chain'}</button>
      </div>
      {error && <p className='error-banner' role='alert'>{error}</p>}
      {verification && <p role='status'>{verification}</p>}
      <table className='forensic-table'>
        <thead><tr><th>Action</th><th>Actor</th><th>Entity</th><th>Outcome</th><th>Details</th><th>Timestamp</th></tr></thead>
        <tbody>
          {!isLoading && logs.length === 0 && <tr><td colSpan={6}>No audit events have been recorded yet.</td></tr>}
          {logs.map((log) => (
            <tr key={log.eventId}>
              <td data-label='Action'>{log.action}</td>
              <td data-label='Actor'>{log.actorUsername || log.actorRole}</td>
              <td data-label='Entity'>{log.targetEntityType}: {log.targetEntityId}</td>
              <td data-label='Outcome'>{log.outcomeStatus}</td>
              <td data-label='Details'><code>{log.detailsSummary || 'No additional details'}</code></td>
              <td data-label='Timestamp'><time dateTime={log.timestampUtc}>{formatUtcEventDateTime(log.timestampUtc)}</time></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
