import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppV2 } from './AppV2'
import { request, endRequestSession } from './api/request'

const storageKey = 'iz-cna-v2-access-token'
type Override = (path: string, init?: RequestInit) => Promise<Response> | undefined

function mockApi(override: Override = () => undefined) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const overridden = override(path, init)
    if (overridden) return overridden
    if (path === '/api/auth/login') return Promise.resolve(reply({ access_token: 'new-session' }))
    if (path === '/api/users/me') return Promise.resolve(reply(user()))
    if (path === '/api/v2/navigation') return Promise.resolve(reply({ items: ['Help', 'Manual Upload'] }))
    return Promise.resolve(reply({}, path === '/api/expired' ? 401 : 200))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function user(role = 'office_manager') {
  return { id: 1, username: 'synthetic-user', full_name: 'Synthetic User', role, is_active: true, must_reset_password: false, facilities: [] }
}

function reply(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status })
}

async function signIn() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'synthetic-user' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-password-123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await screen.findByRole('button', { name: 'Sign out' })
}

describe('V2 session lifecycle', () => {
  afterEach(() => { cleanup(); sessionStorage.clear(); endRequestSession(); vi.unstubAllGlobals() })

  it('shows protected navigation when valid credentials sign in', async () => {
    // Given: a synthetic successful local API.
    mockApi()
    render(<AppV2 />)
    // When: the user signs in.
    await signIn()
    // Then: authorized navigation is visible and the session is retained.
    expect(screen.getByRole('navigation')).toBeInTheDocument()
    expect(sessionStorage.getItem(storageKey) === 'new-session').toBe(true)
  })

  it('clears protected content when the current session receives 401', async () => {
    // Given: an authenticated user has opened a protected page.
    mockApi()
    render(<AppV2 />)
    await signIn()
    fireEvent.click(screen.getByRole('button', { name: 'Manual Upload' }))
    // When: two current-session requests fail as unauthorized.
    await act(async () => { await Promise.allSettled([
      request('/api/expired', { token: 'new-session' }), request('/api/expired', { token: 'new-session' }),
    ]) })
    // Then: one login state replaces all protected content and storage is cleared.
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Treatment-plan binder files')).not.toBeInTheDocument()
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(sessionStorage.getItem(storageKey)).toBeNull()
  })

  it.each([403, 422, 500])('keeps authentication when a protected request fails with %s', async (status) => {
    // Given: an authenticated local session.
    mockApi((path) => path === '/api/failure' ? Promise.resolve(reply({}, status)) : undefined)
    render(<AppV2 />)
    await signIn()
    // When: a protected operation fails without 401.
    await act(async () => { await Promise.allSettled([request('/api/failure', { token: 'new-session' })]) })
    // Then: the navigation and stored session survive.
    expect(screen.getByRole('navigation')).toBeInTheDocument()
    expect(sessionStorage.getItem(storageKey) === 'new-session').toBe(true)
  })

  it('rejects blank login fields locally when the form is submitted', async () => {
    // Given: an empty username and password.
    const fetchMock = mockApi()
    render(<AppV2 />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: '   ' } })
    // When: the user submits the form.
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    // Then: local feedback is visible and credentials never reach the API.
    expect(fetchMock.mock.calls.length).toBe(0)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it.each([401, 500, 200])('ignores a stale restore result when its status is %s after new login', async (status) => {
    // Given: initial restoration is pending while a new login succeeds.
    sessionStorage.setItem(storageKey, 'old-session')
    let finish: ((response: Response) => void) | undefined
    mockApi((path, init) => path === '/api/users/me' && new Headers(init?.headers).get('authorization') === 'Bearer old-session'
      ? new Promise<Response>((resolve) => { finish = resolve }) : undefined)
    render(<AppV2 />)
    await signIn()
    // When: the older restore completes late.
    await act(async () => { finish?.(reply(user('viewer'), status)) })
    // Then: neither the new token nor the new user's protected state changes.
    expect(sessionStorage.getItem(storageKey) === 'new-session').toBe(true)
    expect(screen.getByLabelText('Signed-in role')).toHaveTextContent('office manager')
  })

  it.each([403, 422, 500])('retains the stored token when initial restoration fails with %s', async (status) => {
    // Given: a stored session hits a temporary or non-authentication error.
    sessionStorage.setItem(storageKey, 'old-session')
    mockApi((path) => path === '/api/users/me' ? Promise.resolve(reply({}, status)) : undefined)
    render(<AppV2 />)
    // When: restore reports the error.
    await screen.findByRole('alert')
    // Then: it does not silently discard authentication.
    expect(sessionStorage.getItem(storageKey) === 'old-session').toBe(true)
  })

  it('does not mutate storage when an unmounted restore fails late', async () => {
    // Given: an earlier app instance has an in-flight restore.
    sessionStorage.setItem(storageKey, 'old-session')
    let finish: ((response: Response) => void) | undefined
    mockApi((path) => path === '/api/users/me' ? new Promise<Response>((resolve) => { finish = resolve }) : undefined)
    const view = render(<AppV2 />)
    view.unmount()
    sessionStorage.setItem(storageKey, 'new-session')
    // When: its stale request fails after unmount.
    await act(async () => { finish?.(reply({}, 401)) })
    // Then: storage owned by a replacement session is untouched.
    expect(sessionStorage.getItem(storageKey) === 'new-session').toBe(true)
  })

  it('submits credentials once when the form receives duplicate submit events', async () => {
    // Given: a login request stays in flight.
    let finish: ((response: Response) => void) | undefined
    const fetchMock = mockApi((path) => path === '/api/auth/login' ? new Promise<Response>((resolve) => { finish = resolve }) : undefined)
    render(<AppV2 />)
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-password-123' } })
    const form = screen.getByRole('button', { name: 'Sign in' }).closest('form')
    if (!form) throw new Error('Login form missing')
    // When: submit is emitted twice before the request completes.
    fireEvent.submit(form)
    fireEvent.submit(form)
    // Then: only one login attempt is made.
    expect(fetchMock.mock.calls.filter(([path]) => path === '/api/auth/login').length).toBe(1)
    await act(async () => { finish?.(reply({ access_token: 'new-session' })) })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument())
  })
})
