import { useState } from 'react'
import { changeCurrentPassword } from '../api/client'

type PasswordResetPageProps = {
  readonly token: string
  readonly onChanged: () => Promise<void>
}

export function PasswordResetPage({ token, onChanged }: PasswordResetPageProps) {
  const [message, setMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const currentPassword = String(form.get('currentPassword') ?? '')
    const newPassword = String(form.get('newPassword') ?? '')
    setIsSaving(true)
    try {
      await changeCurrentPassword(token, currentPassword, newPassword)
      await onChanged()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to change password.')
    } finally {
      setIsSaving(false)
    }
  }

  return <main className='login-page'><section className='login-card'><p className='eyebrow'>Password update required</p><h1>Set a new password</h1><form onSubmit={submit}><label>Current password<input name='currentPassword' type='password' autoComplete='current-password' /></label><label>New password<input name='newPassword' type='password' autoComplete='new-password' /></label>{message && <p role='alert' className='error-banner'>{message}</p>}<button type='submit' disabled={isSaving}>{isSaving ? 'Updating password...' : 'Update password'}</button></form></section></main>
}
