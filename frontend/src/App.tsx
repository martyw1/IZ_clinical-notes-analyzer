import { FormEvent, useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/api'

type User = { username: string; role: 'admin' | 'counselor' | 'manager'; must_reset_password: boolean }
type Chart = { id: number; client_name: string; level_of_care: string; primary_clinician: string; state: string }

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
  const [user, setUser] = useState<User | null>(null)
  const [charts, setCharts] = useState<Chart[]>([])
  const [form, setForm] = useState({ username: 'admin', password: 'r3' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [loading, setLoading] = useState(false)

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])

  async function login(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setStatus(`Login failed. ${readErrorMessage(response.status, payload)}`)
        return
      }
      const data = payload as { access_token: string; must_reset_password: boolean }
      setToken(data.access_token)
      setStatus(data.must_reset_password ? 'Password reset required before continuing.' : 'Login successful.')
    } catch {
      setStatus('Login failed: backend unreachable. Verify API URL or port mapping.')
    } finally {
      setLoading(false)
    }
  }

  async function loadMeAndCharts() {
    if (!token) return
    setLoading(true)
    try {
      const me = await fetch(`${API}/users/me`, { headers: authHeaders })
      const mePayload = (await me.json().catch(() => null)) as ApiError | User | null
      if (!me.ok) {
        setStatus(`Unable to load current user. ${readErrorMessage(me.status, mePayload as ApiError | null)}`)
        return
      }
      const currentUser = mePayload as User
      setUser(currentUser)

      const chartRes = await fetch(`${API}/charts`, { headers: authHeaders })
      const chartPayload = (await chartRes.json().catch(() => null)) as ApiError | Chart[] | null
      if (!chartRes.ok) {
        setStatus(`Logged in, but charts failed to load. ${readErrorMessage(chartRes.status, chartPayload as ApiError | null)}`)
        return
      }
      setCharts((chartPayload as Chart[]) || [])
      if (!currentUser.must_reset_password) {
        setStatus('Dashboard loaded.')
      }
    } catch {
      setStatus('Network error while loading dashboard data.')
    } finally {
      setLoading(false)
    }
  }

  async function resetPassword(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      const response = await fetch(`${API}/auth/reset-password`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ new_password: resetForm.newPassword }),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setStatus(`Password reset failed. ${readErrorMessage(response.status, payload)}`)
        return
      }
      setResetForm({ newPassword: '' })
      setStatus('Password reset complete. Loading dashboard...')
      await loadMeAndCharts()
    } catch {
      setStatus('Password reset failed: backend unreachable.')
    } finally {
      setLoading(false)
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
    setStatus(response.ok ? 'Chart created.' : `Unable to create chart (HTTP ${response.status}).`)
    await loadMeAndCharts()
  }

  useEffect(() => {
    loadMeAndCharts()
  }, [token])

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', margin: '0 auto', maxWidth: 1000, padding: 16 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Chart Review Workflow</h1>
        <div style={{ fontWeight: 700 }}>r3recoveryservices.com</div>
      </header>
      <div style={{ background: '#e6f0ff', padding: 8, borderRadius: 6, marginBottom: 16 }}>
        Status: {status} {loading ? 'Loading…' : ''}
      </div>

      {!token ? (
        <form onSubmit={login} style={{ display: 'grid', gap: 8, maxWidth: 320 }}>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder='Username' />
          <input type='password' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder='Password' />
          <button type='submit' disabled={loading}>Sign in</button>
        </form>
      ) : user?.must_reset_password ? (
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
          <button type='submit' disabled={loading || resetForm.newPassword.length < 12}>Reset password</button>
        </form>
      ) : (
        <>
          <section>
            <h2>{user?.role === 'admin' ? 'Admin Dashboard' : 'Counselor Dashboard'}</h2>
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
      )}
    </div>
  )
}
