import { readBoolean, readRecordPayload, readString } from './json'
import { request } from './request'

export async function recoveryConfigured(token: string): Promise<boolean> {
  return readBoolean(await readRecordPayload(await request('/api/users/me/recovery-code', { token })), 'configured')
}

export async function generateRecoveryCode(token: string, currentPassword: string): Promise<string> {
  return readString(await readRecordPayload(await request('/api/users/me/recovery-code', {
    token, method: 'POST', body: { current_password: currentPassword },
  })), 'recovery_code')
}

export async function recoverPassword(username: string, recoveryCode: string, newPassword: string): Promise<void> {
  await request('/api/auth/recover-password', {
    method: 'POST', body: { username, recovery_code: recoveryCode, new_password: newPassword },
  })
}
