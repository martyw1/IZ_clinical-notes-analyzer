import { useEffect, useState } from 'react'
import { assignUserFacility, createUser, listFacilities, listUsers, resetUserPassword } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { Facility, UserProfile } from '../api/types'
import { PatientAssignmentForm } from '../components/PatientAssignmentForm'
import type { SessionGuard } from '../hooks/useRequestGeneration'

type UsersPageProps = {
  readonly token: string
  readonly isSessionCurrent?: SessionGuard
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load users.'
}

export function UsersPage({ token, isSessionCurrent }: UsersPageProps) {
  const [users, setUsers] = useState<readonly UserProfile[]>([])
  const [facilities, setFacilities] = useState<readonly Facility[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadUsers() {
      try {
        const [userPayload, facilityPayload] = await Promise.all([listUsers(token), listFacilities(token)])
        if (!cancelled) {
          setUsers(userPayload)
          setFacilities(facilityPayload)
        }
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

  async function assignFacility(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await assignUserFacility(token, Number(form.get('facilityUserId')), Number(form.get('facilityId')))
    await refreshUsers()
    setMessage('Facility assigned.')
  }

  return (
    <section className='panel table-panel users-page'>
      <p className='eyebrow'>Users</p>
      <h2>Role-based access</h2>
      <form onSubmit={create} className='settings-form'>
        <label>Username<input name='username' autoComplete='username' /></label>
        <label>Full name<input name='fullName' /></label>
        <label>Role<select name='role' defaultValue='counselor'><option value='counselor'>Counselor</option><option value='office_manager'>Office manager</option><option value='viewer'>Viewer</option></select></label>
        <label>Temporary password<input name='password' type='password' autoComplete='new-password' /></label>
        <div className='button-row settings-actions'>
          <button type='submit'>Create user</button>
        </div>
      </form>
      <form onSubmit={assignFacility} className='settings-form'>
        <h3>Facility assignment</h3>
        <label>Facility assignment user<select name='facilityUserId'>{users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}</select></label>
        <label>Facility<select name='facilityId'>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.displayName}</option>)}</select></label>
        <div className='button-row settings-actions'>
          <button type='submit'>Assign facility</button>
        </div>
      </form>
      <PatientAssignmentForm token={token} users={users} isSessionCurrent={isSessionCurrent} />
      <table className='users-table'>
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Password reset</th><th>Action</th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td data-label='User'>{user.fullName}</td>
              <td data-label='Role'>{user.role}</td>
              <td data-label='Status'>{user.authState}</td>
              <td data-label='Password reset'>{user.mustResetPassword ? 'required' : 'not required'}</td>
              <td data-label='Action'><button type='button' className='secondary-button' onClick={() => void resetPassword(user)} disabled={user.username === 'admin'}>Reset password</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {message && <p role='status'>{message}</p>}
    </section>
  )
}
