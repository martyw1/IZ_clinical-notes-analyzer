import { useState } from 'react'
import { generateRecoveryCode } from '../api/passwordClient'

type RecoverySetupProps = {
  readonly token: string
  readonly configured: boolean
  readonly onSaved: () => void
}

export function RecoverySetup({ token, configured, onSaved }: RecoverySetupProps) {
  const [code, setCode] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function generate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    setBusy(true)
    setMessage('')
    try {
      setCode(await generateRecoveryCode(token, String(form.get('currentPassword') ?? '')))
      formElement.reset()
      setSaved(false)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to create a recovery code.')
    } finally { setBusy(false) }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(code)
      setMessage('Copied. Save the code in a secure place before continuing.')
    } catch (error) {
      setMessage(error instanceof Error ? 'Copy was unavailable. Select and copy the code below, or download it.' : 'Select and copy the code below, or download it.')
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([`IZ Clinical Notes Analyzer recovery code\n\n${code}\n\nKeep this private. Use Forgot password on this installation to recover your account. This code works once.\n`], { type: 'text/plain' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'IZ-account-recovery-code.txt'
    link.click()
    URL.revokeObjectURL(url)
  }

  return <section className='panel'>
    <h2>{code ? 'Save your recovery code' : 'Set up password recovery'}</h2>
    <p>{configured ? 'A recovery code is configured. Creating a replacement invalidates your previous code.' : 'Save a recovery code so you can reset a forgotten password directly from the sign-in screen.'}</p>
    {code ? <div className='password-form'>
      <p>This code is shown only now and works once. Store it in your password manager or another private, secure place separate from this app.</p>
      <label>Recovery code<textarea readOnly value={code} rows={3} autoComplete='off' spellCheck={false} /></label>
      <div className='button-row'><button type='button' className='secondary-button' onClick={() => void copy()}>Copy code</button><button type='button' className='secondary-button' onClick={download}>Download code</button></div>
      <label className='checkbox-row'><input type='checkbox' checked={saved} onChange={event => setSaved(event.target.checked)} />I have saved my recovery code in a secure place.</label>
      <button type='button' disabled={!saved} onClick={() => { setCode(''); setSaved(false); onSaved() }}>Continue</button>
    </div> : <form className='password-form' onSubmit={generate}>
      <label>Current password for recovery setup<input name='currentPassword' type='password' autoComplete='current-password' required /></label>
      <button type='submit' disabled={busy}>{busy ? 'Creating code...' : configured ? 'Replace recovery code' : 'Create recovery code'}</button>
    </form>}
    {message && <p role='status'>{message}</p>}
  </section>
}
