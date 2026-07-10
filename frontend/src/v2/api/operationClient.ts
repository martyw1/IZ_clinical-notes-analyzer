import { readBoolean, readNumber, readRecordPayload, readString } from './json'
import { request } from './request'
import type { OperationTestResult } from './types'

export async function testReadOnlyOperation(token: string, path: string): Promise<OperationTestResult> {
  const payload = await readRecordPayload(await request('/api/api-configuration/test-operation', { token, method: 'POST', body: { path } }))
  return { status: readString(payload, 'status') === 'ok' ? 'ok' : 'failure', message: readString(payload, 'message'), statusCode: typeof payload.status_code === 'number' ? readNumber(payload, 'status_code') : null, contentType: readString(payload, 'content_type'), responseBytes: readNumber(payload, 'response_bytes'), responseTruncated: readBoolean(payload, 'response_truncated') }
}
