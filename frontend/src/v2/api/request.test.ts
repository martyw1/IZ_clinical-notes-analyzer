import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError, readRecordPayload } from './json'
import { request } from './request'

describe('request', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('preserves successful response bodies when a request succeeds', async () => {
    // Given: the local API returns a successful JSON response.
    vi.stubGlobal('fetch', vi.fn(async () => reply({ result: 'ready' })))
    // When: a request completes.
    const response = await request('/api/health')
    // Then: the caller can still read the body.
    expect(await response.json()).toEqual({ result: 'ready' })
  })

  it('turns a non-JSON server failure into an actionable local-service error', async () => {
    // Given: the local API returns an HTML/text failure.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Internal Server Error', { status: 500 })))
    // When/Then: reading the failure yields a fixed, safe message.
    await expect(request('/api/audit/logs')).rejects.toThrow(
      'The local service returned an unexpected error. Restart the app and try again.',
    )
  })

  it('maps validation fields and types without exposing any raw error data', async () => {
    // Given: FastAPI includes private input, context, message, and an unknown location.
    const privateMarker = 'SYNTHETIC-PRIVATE-VALIDATION-MARKER'
    vi.stubGlobal('fetch', vi.fn(async () => reply({ detail: [
      { loc: ['body', 'password'], type: 'string_too_short', input: privateMarker, ctx: { error: privateMarker }, msg: privateMarker },
      { loc: ['body', 'username'], type: 'missing', input: { password: privateMarker } },
      { loc: ['body', privateMarker], type: privateMarker, msg: privateMarker },
    ] }, 422)))
    // When: validation fails.
    const error = await request('/api/auth/login').catch((reason: unknown) => reason)
    // Then: only approved field/type messages reach the error object.
    expect(error instanceof ApiRequestError).toBe(true)
    if (!(error instanceof ApiRequestError)) return
    expect(error.message).toContain('Password')
    expect(error.message).toContain('Username')
    expect(error.message.includes(privateMarker)).toBe(false)
    expect(JSON.stringify(error).includes(privateMarker)).toBe(false)
  })

  it.each([400, 401, 403, 409, 422, 500])('redacts arbitrary exception details when status is %s', async (status) => {
    // Given: an arbitrary server exception string could contain a password.
    const privateMarker = 'SYNTHETIC-PRIVATE-EXCEPTION-MARKER'
    vi.stubGlobal('fetch', vi.fn(async () => reply({ detail: privateMarker }, status)))
    // When: the request fails.
    const error = await request('/api/test').catch((reason: unknown) => reason)
    // Then: no part of that string is displayed or retained on the error.
    expect(error instanceof ApiRequestError).toBe(true)
    if (!(error instanceof ApiRequestError)) return
    expect(error.message.includes(privateMarker)).toBe(false)
    expect(error.status).toBe(status)
  })

  it('keeps known corrective guidance when the API reports an MRN conflict', async () => {
    // Given: a fixed known corrective message is returned.
    vi.stubGlobal('fetch', vi.fn(async () => reply({ detail: 'Confirm the MRN correction and submit again.' }, 409)))
    // When/Then: the safe guidance survives the boundary.
    await expect(request('/api/test')).rejects.toThrow('Confirm the MRN correction and submit again.')
  })

  it('redacts malformed success JSON rather than propagating its parser exception', async () => {
    // Given: malformed JSON includes data that must never become an error message.
    const privateMarker = 'SYNTHETIC-PRIVATE-JSON-MARKER'
    // When: a successful response cannot be parsed.
    const error = await readRecordPayload(new Response(privateMarker)).catch((reason: unknown) => reason)
    // Then: consumers receive a typed safe error, not the raw parser failure.
    expect(error instanceof ApiRequestError).toBe(true)
    if (!(error instanceof ApiRequestError)) return
    expect(error.message.includes(privateMarker)).toBe(false)
  })

  it('redacts network exception text when the local connection fails', async () => {
    // Given: a transport failure includes a private marker in its exception text.
    const privateMarker = 'SYNTHETIC-PRIVATE-NETWORK-MARKER'
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError(privateMarker) }))
    // When: the connection fails.
    const error = await request('/api/test').catch((reason: unknown) => reason)
    // Then: only a typed, fixed local-service message escapes.
    expect(error instanceof ApiRequestError).toBe(true)
    if (!(error instanceof ApiRequestError)) return
    expect(error.message.includes(privateMarker)).toBe(false)
    expect(error.status).toBe(0)
  })
})

function reply(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status })
}
