import { FormEvent, useEffect, useMemo, useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/api'

type User = { username: string; role: 'admin' | 'counselor' | 'manager'; must_reset_password: boolean }
type Chart = { id: number; client_name: string; level_of_care: string; primary_clinician: string; state: string }

export function App() {
  const [token, setToken] = useState<string>('')
  const [status, setStatus] = useState<string>('Ready')
  const [user, setUser] = useState<User | null>(null)
  const [charts, setCharts] = useState<Chart[]>([])
  const [form, setForm] = useState({ username: 'admin', password: 'r3' })

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])

  async function login(e: FormEvent) {
    e.preventDefault()
    try {
      const response = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
      if (!response.ok) {
        setStatus('Login failed')
        return
      }
      const data = await response.json()
      setToken(data.access_token)
      setStatus(data.must_reset_password ? 'Password reset required on first login.' : 'Login successful.')
    } catch {
      setStatus('Login failed: backend unreachable. Verify API URL or port mapping.')
    }
  }

  async function loadMeAndCharts() {
    if (!token) return
    const me = await fetch(`${API}/users/me`, { headers: authHeaders })
    if (me.ok) {
      setUser(await me.json())
    }
    const chartRes = await fetch(`${API}/charts`, { headers: authHeaders })
    if (chartRes.ok) {
      setCharts(await chartRes.json())
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
    setStatus(response.ok ? 'Chart created.' : 'Unable to create chart.')
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
      <div style={{ background: '#e6f0ff', padding: 8, borderRadius: 6, marginBottom: 16 }}>Status: {status}</div>

      {!token ? (
        <form onSubmit={login} style={{ display: 'grid', gap: 8, maxWidth: 320 }}>
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder='Username' />
          <input type='password' value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder='Password' />
          <button type='submit'>Sign in</button>
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
