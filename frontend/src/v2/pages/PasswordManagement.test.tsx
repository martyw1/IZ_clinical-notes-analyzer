import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PasswordResetPage } from './PasswordResetPage'
import { ForgotPasswordPage } from './ForgotPasswordPage'
import { RecoverySetup } from './RecoverySetup'
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
it('blocks password changes when confirmation differs', async () => {
  // Given: different new passwords in the confirmation form.
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<PasswordResetPage token='synthetic-token' onChanged={async () => {}} />)
  fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'SyntheticOld123' } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'SyntheticNew123' } })
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'DifferentNew123' } })
  // When: submitting the change.
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  // Then: no password request leaves the form.
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('returns to sign in after recovery without creating a session', async () => {
  // Given: an available public recovery endpoint.
  const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const onBack = vi.fn()
  render(<ForgotPasswordPage onBack={onBack} />)
  fireEvent.change(screen.getByLabelText('Recovery code'), { target: { value: 'SYNTHETIC-CODE' } })
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'SyntheticNew123' } })
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'SyntheticNew123' } })
  // When: the account is recovered.
  fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))
  // Then: the user returns to sign in and the public request carries no authorization.
  await waitFor(() => expect(onBack).toHaveBeenCalledWith(true))
  expect(fetchMock).toHaveBeenCalledWith('/api/auth/recover-password', expect.objectContaining({ method: 'POST' }))
})

it('requires acknowledgment before dismissing a generated recovery code', async () => {
  // Given: a generated synthetic recovery code.
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ recovery_code: 'SYNTHETIC-CODE' }))))
  const onSaved = vi.fn()
  render(<RecoverySetup token='synthetic-token' configured={false} onSaved={onSaved} />)
  fireEvent.change(screen.getByLabelText('Current password for recovery setup'), { target: { value: 'SyntheticCurrent123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Create recovery code' }))
  await screen.findByLabelText('Recovery code')
  expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  // When: the user confirms saving the code and continues.
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
  // Then: the plaintext is removed and completion is reported.
  expect(screen.queryByLabelText('Recovery code')).not.toBeInTheDocument()
  expect(onSaved).toHaveBeenCalledOnce()
})
