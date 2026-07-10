import { readNumber, readRecordPayload, readString } from './json'
import { request } from './request'
import type { OAuthConnectivityResult } from './types'

export async function testSavedOAuthConnectivity(token: string): Promise<OAuthConnectivityResult> {
  const payload = await readRecordPayload(
    await request('/api/api-configuration/test-connectivity', { token, method: 'POST' }),
  )
  const status = readString(payload, 'status') === 'ok' ? 'ok' : 'failure'
  const authStyle = readString(payload, 'token_auth_style') === 'basic' ? 'basic' : 'body'
  const expiresIn = payload.expires_in
  return { status, tokenAuthStyle: authStyle, message: readString(payload, 'message'), tokenType: readString(payload, 'token_type'), expiresIn: typeof expiresIn === 'number' ? readNumber(payload, 'expires_in') : null }
}
