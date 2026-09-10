import { useState } from 'react'
import { changeCurrentPassword } from '../api/client'
import { PasswordFields } from '../components/PasswordFields'

type PasswordResetPageProps = {
  readonly token: string
  readonly onChanged: (token: string) => Promise<void>
  readonly embedded?: boolean
  readonly onSignOut?: () => void
}

export function PasswordResetPage({ token, onChanged, embedded = false, onSignOut }: PasswordResetPageProps) {
  const [message, setMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    const newPassword = String(form.get('newPassword') ?? '')
    setMessage('')
    if (newPassword !== String(form.get('confirmPassword') ?? '')) {
      setMessage('The new passwords do not match.')
      return
    }
    setIsSaving(true)
    try {
      const result = await changeCurrentPassword(token, String(form.get('currentPassword') ?? ''), newPassword)
      formElement.reset()
      await onChanged(result.accessToken)
      setMessage('Password updated. Other sign-in sessions have ended.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to change password.')
    } finally { setIsSaving(false) }
  }

  const content = <section className={embedded ? 'panel' : 'login-card'}>
    <p className='eyebrow'>{embedded ? 'Password' : 'Password update required'}</p>
    {embedded ? <h2>Change password</h2> : <h1>Set a new password</h1>}
    {!embedded && <p>Replace your temporary password to continue. Then save a recovery code in case you forget your password.</p>}
    <form onSubmit={submit} className='password-form'>
      <label>Current password<input name='currentPassword' type='password' autoComplete='current-password' required /></label>
      <PasswordFields />
      {message && <p role='alert'>{message}</p>}
      <button type='submit' disabled={isSaving}>{isSaving ? 'Updating password...' : 'Update password'}</button>
    </form>
    {onSignOut && <button type='button' className='secondary-button' onClick={onSignOut}>Sign out</button>}
  </section>
  return embedded ? content : <main className='login-page'>{content}</main>
}
