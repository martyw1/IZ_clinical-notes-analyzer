import { describe, expect, it, vi } from 'vitest'
import { request } from './request'

describe('request', () => {
  it('turns a non-JSON server failure into an actionable local-service error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Internal Server Error', { status: 500 })))

    await expect(request('/api/audit/logs')).rejects.toThrow(
      'The local service returned an unexpected error. Restart the app and try again.',
    )
  })
})
