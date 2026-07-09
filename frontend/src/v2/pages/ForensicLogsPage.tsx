<<<<<<< HEAD
import { useEffect, useState } from 'react'
import { listAuditLogs } from '../api/client'
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

=======
export function ForensicLogsPage() {
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
  return (
    <section className='panel'>
      <p className='eyebrow'>Forensic Logs</p>
      <h2>Redacted audit events</h2>
      <div className='summary-grid'>
<<<<<<< HEAD
        <span>Hash-chain verification: recorded</span>
        <span>Patient names: excluded</span>
        <span>Clinical narrative: not logged</span>
        <span>Vendor secrets: configured flags only</span>
      </div>
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
=======
        <span>Hash-chain verification: ready</span>
        <span>Patient names: excluded</span>
        <span>Clinical narrative: not logged</span>
        <span>Large job lifecycle: audited</span>
      </div>
      <table>
        <thead><tr><th>Action</th><th>Entity</th><th>Outcome</th><th>Safe details</th></tr></thead>
        <tbody>
          <tr><td>manager.criterion.return_for_correction</td><td>Patient ID 307</td><td>success</td><td>comment present, no narrative payload</td></tr>
          <tr><td>api_harness.job.completed</td><td>job-local-demo</td><td>success</td><td>records and artifact names only</td></tr>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
        </tbody>
      </table>
    </section>
  )
}
