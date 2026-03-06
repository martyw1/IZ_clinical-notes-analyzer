import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App } from './App'

declare global {
  // eslint-disable-next-line no-var
  var fetch: typeof window.fetch
}

type MockResponse = { ok: boolean; status: number; json: () => Promise<unknown> }

function makeResponse(status: number, payload: unknown): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

function mockFetchSequence(responses: MockResponse[]) {
  const fn = vi.fn()
  responses.forEach((response) => fn.mockResolvedValueOnce(response))
  global.fetch = fn as unknown as typeof window.fetch
  return fn
}

describe('App auth flow', () => {
  it('renders dashboard only after login and profile+charts load', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-a', must_reset_password: false }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, []),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Admin Dashboard')).toBeInTheDocument())
    expect(screen.queryByText('Session issue detected')).not.toBeInTheDocument()
  })

  it('shows password reset flow when login marks reset required', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-b', must_reset_password: true }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: true }),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Password Reset Required')).toBeInTheDocument())
    expect(screen.queryByText('Admin Dashboard')).not.toBeInTheDocument()
  })

  it('does not render dashboard when profile load fails', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-c', must_reset_password: false }),
      makeResponse(500, { detail: 'boom' }),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText(/profile load failed/)).toBeInTheDocument())
    expect(screen.queryByText('Admin Dashboard')).not.toBeInTheDocument()
  })

  it('completes reset and lands on dashboard after reload', async () => {
    mockFetchSequence([
      makeResponse(200, { access_token: 'token-d', must_reset_password: true }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: true }),
      makeResponse(200, { status: 'ok' }),
      makeResponse(200, { username: 'admin', role: 'admin', must_reset_password: false }),
      makeResponse(200, [{ id: 1, client_name: 'A', level_of_care: 'Residential', primary_clinician: 'admin', state: 'created' }]),
    ])

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Password Reset Required')).toBeInTheDocument())

    fireEvent.change(screen.getByPlaceholderText('New password (min 12 chars)'), { target: { value: 'new-password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(screen.getByText('Admin Dashboard')).toBeInTheDocument())
  })
})
