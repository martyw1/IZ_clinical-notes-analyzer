import { useEffect, useState } from 'react'
import { createUser, listUsers, resetUserPassword } from '../api/client'
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
  const [message, setMessage] = useState('')

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

  async function refreshUsers() {
    setUsers(await listUsers(token))
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    try {
      await createUser(token, String(form.get('username') ?? ''), String(form.get('fullName') ?? ''), String(form.get('role') ?? 'counselor') as UserProfile['role'], String(form.get('password') ?? ''))
      formElement.reset()
      await refreshUsers()
      setMessage('User created; password change is required on first sign-in.')
    } catch (createError) { setMessage(messageForError(createError)) }
  }

  async function resetPassword(user: UserProfile) {
    const newPassword = window.prompt(`Set a temporary password for ${user.username}`)
    if (!newPassword) return
    try {
      await resetUserPassword(token, user.id, newPassword)
      await refreshUsers()
      setMessage(`Password reset for ${user.username}; password change is required on next sign-in.`)
    } catch (resetError) { setMessage(messageForError(resetError)) }
  }

  return (
    <section className='panel'>
      <p className='eyebrow'>Users</p>
      <h2>Role-based access</h2>
      <form onSubmit={create} className='settings-form'>
        <label>Username<input name='username' autoComplete='username' /></label>
        <label>Full name<input name='fullName' /></label>
        <label>Role<select name='role' defaultValue='counselor'><option value='counselor'>Counselor</option><option value='office_manager'>Office manager</option><option value='viewer'>Viewer</option></select></label>
        <label>Temporary password<input name='password' type='password' autoComplete='new-password' /></label>
        <button type='submit'>Create user</button>
      </form>
      <table>
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Password reset</th><th>Action</th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.fullName}</td>
              <td>{user.role}</td>
              <td>{user.isActive && !user.isLocked ? 'active' : 'blocked'}</td>
              <td>{user.mustResetPassword ? 'required' : 'not required'}</td>
              <td><button type='button' className='secondary-button' onClick={() => void resetPassword(user)} disabled={user.username === 'admin'}>Reset password</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {message && <p role='status'>{message}</p>}
    </section>
  )
}
