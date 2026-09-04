import { ApiRequestError, readRecordPayload, safeApiErrorMessage } from './json'

type RequestOptions = {
  readonly token?: string
  readonly method?: 'DELETE' | 'GET' | 'POST' | 'PUT' | 'PATCH'
  readonly body?: Record<string, unknown>
  readonly formBody?: FormData
}

type RequestSession = { readonly token: string; readonly onExpired: () => void }
let activeSession: RequestSession | null = null

export function beginRequestSession(token: string, onExpired: () => void): () => boolean {
  const session = { token, onExpired }
  activeSession = session
  return () => activeSession === session
}

export function endRequestSession(): void {
  activeSession = null
}

function headersFor(options: RequestOptions): Headers {
  const headers = new Headers()
  headers.set('accept', 'application/json')
  if (options.body && !options.formBody) headers.set('content-type', 'application/json')
  if (options.token) headers.set('authorization', `Bearer ${options.token}`)
  return headers
}

export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const session = options.token && activeSession?.token === options.token ? activeSession : null
  let response: Response
  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers: headersFor(options),
      body: options.formBody ?? (options.body ? JSON.stringify(options.body) : undefined),
    })
  } catch {
    throw new ApiRequestError(0, 'Unable to reach the local service. Check that the app is running and try again.')
  }
  if (response.ok) return response
  if (response.status === 401 && session && activeSession === session) {
    endRequestSession()
    session.onExpired()
  }
  let payload
  try {
    payload = await readRecordPayload(response)
  } catch (error) {
    if (error instanceof ApiRequestError) throw error
    throw new ApiRequestError(
      response.status,
      'The local service returned an unexpected error. Restart the app and try again.',
    )
  }
  throw new ApiRequestError(response.status, safeApiErrorMessage(response.status, payload))
}
