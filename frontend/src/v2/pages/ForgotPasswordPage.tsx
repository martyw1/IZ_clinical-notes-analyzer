import { useState } from 'react'
import { recoverPassword } from '../api/passwordClient'
import { PasswordFields } from '../components/PasswordFields'

export function ForgotPasswordPage({ onBack }: { readonly onBack: (recovered: boolean) => void }) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const newPassword = String(form.get('newPassword') ?? '')
    if (newPassword !== String(form.get('confirmPassword') ?? '')) { setMessage('The new passwords do not match.'); return }
    setBusy(true)
    setMessage('')
    try {
      await recoverPassword(String(form.get('username') ?? '').trim(), String(form.get('recoveryCode') ?? '').trim(), newPassword)
      onBack(true)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to recover your account.') }
    finally { setBusy(false) }
  }
  return <main className='login-page'><section className='login-card'>
    <h1>Reset a forgotten password</h1>
    <p>Use the recovery code saved for this account on this installation. Without a code, ask an authorized administrator to reset your password. If you are the only administrator, contact your R3 support contact for local recovery assistance.</p>
    <form onSubmit={submit}>
      <label>Username<input name='username' autoComplete='username' defaultValue='admin' required /></label>
      <label>Recovery code<input name='recoveryCode' type='password' autoComplete='off' required /></label>
      <PasswordFields />
      {message && <p role='alert' className='error-banner'>{message}</p>}
      <button type='submit' disabled={busy}>{busy ? 'Resetting password...' : 'Reset password'}</button>
    </form>
    <button type='button' className='secondary-button' disabled={busy} onClick={() => onBack(false)}>Back to sign in</button>
  </section></main>
}
