import { useEffect, useState } from 'react'
import { assignPatient, assignUserFacility, createUser, listFacilities, listUsers, resetUserPassword } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { Facility, UserProfile } from '../api/types'

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

  async function assignPatientToCounselor(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await assignPatient(token, String(form.get('patientId') ?? ''), String(form.get('counselorUsername') ?? ''))
    setMessage('Patient assigned to counselor.')
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
      <form onSubmit={assignFacility} className='settings-form'>
        <h3>Facility assignment</h3>
        <label>Facility assignment user<select name='facilityUserId'>{users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}</select></label>
        <label>Facility<select name='facilityId'>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.displayName}</option>)}</select></label>
        <button type='submit'>Assign facility</button>
      </form>
      <form onSubmit={assignPatientToCounselor} className='settings-form'>
        <h3>Patient assignment</h3>
        <label>Patient ID assignment<input name='patientId' /></label>
        <label>Counselor assignment<select name='counselorUsername'>{users.filter((user) => user.role === 'counselor').map((user) => <option key={user.id} value={user.username}>{user.username}</option>)}</select></label>
        <button type='submit'>Assign patient</button>
      </form>
      <table>
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Password reset</th><th>Action</th></tr></thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.fullName}</td>
              <td>{user.role}</td>
              <td>{user.authState}</td>
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
