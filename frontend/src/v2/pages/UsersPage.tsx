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

  return (
    <section className='panel'>
      <p className='eyebrow'>Users</p>
      <h2>Role-based access</h2>
      <table>
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
        </tbody>
      </table>
    </section>
  )
}
