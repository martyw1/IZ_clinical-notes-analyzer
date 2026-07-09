<<<<<<< HEAD
import { useEffect, useState } from 'react'
import { listUsers } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { UserProfile } from '../api/types'

type UsersPageProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load users.'
}

export function UsersPage({ token }: UsersPageProps) {
  const [users, setUsers] = useState<readonly UserProfile[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const payload = await listUsers(token)
        if (!cancelled) setUsers(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      }
    }
    void loadUsers()
    return () => {
      cancelled = true
    }
  }, [token])

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>

=======
export function UsersPage() {
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
  return (
    <section className='panel'>
      <p className='eyebrow'>Users</p>
      <h2>Role-based access</h2>
      <table>
<<<<<<< HEAD
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Password reset</th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.fullName}</td>
              <td>{user.role}</td>
              <td>{user.isActive && !user.isLocked ? 'active' : 'blocked'}</td>
              <td>{user.mustResetPassword ? 'required' : 'not required'}</td>
            </tr>
          ))}
=======
        <thead><tr><th>Role</th><th>Permissions</th></tr></thead>
        <tbody>
          <tr><td>admin</td><td>Settings, API harness, sync/import, logs, exports, users</td></tr>
          <tr><td>office_manager</td><td>Treatment-plan workbench, criterion review, comments, returns, overrides</td></tr>
          <tr><td>counselor</td><td>Returned action items only when ownership exists</td></tr>
          <tr><td>viewer</td><td>Read-only dashboards if enabled</td></tr>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
        </tbody>
      </table>
    </section>
  )
}
