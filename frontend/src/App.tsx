import { FormEvent, useMemo, useState } from 'react'
import './app.css'

const API = import.meta.env.VITE_API_URL || '/api'

type Role = 'admin' | 'counselor' | 'manager'
type WorkflowState = 'Draft' | 'Submitted to Admin' | 'Returned for Update' | 'In Progress Review' | 'Completed' | 'Verified'
type ComplianceStatus = 'pending' | 'yes' | 'no' | 'na'

type User = { username: string; role: Role; must_reset_password: boolean }
type AuditTemplateItem = {
  key: string
  step: number
  section: string
  label: string
  timeframe: string
  instructions: string
  evidence_hint: string
  policy_note: string | null
}
type AuditTemplateSection = { section: string; items: AuditTemplateItem[] }
type AuditItem = {
  item_key: string
  step: number
  section: string
  label: string
  timeframe: string
  instructions: string
  evidence_hint: string
  policy_note: string | null
  status: ComplianceStatus
  notes: string
  evidence_location: string
  evidence_date: string
  expiration_date: string
}
type ChartSummary = {
  id: number
  client_name: string
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  auditor_name: string
  other_details: string
  counselor_id: number
  state: WorkflowState
  notes: string
  pending_items: number
  passed_items: number
  failed_items: number
  not_applicable_items: number
}
type ChartDetail = ChartSummary & { checklist_items: AuditItem[] }
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

type TransitionAction = {
  toState: WorkflowState
  label: string
  requiresComment?: boolean
}

const STATUS_LABELS: Record<ComplianceStatus, string> = {
  pending: 'Pending',
  yes: 'Yes',
  no: 'No',
  na: 'N/A',
}

const STATUS_ORDER: ComplianceStatus[] = ['pending', 'yes', 'no', 'na']

const TRANSITION_MAP: Record<Role, Partial<Record<WorkflowState, TransitionAction[]>>> = {
  counselor: {
    Draft: [{ toState: 'Submitted to Admin', label: 'Submit to admin' }],
    'Returned for Update': [{ toState: 'Submitted to Admin', label: 'Resubmit to admin' }],
  },
  admin: {
    'Submitted to Admin': [
      { toState: 'In Progress Review', label: 'Start review' },
      { toState: 'Returned for Update', label: 'Return for update', requiresComment: true },
    ],
    'In Progress Review': [
      { toState: 'Completed', label: 'Mark completed' },
      { toState: 'Returned for Update', label: 'Return for update', requiresComment: true },
    ],
    Completed: [{ toState: 'Verified', label: 'Verify audit' }],
  },
  manager: {
    'Submitted to Admin': [{ toState: 'In Progress Review', label: 'Start review' }],
    Completed: [{ toState: 'Verified', label: 'Verify audit' }],
  },
}

function readErrorMessage(status: number, payload: ApiError | null) {
  const detail = payload?.detail
  if (typeof detail === 'string' && detail.trim()) return `HTTP ${status}: ${detail}`
  if (detail && typeof detail === 'object' && typeof detail.msg === 'string') return `HTTP ${status}: ${detail.msg}`
  return `HTTP ${status}: request failed`
}

function statusTone(authState: AuthState): { background: string; border: string } {
  if (authState === 'error') return { background: '#fbe5df', border: '#d77862' }
  if (authState === 'authenticated_ready') return { background: '#e5f0ea', border: '#6f927f' }
  return { background: '#f0ede2', border: '#c7b99d' }
}

function stateClassName(state: WorkflowState) {
  return `state-chip state-chip--${state.toLowerCase().replaceAll(' ', '-').replaceAll('/', '-')}`
}

function complianceClassName(status: ComplianceStatus) {
  return `segmented-choice segmented-choice--${status}`
}

function createNewChartForm(auditorName = '') {
  return {
    client_name: '',
    level_of_care: '',
    admission_date: '',
    discharge_date: '',
    primary_clinician: '',
    auditor_name: auditorName,
    other_details: '',
    notes: '',
  }
}

function copyChartDetail(detail: ChartDetail): ChartDetail {
  return {
    ...detail,
    checklist_items: detail.checklist_items.map((item) => ({ ...item })),
  }
}

function toChartSummary(detail: ChartDetail): ChartSummary {
  return {
    id: detail.id,
    client_name: detail.client_name,
    level_of_care: detail.level_of_care,
    admission_date: detail.admission_date,
    discharge_date: detail.discharge_date,
    primary_clinician: detail.primary_clinician,
    auditor_name: detail.auditor_name,
    other_details: detail.other_details,
    counselor_id: detail.counselor_id,
    state: detail.state,
    notes: detail.notes,
    pending_items: detail.pending_items,
    passed_items: detail.passed_items,
    failed_items: detail.failed_items,
    not_applicable_items: detail.not_applicable_items,
  }
}

function upsertChartSummary(charts: ChartSummary[], nextSummary: ChartSummary) {
  const exists = charts.some((chart) => chart.id === nextSummary.id)
  const nextCharts = exists
    ? charts.map((chart) => (chart.id === nextSummary.id ? nextSummary : chart))
    : [nextSummary, ...charts]
  return nextCharts.sort((left, right) => right.id - left.id)
}

function progressPercent(chart: Pick<ChartSummary, 'pending_items' | 'passed_items' | 'failed_items' | 'not_applicable_items'>) {
  const total = chart.pending_items + chart.passed_items + chart.failed_items + chart.not_applicable_items
  if (total === 0) return 0
  return Math.round(((total - chart.pending_items) / total) * 100)
}

function groupedChecklist(items: AuditItem[]) {
  const grouped = new Map<string, AuditItem[]>()
  items.forEach((item) => {
    const existing = grouped.get(item.section) || []
    existing.push(item)
    grouped.set(item.section, existing)
  })
  return Array.from(grouped.entries())
}

function availableTransitions(role: Role, state: WorkflowState) {
  return TRANSITION_MAP[role][state] || []
}

function flattenPlaybook(sections: AuditTemplateSection[]) {
  return sections.flatMap((section) => section.items)
}

export function App() {
  const [token, setToken] = useState('')
  const [status, setStatus] = useState('Ready to sign in. Enter your username and password to begin the chart audit workflow.')
  const [authState, setAuthState] = useState<AuthState>('anonymous')
  const [mustResetPassword, setMustResetPassword] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [chartSummaries, setChartSummaries] = useState<ChartSummary[]>([])
  const [templateSections, setTemplateSections] = useState<AuditTemplateSection[]>([])
  const [selectedChartId, setSelectedChartId] = useState<number | null>(null)
  const [chartDetail, setChartDetail] = useState<ChartDetail | null>(null)
  const [chartDraft, setChartDraft] = useState<ChartDetail | null>(null)
  const [showCreateAudit, setShowCreateAudit] = useState(false)
  const [transitionComment, setTransitionComment] = useState('')
  const [form, setForm] = useState({ username: 'admin', password: 'r3' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [newChartForm, setNewChartForm] = useState(createNewChartForm())

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])
  const playbookItems = useMemo(() => flattenPlaybook(templateSections), [templateSections])
  const groupedDraftItems = useMemo(() => groupedChecklist(chartDraft?.checklist_items || []), [chartDraft])

  function resetSession(message = 'Signed out. Session data cleared. Ready for a new login attempt.') {
    setToken('')
    setUser(null)
    setChartSummaries([])
    setTemplateSections([])
    setSelectedChartId(null)
    setChartDetail(null)
    setChartDraft(null)
    setShowCreateAudit(false)
    setTransitionComment('')
    setMustResetPassword(false)
    setAuthState('anonymous')
    setNewChartForm(createNewChartForm())
    setStatus(message)
  }

  async function fetchChartDetail(currentToken: string, chartId: number) {
    const response = await fetch(`${API}/charts/${chartId}`, {
      headers: { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' },
    })
    const payload = (await response.json().catch(() => null)) as ApiError | ChartDetail | null
    if (!response.ok) {
      throw new Error(readErrorMessage(response.status, payload as ApiError | null))
    }
    return payload as ChartDetail
  }

  async function loadWorkspace(currentToken: string, currentUser: User, initialMessage?: string) {
    setAuthState('authenticated_loading_profile')
    setStatus(initialMessage || `Welcome ${currentUser.username}. Loading your audit queue, playbook, and chart review workspace...`)

    const headers = { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' }
    const [chartsResponse, templateResponse] = await Promise.all([
      fetch(`${API}/charts`, { headers }),
      fetch(`${API}/audit-template`, { headers }),
    ])

    const chartsPayload = (await chartsResponse.json().catch(() => null)) as ApiError | ChartSummary[] | null
    const templatePayload = (await templateResponse.json().catch(() => null)) as ApiError | AuditTemplateSection[] | null

    if (!chartsResponse.ok) {
      setAuthState('error')
      setStatus(`Audit queue failed to load. ${readErrorMessage(chartsResponse.status, chartsPayload as ApiError | null)}`)
      return
    }
    if (!templateResponse.ok) {
      setAuthState('error')
      setStatus(`Audit playbook failed to load. ${readErrorMessage(templateResponse.status, templatePayload as ApiError | null)}`)
      return
    }

    const charts = (chartsPayload as ChartSummary[]) || []
    const sections = (templatePayload as AuditTemplateSection[]) || []
    setChartSummaries(charts)
    setTemplateSections(sections)
    setNewChartForm(createNewChartForm(currentUser.username))

    if (charts.length > 0) {
      const firstChart = await fetchChartDetail(currentToken, charts[0].id)
      setSelectedChartId(firstChart.id)
      setChartDetail(firstChart)
      setChartDraft(copyChartDetail(firstChart))
      setShowCreateAudit(false)
      setStatus(`Workspace ready. ${charts.length} audit${charts.length === 1 ? '' : 's'} in queue; review playbook loaded with ${playbookItems.length || sections.flatMap((section) => section.items).length} checklist steps.`)
    } else {
      setSelectedChartId(null)
      setChartDetail(null)
      setChartDraft(null)
      setShowCreateAudit(true)
      setStatus('Workspace ready. No chart audits are in the queue yet, so start by creating a new chart audit from the guided intake form.')
    }

    setAuthState('authenticated_ready')
  }

  async function loadProfileAndWorkspace(currentToken: string, expectsReset: boolean) {
    setAuthState('authenticated_loading_profile')
    setStatus('Authentication succeeded. Loading profile, role permissions, and chart audit workspace...')

    const me = await fetch(`${API}/users/me`, {
      headers: { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' },
    })
    const mePayload = (await me.json().catch(() => null)) as ApiError | User | null
    if (!me.ok) {
      setAuthState('error')
      setStatus(`Authentication token was issued, but profile load failed. ${readErrorMessage(me.status, mePayload as ApiError | null)}`)
      return
    }

    const currentUser = mePayload as User
    setUser(currentUser)

    if (expectsReset || currentUser.must_reset_password) {
      setMustResetPassword(true)
      setAuthState('password_reset_required')
      setStatus('Login verified. A password reset is required before chart audit tools are available.')
      return
    }

    await loadWorkspace(currentToken, currentUser)
  }

  async function login(e: FormEvent) {
    e.preventDefault()
    setAuthState('logging_in')
    setStatus(`Submitting credentials for "${form.username}". Waiting for authentication response...`)
    try {
      const response = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Login rejected for "${form.username}". ${readErrorMessage(response.status, payload)}`)
        return
      }

      const data = payload as { access_token: string; must_reset_password: boolean }
      setToken(data.access_token)
      setMustResetPassword(data.must_reset_password)
      await loadProfileAndWorkspace(data.access_token, data.must_reset_password)
    } catch {
      setAuthState('error')
      setStatus('Login failed before authentication could complete: backend unreachable. Verify API URL, container status, and port mapping.')
    }
  }

  async function resetPassword(e: FormEvent) {
    e.preventDefault()
    setStatus('Password reset request submitted. Validating new password and updating credentials...')
    try {
      const response = await fetch(`${API}/auth/reset-password`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ new_password: resetForm.newPassword }),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Password reset failed after authentication. ${readErrorMessage(response.status, payload)}`)
        return
      }
      setResetForm({ newPassword: '' })
      setMustResetPassword(false)
      setStatus('Password reset successful. Reloading your audit workspace...')
      await loadProfileAndWorkspace(token, false)
    } catch {
      setAuthState('error')
      setStatus('Password reset failed: backend unreachable or session expired. Please sign in again.')
    }
  }

  async function selectChart(chartId: number) {
    if (!token) return
    setStatus('Loading selected chart audit...')
    try {
      const detail = await fetchChartDetail(token, chartId)
      setSelectedChartId(detail.id)
      setChartDetail(detail)
      setChartDraft(copyChartDetail(detail))
      setShowCreateAudit(false)
      setTransitionComment('')
      setStatus(`Loaded chart audit for ${detail.client_name}. Review the step-by-step checklist and capture proof for each item.`)
    } catch (error) {
      setAuthState('error')
      setStatus(`Unable to load chart audit. ${error instanceof Error ? error.message : 'Unexpected error.'}`)
    }
  }

  async function createChart(e: FormEvent) {
    e.preventDefault()
    setStatus('Creating a new chart audit and loading the checklist template...')
    try {
      const response = await fetch(`${API}/charts`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(newChartForm),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | ChartDetail | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Unable to create chart audit. ${readErrorMessage(response.status, payload as ApiError | null)}`)
        return
      }

      const detail = payload as ChartDetail
      setChartSummaries((existing) => upsertChartSummary(existing, toChartSummary(detail)))
      setSelectedChartId(detail.id)
      setChartDetail(detail)
      setChartDraft(copyChartDetail(detail))
      setShowCreateAudit(false)
      setTransitionComment('')
      setNewChartForm(createNewChartForm(user?.username || detail.auditor_name))
      setAuthState('authenticated_ready')
      setStatus(`Chart audit created for ${detail.client_name}. Work top to bottom through the checklist before submitting it for review.`)
    } catch {
      setAuthState('error')
      setStatus('Chart creation failed: backend unreachable or request interrupted.')
    }
  }

  async function saveChart() {
    if (!chartDraft) return

    setStatus(`Saving audit for ${chartDraft.client_name}...`)
    try {
      const response = await fetch(`${API}/charts/${chartDraft.id}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({
          client_name: chartDraft.client_name,
          level_of_care: chartDraft.level_of_care,
          admission_date: chartDraft.admission_date,
          discharge_date: chartDraft.discharge_date,
          primary_clinician: chartDraft.primary_clinician,
          auditor_name: chartDraft.auditor_name,
          other_details: chartDraft.other_details,
          notes: chartDraft.notes,
          checklist_items: chartDraft.checklist_items.map((item) => ({
            item_key: item.item_key,
            status: item.status,
            notes: item.notes,
            evidence_location: item.evidence_location,
            evidence_date: item.evidence_date,
            expiration_date: item.expiration_date,
          })),
        }),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | ChartDetail | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Save failed. ${readErrorMessage(response.status, payload as ApiError | null)}`)
        return
      }

      const detail = payload as ChartDetail
      setChartDetail(detail)
      setChartDraft(copyChartDetail(detail))
      setChartSummaries((existing) => upsertChartSummary(existing, toChartSummary(detail)))
      setStatus(`Saved audit for ${detail.client_name}. ${detail.failed_items} failed item(s) and ${detail.pending_items} pending item(s) remain.`)
    } catch {
      setAuthState('error')
      setStatus('Save failed: backend unreachable or request interrupted.')
    }
  }

  async function applyTransition(action: TransitionAction) {
    if (!chartDraft) return
    if (action.requiresComment && !transitionComment.trim()) {
      setStatus('A return comment is required before sending an audit back for update.')
      return
    }

    setStatus(`${action.label} in progress for ${chartDraft.client_name}...`)
    try {
      const response = await fetch(`${API}/charts/${chartDraft.id}/transition`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ to_state: action.toState, comment: transitionComment }),
      })
      const payload = (await response.json().catch(() => null)) as ApiError | ChartDetail | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`State transition failed. ${readErrorMessage(response.status, payload as ApiError | null)}`)
        return
      }

      const detail = payload as ChartDetail
      setChartDetail(detail)
      setChartDraft(copyChartDetail(detail))
      setChartSummaries((existing) => upsertChartSummary(existing, toChartSummary(detail)))
      setTransitionComment('')
      setStatus(`Workflow updated. ${detail.client_name} is now "${detail.state}".`)
    } catch {
      setAuthState('error')
      setStatus('Workflow transition failed: backend unreachable or request interrupted.')
    }
  }

  function updateDraftField(field: keyof ChartDetail, value: string) {
    setChartDraft((current) => (current ? { ...current, [field]: value } : current))
  }

  function updateChecklistItem(itemKey: string, patch: Partial<AuditItem>) {
    setChartDraft((current) => {
      if (!current) return current
      return {
        ...current,
        checklist_items: current.checklist_items.map((item) => (item.item_key === itemKey ? { ...item, ...patch } : item)),
      }
    })
  }

  const tone = statusTone(authState)
  const transitionActions = user && chartDraft ? availableTransitions(user.role, chartDraft.state) : []
  const activeSummary = chartDraft || chartDetail
  const openIssues = (chartDraft?.checklist_items || []).filter((item) => item.status === 'no' || item.status === 'pending')

  return (
    <div className='app-shell'>
      <header className='topbar'>
        <div>
          <p className='eyebrow'>Clinical Audit Workflow</p>
          <h1>Chart Review Workflow</h1>
          <p className='subtitle'>Checklist-driven chart audits for counselors, office managers, and compliance reviewers.</p>
        </div>
        <div className='topbar-actions'>
          <div className='brand-lockup'>
            <span className='brand-dot' />
            <div>
              <strong>r3recoveryservices.com</strong>
              <p>Alleva chart audit workspace</p>
            </div>
          </div>
          {user ? <span className='role-chip'>{user.role}</span> : null}
          {token ? <button className='ghost-button' onClick={() => resetSession()}>Logout</button> : null}
        </div>
      </header>

      <div className='status-banner' style={{ background: tone.background, borderColor: tone.border }}>
        <strong>Status</strong>
        <span>{status}</span>
      </div>

      {(authState === 'anonymous' || authState === 'error') && !token ? (
        <section className='panel auth-panel'>
          <h2>Sign In</h2>
          <p className='panel-lead'>Use your chart audit account to open the guided review queue and checklist workspace.</p>
          <form className='stack-form' onSubmit={login}>
            <label>
              Username
              <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} placeholder='Username' />
            </label>
            <label>
              Password
              <input type='password' value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder='Password' />
            </label>
            <button type='submit' disabled={authState === 'logging_in'}>Sign in</button>
          </form>
        </section>
      ) : authState === 'logging_in' || authState === 'authenticated_loading_profile' ? (
        <section className='panel auth-panel'>
          <h2>Preparing Workspace</h2>
          <p className='panel-lead'>The system is validating credentials, loading your role permissions, and preparing the chart audit queue.</p>
        </section>
      ) : authState === 'password_reset_required' || (mustResetPassword && token) ? (
        <section className='panel auth-panel'>
          <h2>Password Reset Required</h2>
          <p className='panel-lead'>Authentication succeeded, but policy requires a new password before any chart audit data can be accessed.</p>
          <form className='stack-form' onSubmit={resetPassword}>
            <label>
              New password
              <input
                type='password'
                value={resetForm.newPassword}
                minLength={12}
                onChange={(event) => setResetForm({ newPassword: event.target.value })}
                placeholder='New password (min 12 chars)'
              />
            </label>
            <button type='submit' disabled={resetForm.newPassword.length < 12}>Reset password</button>
          </form>
        </section>
      ) : authState === 'authenticated_ready' && token && user ? (
        <div className='workspace-grid'>
          <aside className='sidebar'>
            <section className='panel'>
              <div className='panel-heading'>
                <div>
                  <p className='eyebrow'>Queue</p>
                  <h2>{user.role === 'admin' ? 'Admin Dashboard' : user.role === 'manager' ? 'Manager Dashboard' : 'Counselor Dashboard'}</h2>
                </div>
                <button className='secondary-button' onClick={() => {
                  setShowCreateAudit(true)
                  setSelectedChartId(null)
                  setChartDetail(null)
                  setChartDraft(null)
                  setTransitionComment('')
                  setNewChartForm(createNewChartForm(user.username))
                  setStatus('New chart audit form opened. Fill in the episode header before working through the checklist.')
                }}>
                  New chart audit
                </button>
              </div>
              <div className='queue-summary'>
                <div>
                  <span className='metric-value'>{chartSummaries.length}</span>
                  <span className='metric-label'>Active audits</span>
                </div>
                <div>
                  <span className='metric-value'>{chartSummaries.reduce((sum, chart) => sum + chart.failed_items, 0)}</span>
                  <span className='metric-label'>Failed items</span>
                </div>
                <div>
                  <span className='metric-value'>{chartSummaries.reduce((sum, chart) => sum + chart.pending_items, 0)}</span>
                  <span className='metric-label'>Pending items</span>
                </div>
              </div>
              <div className='queue-list'>
                {chartSummaries.length === 0 ? (
                  <div className='empty-queue'>
                    <strong>No audits in queue.</strong>
                    <p>Create a chart audit to start the guided review workflow.</p>
                  </div>
                ) : (
                  chartSummaries.map((chart) => (
                    <button
                      key={chart.id}
                      type='button'
                      className={`queue-card ${selectedChartId === chart.id ? 'queue-card--active' : ''}`}
                      onClick={() => void selectChart(chart.id)}
                    >
                      <div className='queue-card__header'>
                        <strong>{chart.client_name}</strong>
                        <span className={stateClassName(chart.state)}>{chart.state}</span>
                      </div>
                      <p>{chart.level_of_care || 'Level of care not entered yet'}</p>
                      <div className='queue-card__meta'>
                        <span>{chart.primary_clinician || 'No clinician listed'}</span>
                        <span>{progressPercent(chart)}% reviewed</span>
                      </div>
                      <div className='queue-card__counts'>
                        <span>Passed {chart.passed_items}</span>
                        <span>Failed {chart.failed_items}</span>
                        <span>Pending {chart.pending_items}</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </section>

            <section className='panel'>
              <div className='panel-heading'>
                <div>
                  <p className='eyebrow'>Playbook</p>
                  <h2>Combined Audit Flow</h2>
                </div>
              </div>
              <ol className='playbook-list'>
                {playbookItems.map((item) => (
                  <li key={item.key}>
                    <strong>Step {item.step}: {item.label}</strong>
                    <span>{item.section}</span>
                    <p>{item.instructions}</p>
                  </li>
                ))}
              </ol>
            </section>
          </aside>

          <main className='main-column'>
            {showCreateAudit ? (
              <section className='panel'>
                <div className='panel-heading'>
                  <div>
                    <p className='eyebrow'>Start</p>
                    <h2>New Chart Audit</h2>
                  </div>
                </div>
                <p className='panel-lead'>Capture the episode header first. The full checklist will load immediately after creation.</p>
                <form className='editor-grid' onSubmit={createChart}>
                  <label>
                    Client name
                    <input value={newChartForm.client_name} onChange={(event) => setNewChartForm({ ...newChartForm, client_name: event.target.value })} placeholder='Client name' />
                  </label>
                  <label>
                    Level of care
                    <input value={newChartForm.level_of_care} onChange={(event) => setNewChartForm({ ...newChartForm, level_of_care: event.target.value })} placeholder='IOP, PHP, Residential...' />
                  </label>
                  <label>
                    Admission date
                    <input value={newChartForm.admission_date} onChange={(event) => setNewChartForm({ ...newChartForm, admission_date: event.target.value })} placeholder='MM/DD/YYYY' />
                  </label>
                  <label>
                    Discharge date
                    <input value={newChartForm.discharge_date} onChange={(event) => setNewChartForm({ ...newChartForm, discharge_date: event.target.value })} placeholder='MM/DD/YYYY' />
                  </label>
                  <label>
                    Primary clinician
                    <input value={newChartForm.primary_clinician} onChange={(event) => setNewChartForm({ ...newChartForm, primary_clinician: event.target.value })} placeholder='Primary clinician' />
                  </label>
                  <label>
                    Auditor name
                    <input value={newChartForm.auditor_name} onChange={(event) => setNewChartForm({ ...newChartForm, auditor_name: event.target.value })} placeholder='Auditor name' />
                  </label>
                  <label className='editor-grid__full'>
                    Episode / other notes
                    <textarea value={newChartForm.other_details} onChange={(event) => setNewChartForm({ ...newChartForm, other_details: event.target.value })} placeholder='Use this field for episode-level context, multi-LOC notes, or anything that belongs in the form header.' />
                  </label>
                  <label className='editor-grid__full'>
                    Initial audit summary
                    <textarea value={newChartForm.notes} onChange={(event) => setNewChartForm({ ...newChartForm, notes: event.target.value })} placeholder='Optional handoff summary or opening notes for the reviewer.' />
                  </label>
                  <div className='editor-actions editor-grid__full'>
                    <button type='submit'>Create audit and load checklist</button>
                    {chartSummaries.length > 0 ? (
                      <button
                        type='button'
                        className='ghost-button'
                        onClick={() => {
                          setShowCreateAudit(false)
                          void selectChart(chartSummaries[0].id)
                        }}
                      >
                        Cancel and return to queue
                      </button>
                    ) : null}
                  </div>
                </form>
              </section>
            ) : chartDraft && activeSummary ? (
              <>
                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Active Audit</p>
                      <h2>{chartDraft.client_name || 'Untitled chart audit'}</h2>
                    </div>
                    <div className='panel-heading__actions'>
                      <span className={stateClassName(chartDraft.state)}>{chartDraft.state}</span>
                      <button onClick={() => void saveChart()}>Save audit</button>
                    </div>
                  </div>
                  <div className='queue-summary'>
                    <div>
                      <span className='metric-value'>{progressPercent(activeSummary)}%</span>
                      <span className='metric-label'>Checklist reviewed</span>
                    </div>
                    <div>
                      <span className='metric-value'>{activeSummary.failed_items}</span>
                      <span className='metric-label'>Failed items</span>
                    </div>
                    <div>
                      <span className='metric-value'>{activeSummary.pending_items}</span>
                      <span className='metric-label'>Pending items</span>
                    </div>
                  </div>

                  <div className='editor-grid'>
                    <label>
                      Client name
                      <input value={chartDraft.client_name} onChange={(event) => updateDraftField('client_name', event.target.value)} />
                    </label>
                    <label>
                      Level of care
                      <input value={chartDraft.level_of_care} onChange={(event) => updateDraftField('level_of_care', event.target.value)} />
                    </label>
                    <label>
                      Admission date
                      <input value={chartDraft.admission_date} onChange={(event) => updateDraftField('admission_date', event.target.value)} />
                    </label>
                    <label>
                      Discharge date
                      <input value={chartDraft.discharge_date} onChange={(event) => updateDraftField('discharge_date', event.target.value)} />
                    </label>
                    <label>
                      Primary clinician
                      <input value={chartDraft.primary_clinician} onChange={(event) => updateDraftField('primary_clinician', event.target.value)} />
                    </label>
                    <label>
                      Auditor name
                      <input value={chartDraft.auditor_name} onChange={(event) => updateDraftField('auditor_name', event.target.value)} />
                    </label>
                    <label className='editor-grid__full'>
                      Episode / other notes
                      <textarea value={chartDraft.other_details} onChange={(event) => updateDraftField('other_details', event.target.value)} />
                    </label>
                    <label className='editor-grid__full'>
                      Audit summary / handoff notes
                      <textarea value={chartDraft.notes} onChange={(event) => updateDraftField('notes', event.target.value)} />
                    </label>
                  </div>
                </section>

                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Focus</p>
                      <h2>Open Issues</h2>
                    </div>
                  </div>
                  {openIssues.length === 0 ? (
                    <p className='panel-lead'>No failed or pending items right now. This audit is ready for the next workflow step.</p>
                  ) : (
                    <div className='open-issue-list'>
                      {openIssues.slice(0, 5).map((item) => (
                        <div className='open-issue' key={item.item_key}>
                          <strong>Step {item.step}: {item.label}</strong>
                          <span>{STATUS_LABELS[item.status]}</span>
                          <p>{item.evidence_hint}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Checklist</p>
                      <h2>Review Criteria</h2>
                    </div>
                  </div>
                  <div className='section-stack'>
                    {groupedDraftItems.map(([sectionName, items]) => (
                      <section key={sectionName} className='checklist-section'>
                        <div className='checklist-section__header'>
                          <h3>{sectionName}</h3>
                          <span>{items.length} item{items.length === 1 ? '' : 's'}</span>
                        </div>
                        <div className='checklist-grid'>
                          {items.map((item) => (
                            <article key={item.item_key} className='checklist-card'>
                              <div className='checklist-card__header'>
                                <div>
                                  <p className='eyebrow'>Step {item.step}</p>
                                  <h4>{item.label}</h4>
                                  <p className='timeframe'>{item.timeframe}</p>
                                </div>
                                <div className='segmented-control' role='group' aria-label={`${item.label} status`}>
                                  {STATUS_ORDER.map((choice) => (
                                    <button
                                      key={choice}
                                      type='button'
                                      className={item.status === choice ? complianceClassName(choice) + ' segmented-choice--active' : complianceClassName(choice)}
                                      onClick={() => updateChecklistItem(item.item_key, { status: choice })}
                                    >
                                      {STATUS_LABELS[choice]}
                                    </button>
                                  ))}
                                </div>
                              </div>
                              <p>{item.instructions}</p>
                              <div className='hint-box'>
                                <strong>Proof standard</strong>
                                <p>{item.evidence_hint}</p>
                              </div>
                              {item.policy_note ? (
                                <div className='policy-box'>
                                  <strong>Policy still to define</strong>
                                  <p>{item.policy_note}</p>
                                </div>
                              ) : null}
                              <div className='editor-grid editor-grid--compact'>
                                <label>
                                  Location / tab
                                  <input value={item.evidence_location} onChange={(event) => updateChecklistItem(item.item_key, { evidence_location: event.target.value })} placeholder='Client Overview, Lab tab, Document Manager...' />
                                </label>
                                <label>
                                  Completed / signed date
                                  <input value={item.evidence_date} onChange={(event) => updateChecklistItem(item.item_key, { evidence_date: event.target.value })} placeholder='MM/DD/YYYY' />
                                </label>
                                <label>
                                  Expiry / renewal date
                                  <input value={item.expiration_date} onChange={(event) => updateChecklistItem(item.item_key, { expiration_date: event.target.value })} placeholder='Optional when applicable' />
                                </label>
                                <label className='editor-grid__full'>
                                  Reviewer notes
                                  <textarea value={item.notes} onChange={(event) => updateChecklistItem(item.item_key, { notes: event.target.value })} placeholder='Capture what was verified, what failed, or what follow-up is needed.' />
                                </label>
                              </div>
                            </article>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                </section>

                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Workflow</p>
                      <h2>Move Audit Forward</h2>
                    </div>
                  </div>
                  <p className='panel-lead'>Use the workflow controls after saving. Returning an audit requires a comment so counselors know exactly what to fix.</p>
                  <label className='editor-grid__full'>
                    Transition comment
                    <textarea value={transitionComment} onChange={(event) => setTransitionComment(event.target.value)} placeholder='Required for returns; optional for other transitions.' />
                  </label>
                  <div className='editor-actions'>
                    <button onClick={() => void saveChart()}>Save before transition</button>
                    {transitionActions.length === 0 ? <span className='empty-hint'>No workflow transition is available for your role in the current state.</span> : null}
                    {transitionActions.map((action) => (
                      <button
                        key={action.toState}
                        type='button'
                        className={action.requiresComment ? 'danger-button' : 'secondary-button'}
                        onClick={() => void applyTransition(action)}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                </section>
              </>
            ) : (
              <section className='panel'>
                <h2>Choose a Chart Audit</h2>
                <p className='panel-lead'>Select an audit from the queue or start a new one to load the checklist workspace.</p>
              </section>
            )}
          </main>
        </div>
      ) : (
        <section className='panel auth-panel'>
          <h2>Session issue detected</h2>
          <p className='panel-lead'>We could not finish loading your session. Check the status banner for details, then clear the session and try again.</p>
          <button onClick={() => resetSession('Session cleared after error. You can now attempt login again.')}>Clear session</button>
        </section>
      )}
    </div>
  )
}
