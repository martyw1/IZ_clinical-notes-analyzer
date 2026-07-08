export function ForensicLogsPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Forensic Logs</p>
      <h2>Redacted audit events</h2>
      <div className='summary-grid'>
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
        </tbody>
      </table>
    </section>
  )
}
