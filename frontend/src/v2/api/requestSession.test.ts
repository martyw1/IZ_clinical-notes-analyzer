import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadChecklistEvidenceExport, downloadTreatmentPlanListExport, downloadTreatmentPlanSourceDocument } from './downloads'
import { readPlanIdentity } from './identity'
import { beginRequestSession, endRequestSession, request } from './request'

const selection = { ...readPlanIdentity({ patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'synthetic' }), mrn: 'synthetic', patientKey: 'synthetic' }

describe('authenticated request generations', () => {
  afterEach(() => { endRequestSession(); vi.unstubAllGlobals() })

  it('expires once when concurrent requests return current-session 401', async () => {
    // Given: two protected requests share the active session.
    const expired = vi.fn()
    const current = beginRequestSession('current', expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })))
    // When: both fail as unauthorized.
    await Promise.allSettled([request('/api/one', { token: 'current' }), request('/api/two', { token: 'current' })])
    // Then: one invalidation clears the active generation.
    expect(expired).toHaveBeenCalledTimes(1)
    expect(current()).toBe(false)
  })

  it.each(['replacement', 'old'])('ignores delayed old-generation 401 when a new session uses %s token', async (newToken) => {
    // Given: an old protected request is in flight.
    const expired = vi.fn()
    beginRequestSession('old', expired)
    let finish: ((response: Response) => void) | undefined
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve })))
    const pending = request('/api/old', { token: 'old' })
    const current = beginRequestSession(newToken, expired)
    // When: the old generation returns 401 after the replacement is active.
    finish?.(new Response('', { status: 401 }))
    await Promise.allSettled([pending])
    // Then: even token reuse cannot expire the replacement generation.
    expect(current()).toBe(true)
    expect(expired).not.toHaveBeenCalled()
  })

  it.each([403, 422, 500])('preserves the active session when a protected request returns %s', async (status) => {
    // Given: the current token is active.
    const expired = vi.fn()
    const current = beginRequestSession('current', expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status })))
    // When: a non-401 failure occurs.
    await Promise.allSettled([request('/api/test', { token: 'current' })])
    // Then: the session remains active.
    expect(current()).toBe(true)
    expect(expired).not.toHaveBeenCalled()
  })

  it('preserves the active session when an unauthenticated login fails', async () => {
    // Given: a current session exists, but login sends no bearer token.
    const expired = vi.fn()
    const current = beginRequestSession('current', expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })))
    // When: that unauthenticated request fails.
    await Promise.allSettled([request('/api/auth/login')])
    // Then: no authenticated invalidation fires.
    expect(current()).toBe(true)
    expect(expired).not.toHaveBeenCalled()
  })

  it.each([
    () => downloadChecklistEvidenceExport('current', selection),
    () => downloadTreatmentPlanListExport('current', { planVersionIds: [selection.planVersionId] }),
    () => downloadTreatmentPlanSourceDocument('current', selection, 'source'),
  ])('uses the same expiry boundary when a download returns 401', async (download) => {
    // Given: an authenticated download will be rejected.
    const expired = vi.fn()
    beginRequestSession('current', expired)
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })))
    // When: the download is requested.
    await Promise.allSettled([download()])
    // Then: downloads cannot bypass expiry handling.
    expect(expired).toHaveBeenCalledTimes(1)
  })
})
