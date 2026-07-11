import { useEffect, useState } from 'react'
import { listAuditLogs, verifyAuditLogs } from '../api/auditClient'
import { ApiRequestError } from '../api/json'
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

  useEffect(() => {
    let cancelled = false
    async function loadLogs() {
      try {
        const payload = await listAuditLogs(token)
        if (!cancelled) setLogs(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      }
    }
    void loadLogs()
    return () => {
      cancelled = true
    }
  }, [token])

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>

  async function verifyChain() {
    try {
      const result = await verifyAuditLogs(token)
      setVerification(result.valid ? `Hash chain verified across ${result.eventCount} events. Privacy: ${result.privacyMode}; retention hook: ${result.retentionHook}.` : `Hash chain verification failed at audit record ${result.firstInvalidId ?? 'unknown'}.`)
    } catch (verifyError) { setVerification(messageForError(verifyError)) }
  }

  return (
    <section className='panel'>
      <p className='eyebrow'>Forensic Logs</p>
      <h2>Redacted audit events</h2>
      <div className='summary-grid'>
        <span>Hash chain: verify on demand</span>
        <span>Patient names: excluded</span>
        <span>Clinical narrative: not logged</span>
        <span>Vendor secrets: configured flags only</span>
      </div>
      <button type='button' className='secondary-button' onClick={() => void verifyChain()}>Verify hash chain</button>
      {verification && <p role='status'>{verification}</p>}
      <table>
        <thead><tr><th>Action</th><th>Actor</th><th>Entity</th><th>Outcome</th><th>Timestamp</th></tr></thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.eventId}>
              <td>{log.action}</td>
              <td>{log.actorUsername || log.actorRole}</td>
              <td>{log.targetEntityType}: {log.targetEntityId}</td>
              <td>{log.outcomeStatus}</td>
              <td>{log.timestampUtc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
