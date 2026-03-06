import { FormEvent, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/api'

type User = { username: string; role: 'admin' | 'counselor' | 'manager'; must_reset_password: boolean }
type Chart = { id: number; client_name: string; level_of_care: string; primary_clinician: string; state: string }
type AuthState =
  | 'anonymous'
  | 'logging_in'
  | 'authenticated_loading_profile'
  | 'password_reset_required'
  | 'authenticated_ready'
  | 'error'

type ApiError = {
  detail?: string | { msg?: string }
}

function readErrorMessage(status: number, payload: ApiError | null) {
  const detail = payload?.detail
  if (typeof detail === 'string' && detail.trim()) return `HTTP ${status}: ${detail}`
  if (detail && typeof detail === 'object' && typeof detail.msg === 'string') return `HTTP ${status}: ${detail.msg}`
  return `HTTP ${status}: request failed`
}

export function App() {
  const [token, setToken] = useState<string>('')
  const [status, setStatus] = useState<string>('Ready')
  const [authState, setAuthState] = useState<AuthState>('anonymous')
  const [mustResetPassword, setMustResetPassword] = useState<boolean>(false)
  const [user, setUser] = useState<User | null>(null)
  const [charts, setCharts] = useState<Chart[]>([])
  const [form, setForm] = useState({ username: 'admin', password: 'r3' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])

  function resetSession(message = 'Signed out.') {
    setToken('')
    setUser(null)
    setCharts([])
    setMustResetPassword(false)
    setAuthState('anonymous')
    setStatus(message)
  }

  async function loadProfileAndCharts(currentToken: string, expectsReset: boolean) {
    setAuthState('authenticated_loading_profile')
    setStatus('Loading your profile...')

    const headers = { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' }

    const me = await fetch(`${API}/users/me`, { headers })
    const mePayload = (await me.json().catch(() => null)) as ApiError | User | null
    if (!me.ok) {
      setAuthState('error')
      setStatus(`Unable to load current user. ${readErrorMessage(me.status, mePayload as ApiError | null)}`)
      return
    }

    const currentUser = mePayload as User
    setUser(currentUser)

    if (expectsReset || currentUser.must_reset_password) {
      setMustResetPassword(true)
      setAuthState('password_reset_required')
      setStatus('Password reset required before continuing.')
      return
    }

    const chartRes = await fetch(`${API}/charts`, { headers })
    const chartPayload = (await chartRes.json().catch(() => null)) as ApiError | Chart[] | null
    if (!chartRes.ok) {
      setAuthState('error')
      setStatus(`Logged in, but charts failed to load. ${readErrorMessage(chartRes.status, chartPayload as ApiError | null)}`)
      return
    }

    setCharts((chartPayload as Chart[]) || [])
    setMustResetPassword(false)
    setAuthState('authenticated_ready')
    setStatus('Dashboard loaded.')
  }

  async function login(e: FormEvent) {
    e.preventDefault()
    setAuthState('logging_in')
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Login failed. ${readErrorMessage(response.status, payload)}`)
        return
      }
      const data = payload as { access_token: string; must_reset_password: boolean }
      setToken(data.access_token)
      setMustResetPassword(data.must_reset_password)
      await loadProfileAndCharts(data.access_token, data.must_reset_password)
    } catch {
      setAuthState('error')
      setStatus('Login failed: backend unreachable. Verify API URL or port mapping.')
    }
  }

  async function resetPassword(e: FormEvent) {
    e.preventDefault()
    setStatus('Resetting password...')
    try {
      const response = await fetch(`${API}/auth/reset-password`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ new_password: resetForm.newPassword }),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Password reset failed. ${readErrorMessage(response.status, payload)}`)
        return
      }
      setResetForm({ newPassword: '' })
      setMustResetPassword(false)
      await loadProfileAndCharts(token, false)
    } catch {
      setAuthState('error')
      setStatus('Password reset failed: backend unreachable.')
    }
  }

  async function createSampleChart() {
    const payload = {
      client_name: `Client ${Date.now()}`,
      level_of_care: 'Residential',
      primary_clinician: user?.username || 'Unknown',
      notes: 'Initial chart generated from UI',
    }
    const response = await fetch(`${API}/charts`, { method: 'POST', headers: authHeaders, body: JSON.stringify(payload) })
    if (!response.ok) {
      setStatus(`Unable to create chart (HTTP ${response.status}).`)
      return
    }
    setStatus('Chart created.')
    await loadProfileAndCharts(token, false)
  }

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', margin: '0 auto', maxWidth: 1000, padding: 16 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Chart Review Workflow</h1>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ fontWeight: 700 }}>r3recoveryservices.com</div>
          {token ? <button onClick={() => resetSession()}>Logout</button> : null}
        </div>
      </header>
      <div style={{ background: '#e6f0ff', padding: 8, borderRadius: 6, marginBottom: 16 }}>Status: {status}</div>

      {(authState === 'anonymous' || authState === 'error') && !token ? (
        <form onSubmit={login} style={{ display: 'grid', gap: 8, maxWidth: 320 }}>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder='Username' />
          <input type='password' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder='Password' />
          <button type='submit' disabled={authState === 'logging_in'}>Sign in</button>
        </form>
      ) : authState === 'logging_in' || authState === 'authenticated_loading_profile' ? (
        <section style={{ padding: 12, border: '1px solid #d0d7e2', borderRadius: 6 }}>
          <h2>Signing you in...</h2>
          <p>Please wait while we load your account profile.</p>
        </section>
      ) : authState === 'password_reset_required' || (mustResetPassword && token) ? (
        <form onSubmit={resetPassword} style={{ display: 'grid', gap: 8, maxWidth: 420 }}>
          <h2>Password Reset Required</h2>
          <p>For security, your first login requires a new password (minimum 12 characters).</p>
          <input
            type='password'
            value={resetForm.newPassword}
            minLength={12}
            onChange={(e) => setResetForm({ newPassword: e.target.value })}
            placeholder='New password (min 12 chars)'
          />
          <button type='submit' disabled={resetForm.newPassword.length < 12}>Reset password</button>
        </form>
      ) : authState === 'authenticated_ready' && token && user ? (
        <>
          <section>
            <h2>{user.role === 'admin' ? 'Admin Dashboard' : 'Counselor Dashboard'}</h2>
            <button onClick={createSampleChart}>Create sample chart</button>
          </section>
          <section>
            <h3>Charts</h3>
            <table width='100%' cellPadding={6}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Client</th>
                  <th>Level of Care</th>
                  <th>Primary Clinician</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {charts.map((c) => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td>{c.client_name}</td>
                    <td>{c.level_of_care}</td>
                    <td>{c.primary_clinician}</td>
                    <td>{c.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : (
        <section style={{ padding: 12, border: '1px solid #d0d7e2', borderRadius: 6 }}>
          <h2>Session issue detected</h2>
          <p>We could not finish loading your session.</p>
          <button onClick={() => resetSession('Session cleared. Please sign in again.')}>Clear session</button>
        </section>
      )}
    </div>
  )
}
