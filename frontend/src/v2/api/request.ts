import { ApiRequestError, readRecordPayload, readString } from './json'

type RequestOptions = {
  readonly token?: string
  readonly method?: 'DELETE' | 'GET' | 'POST' | 'PUT' | 'PATCH'
  readonly body?: Record<string, unknown>
  readonly formBody?: FormData
}

function headersFor(options: RequestOptions): Headers {
  const headers = new Headers()
  headers.set('accept', 'application/json')
  if (options.body && !options.formBody) headers.set('content-type', 'application/json')
  if (options.token) headers.set('authorization', `Bearer ${options.token}`)
  return headers
}

export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const response = await fetch(path, {
    method: options.method ?? 'GET',
    headers: headersFor(options),
    body: options.formBody ?? (options.body ? JSON.stringify(options.body) : undefined),
  })
  if (response.ok) return response
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
  throw new ApiRequestError(response.status, readString(payload, 'detail', 'The local API request failed.'))
}
