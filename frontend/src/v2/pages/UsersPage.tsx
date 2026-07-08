export function UsersPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Users</p>
      <h2>Role-based access</h2>
      <table>
        <thead><tr><th>Role</th><th>Permissions</th></tr></thead>
        <tbody>
          <tr><td>admin</td><td>Settings, API harness, sync/import, logs, exports, users</td></tr>
          <tr><td>office_manager</td><td>Treatment-plan workbench, criterion review, comments, returns, overrides</td></tr>
          <tr><td>counselor</td><td>Returned action items only when ownership exists</td></tr>
          <tr><td>viewer</td><td>Read-only dashboards if enabled</td></tr>
        </tbody>
      </table>
    </section>
  )
}
