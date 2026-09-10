import { PasswordResetPage } from './PasswordResetPage'
import { RecoverySetup } from './RecoverySetup'

type AccountPageProps = {
  readonly token: string
  readonly onChanged: (token: string) => Promise<void>
  readonly configured: boolean
  readonly onSaved: () => void
}

export function AccountPage({ token, onChanged, configured, onSaved }: AccountPageProps) {
  return <div className='password-form'>
    <h2>Account and password</h2>
    <PasswordResetPage token={token} onChanged={onChanged} embedded />
    <RecoverySetup token={token} configured={configured} onSaved={onSaved} />
  </div>
}
