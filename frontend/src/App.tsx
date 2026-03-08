import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import './app.css'

const API = import.meta.env.VITE_API_URL || '/api'

type Role = 'admin' | 'counselor' | 'manager'
type WorkflowState =
  | 'Draft'
  | 'Awaiting Office Manager Review'
  | 'Returned to Counselor'
  | 'Approved by Office Manager'
type ComplianceStatus = 'pending' | 'yes' | 'no' | 'na'
type NoteSetStatus = 'active' | 'superseded'
type NoteSetUploadMode = 'initial' | 'update'
type AllevaBucket = 'custom_forms' | 'uploaded_documents' | 'portal_documents' | 'labs' | 'medications' | 'notes' | 'other'
type DocumentCompletionStatus = 'completed' | 'incomplete' | 'draft'
type AppView = 'reviews' | 'uploads' | 'users' | 'logs'

type User = {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
  is_locked: boolean
  must_reset_password: boolean
  last_login_at: string | null
  created_at: string | null
}

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
  source_note_set_id: number | null
  patient_id: string
  client_name: string
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  auditor_name: string
  other_details: string
  counselor_id: number
  state: WorkflowState
  system_score: number
  system_summary: string
  manager_comment: string
  reviewed_by_id: number | null
  system_generated_at: string | null
  reviewed_at: string | null
  notes: string
  pending_items: number
  passed_items: number
  failed_items: number
  not_applicable_items: number
}

type ChartDetail = ChartSummary & {
  checklist_items: AuditItem[]
}

type PatientNoteDocument = {
  id: number
  document_label: string
  original_filename: string
  content_type: string
  size_bytes: number
  sha256: string
  alleva_bucket: AllevaBucket
  document_type: string
  completion_status: DocumentCompletionStatus
  client_signed: boolean
  staff_signed: boolean
  document_date: string
  description: string
  created_at: string
}

type PatientNoteSetSummary = {
  id: number
  patient_id: string
  review_chart_id: number | null
  version: number
  status: NoteSetStatus
  upload_mode: NoteSetUploadMode
  source_system: string
  primary_clinician: string
  level_of_care: string
  admission_date: string
  discharge_date: string
  upload_notes: string
  created_at: string
  file_count: number
}

type PatientNoteSetDetail = PatientNoteSetSummary & {
  documents: PatientNoteDocument[]
}

type AuditLogRecord = {
  event_id: string
  timestamp_utc: string
  actor_username: string | null
  actor_role: string | null
  actor_type: string
  source_ip: string | null
  request_id: string
  event_category: string
  action: string
  patient_id: string | null
  message: string
  outcome_status: string
  severity: string
}

type UploadEntry = {
  file: File
  document_label: string
  alleva_bucket: AllevaBucket
  document_type: string
  completion_status: DocumentCompletionStatus
  client_signed: boolean
  staff_signed: boolean
  document_date: string
  description: string
}

type TransitionAction = {
  toState: WorkflowState
  label: string
  commentLabel: string
  requiresComment?: boolean
}

type ApiError = {
  detail?: string | { msg?: string }
}

const STATUS_LABELS: Record<ComplianceStatus, string> = {
  pending: 'Needs manual confirmation',
  yes: 'Confirmed',
  no: 'Missing or incorrect',
  na: 'Not applicable',
}

const NOTE_SET_STATUS_LABELS: Record<NoteSetStatus, string> = {
  active: 'Current binder',
  superseded: 'Superseded',
}

const VIEW_LABELS: Record<AppView, string> = {
  reviews: 'Review queue',
  uploads: 'Upload clinical notes',
  users: 'Users',
  logs: 'Forensic logs',
}

const TRANSITIONS: Record<Role, Partial<Record<WorkflowState, TransitionAction[]>>> = {
  admin: {
    'Awaiting Office Manager Review': [
      { toState: 'Approved by Office Manager', label: 'Approve', commentLabel: 'Approval note' },
      { toState: 'Returned to Counselor', label: 'Return to counselor', commentLabel: 'What needs to be fixed', requiresComment: true },
    ],
  },
  manager: {
    'Awaiting Office Manager Review': [
      { toState: 'Approved by Office Manager', label: 'Approve', commentLabel: 'Approval note' },
      { toState: 'Returned to Counselor', label: 'Return to counselor', commentLabel: 'What needs to be fixed', requiresComment: true },
    ],
  },
  counselor: {},
}

function readErrorMessage(status: number, payload: ApiError | null) {
  const detail = payload?.detail
  if (typeof detail === 'string' && detail.trim()) return `HTTP ${status}: ${detail}`
  if (detail && typeof detail === 'object' && typeof detail.msg === 'string') return `HTTP ${status}: ${detail.msg}`
  return `HTTP ${status}: request failed`
}

function groupedChecklist(items: AuditItem[]) {
  const groups = new Map<string, AuditItem[]>()
  items.forEach((item) => {
    const existing = groups.get(item.section) || []
    existing.push(item)
    groups.set(item.section, existing)
  })
  return Array.from(groups.entries())
}

function createUploadForm(overrides?: Partial<Omit<UploadFormState, 'entries'>>) {
  return {
    patient_id: '',
    upload_mode: 'initial' as NoteSetUploadMode,
    level_of_care: '',
    admission_date: '',
    discharge_date: '',
    primary_clinician: '',
    upload_notes: '',
    entries: [],
    ...overrides,
  }
}

function buildUploadEntry(file: File): UploadEntry {
  const label = file.name.replace(/\.[^.]+$/, '')
  return {
    file,
    document_label: label || file.name,
    alleva_bucket: 'custom_forms',
    document_type: 'clinical_note',
    completion_status: 'completed',
    client_signed: false,
    staff_signed: false,
    document_date: '',
    description: '',
  }
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function shortHash(value: string) {
  return value.length > 12 ? `${value.slice(0, 12)}...` : value
}

function workflowTone(state: string) {
  if (state === 'Approved by Office Manager') return 'success'
  if (state === 'Returned to Counselor') return 'danger'
  return 'neutral'
}

function checklistTone(status: ComplianceStatus) {
  if (status === 'yes') return 'success'
  if (status === 'no') return 'danger'
  if (status === 'na') return 'muted'
  return 'warning'
}

type UploadFormState = {
  patient_id: string
  upload_mode: NoteSetUploadMode
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  upload_notes: string
  entries: UploadEntry[]
}

type ManagedUserForm = {
  full_name: string
  role: Role
  is_active: boolean
  is_locked: boolean
  must_reset_password: boolean
}

type CreateUserForm = {
  username: string
  full_name: string
  password: string
  role: Role
}

type LogFilters = {
  patient_id: string
  action: string
}

async function readJson(response: Response) {
  const text = await response.text()
  if (!text) return null
  return JSON.parse(text)
}

export function App() {
  const [token, setToken] = useState('')
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState('Sign in to upload notes, review findings, and manage approvals.')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [mustResetPassword, setMustResetPassword] = useState(false)
  const [activeView, setActiveView] = useState<AppView>('reviews')

  const [loginForm, setLoginForm] = useState({ username: 'admin', password: 'r3!@analyzer#123' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [decisionComment, setDecisionComment] = useState('')

  const [charts, setCharts] = useState<ChartSummary[]>([])
  const [selectedChartId, setSelectedChartId] = useState<number | null>(null)
  const [selectedChart, setSelectedChart] = useState<ChartDetail | null>(null)

  const [noteSets, setNoteSets] = useState<PatientNoteSetSummary[]>([])
  const [selectedNoteSetId, setSelectedNoteSetId] = useState<number | null>(null)
  const [selectedNoteSet, setSelectedNoteSet] = useState<PatientNoteSetDetail | null>(null)
  const [uploadForm, setUploadForm] = useState<UploadFormState>(createUploadForm())

  const [users, setUsers] = useState<User[]>([])
  const [selectedManagedUserId, setSelectedManagedUserId] = useState<number | null>(null)
  const [managedUserForm, setManagedUserForm] = useState<ManagedUserForm | null>(null)
  const [newUserForm, setNewUserForm] = useState<CreateUserForm>({
    username: '',
    full_name: '',
    password: '',
    role: 'counselor',
  })
  const [adminPasswordReset, setAdminPasswordReset] = useState('')

  const [logs, setLogs] = useState<AuditLogRecord[]>([])
  const [logFilters, setLogFilters] = useState<LogFilters>({ patient_id: '', action: '' })

  const selectedManagedUser = useMemo(
    () => users.find((candidate) => candidate.id === selectedManagedUserId) || null,
    [users, selectedManagedUserId],
  )

  const groupedFindings = useMemo(() => groupedChecklist(selectedChart?.checklist_items || []), [selectedChart])
  const openItems = useMemo(
    () => (selectedChart?.checklist_items || []).filter((item) => item.status === 'no' || item.status === 'pending'),
    [selectedChart],
  )
  const pendingManagerQueue = useMemo(
    () => charts.filter((chart) => chart.state === 'Awaiting Office Manager Review'),
    [charts],
  )
  const transitionActions = useMemo(() => {
    if (!user || !selectedChart) return []
    return TRANSITIONS[user.role]?.[selectedChart.state] || []
  }, [selectedChart, user])

  async function apiRequest<T>(path: string, init?: RequestInit, includeAuth = true): Promise<T> {
    const headers = new Headers(init?.headers)
    if (includeAuth && token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API}${path}`, { ...init, headers })
    const payload = (await readJson(response)) as ApiError | T | null
    if (!response.ok) {
      throw new Error(readErrorMessage(response.status, payload as ApiError | null))
    }
    return payload as T
  }

  async function loadChartDetail(chartId: number) {
    const detail = await apiRequest<ChartDetail>(`/charts/${chartId}`)
    setSelectedChart(detail)
    setSelectedChartId(detail.id)
    if (detail.source_note_set_id) {
      setSelectedNoteSetId(detail.source_note_set_id)
      try {
        const noteSetDetail = await apiRequest<PatientNoteSetDetail>(`/patient-note-sets/${detail.source_note_set_id}`)
        setSelectedNoteSet(noteSetDetail)
      } catch {
        setSelectedNoteSet(null)
      }
    }
  }

  async function loadNoteSetDetail(noteSetId: number) {
    const detail = await apiRequest<PatientNoteSetDetail>(`/patient-note-sets/${noteSetId}`)
    setSelectedNoteSet(detail)
    setSelectedNoteSetId(detail.id)
  }

  async function loadUsers() {
    if (user?.role !== 'admin') return
    const nextUsers = await apiRequest<User[]>('/users')
    setUsers(nextUsers)
    const selectedId = selectedManagedUserId ?? nextUsers[0]?.id ?? null
    setSelectedManagedUserId(selectedId)
    const selected = nextUsers.find((candidate) => candidate.id === selectedId) || null
    setManagedUserForm(
      selected
        ? {
            full_name: selected.full_name,
            role: selected.role,
            is_active: selected.is_active,
            is_locked: selected.is_locked,
            must_reset_password: selected.must_reset_password,
          }
        : null,
    )
  }

  async function loadLogs() {
    if (user?.role !== 'admin') return
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (logFilters.patient_id.trim()) params.set('patient_id', logFilters.patient_id.trim())
    if (logFilters.action.trim()) params.set('action', logFilters.action.trim())
    const payload = await apiRequest<AuditLogRecord[]>(`/audit/logs?${params.toString()}`)
    setLogs(payload)
  }

  async function loadWorkspace() {
    if (!token) return
    setIsBusy(true)
    setError('')
    try {
      const [profile, chartList, noteSetList] = await Promise.all([
        apiRequest<User>('/users/me'),
        apiRequest<ChartSummary[]>('/charts'),
        apiRequest<PatientNoteSetSummary[]>('/patient-note-sets'),
      ])

      setUser(profile)
      setCharts(chartList)
      setNoteSets(noteSetList)
      if (profile.role === 'admin') {
        const directory = await apiRequest<User[]>('/users')
        setUsers(directory)
        const selected = directory[0] || null
        setSelectedManagedUserId(selected?.id ?? null)
        setManagedUserForm(
          selected
            ? {
                full_name: selected.full_name,
                role: selected.role,
                is_active: selected.is_active,
                is_locked: selected.is_locked,
                must_reset_password: selected.must_reset_password,
              }
            : null,
        )
      } else {
        setUsers([])
        setSelectedManagedUserId(null)
        setManagedUserForm(null)
      }

      const firstChartId = selectedChartId && chartList.some((chart) => chart.id === selectedChartId) ? selectedChartId : chartList[0]?.id ?? null
      const firstNoteSetId =
        selectedNoteSetId && noteSetList.some((noteSet) => noteSet.id === selectedNoteSetId) ? selectedNoteSetId : noteSetList[0]?.id ?? null

      if (firstChartId) {
        await loadChartDetail(firstChartId)
      } else {
        setSelectedChart(null)
        setSelectedChartId(null)
      }

      if (!firstChartId && firstNoteSetId) {
        await loadNoteSetDetail(firstNoteSetId)
      } else if (!firstNoteSetId) {
        setSelectedNoteSet(null)
        setSelectedNoteSetId(null)
      }

      setUploadForm((current) =>
        createUploadForm({
          patient_id: current.patient_id,
          upload_mode: current.upload_mode,
          level_of_care: current.level_of_care,
          admission_date: current.admission_date,
          discharge_date: current.discharge_date,
          primary_clinician: current.primary_clinician,
          upload_notes: current.upload_notes,
        }),
      )
      setStatus(`Workspace ready for ${profile.full_name || profile.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load workspace')
    } finally {
      setIsBusy(false)
    }
  }

  useEffect(() => {
    if (!token || mustResetPassword) return
    void loadWorkspace()
  }, [token, mustResetPassword])

  useEffect(() => {
    if (activeView === 'logs' && token && user?.role === 'admin' && !mustResetPassword) {
      void loadLogs()
    }
  }, [activeView, token, user, mustResetPassword])

  function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || [])
    setUploadForm((current) => ({
      ...current,
      entries: files.map((file) => buildUploadEntry(file)),
    }))
  }

  function updateUploadEntry(index: number, field: keyof UploadEntry, value: string | boolean) {
    setUploadForm((current) => ({
      ...current,
      entries: current.entries.map((entry, entryIndex) => {
        if (entryIndex !== index) return entry
        return { ...entry, [field]: value }
      }),
    }))
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    setStatus(`Signing in as ${loginForm.username}...`)
    try {
      const login = await apiRequest<{ access_token: string; must_reset_password: boolean }>(
        '/auth/login',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(loginForm),
        },
        false,
      )
      setToken(login.access_token)
      setMustResetPassword(login.must_reset_password)
      const profile = await apiRequest<User>('/users/me', { headers: { Authorization: `Bearer ${login.access_token}` } }, false)
      setUser(profile)
      if (login.must_reset_password) {
        setStatus('Password reset required before continuing.')
      } else {
        setStatus(`Signed in as ${profile.full_name || profile.username}. Loading workspace...`)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handlePasswordReset(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      await apiRequest(
        '/auth/reset-password',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: resetForm.newPassword }),
        },
      )
      setMustResetPassword(false)
      setResetForm({ newPassword: '' })
      setStatus('Password reset complete. Loading workspace...')
      await loadWorkspace()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Password reset failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!uploadForm.entries.length) {
      setError('Add at least one clinical note file before uploading.')
      return
    }

    setIsBusy(true)
    setError('')
    setStatus(`Uploading clinical notes for patient ${uploadForm.patient_id || 'pending'}...`)

    try {
      const body = new FormData()
      body.set('patient_id', uploadForm.patient_id)
      body.set('upload_mode', uploadForm.upload_mode)
      body.set('level_of_care', uploadForm.level_of_care)
      body.set('admission_date', uploadForm.admission_date)
      body.set('discharge_date', uploadForm.discharge_date)
      body.set('primary_clinician', uploadForm.primary_clinician)
      body.set('upload_notes', uploadForm.upload_notes)
      body.set(
        'file_manifest',
        JSON.stringify(
          uploadForm.entries.map((entry) => ({
            client_file_name: entry.file.name,
            document_label: entry.document_label,
            alleva_bucket: entry.alleva_bucket,
            document_type: entry.document_type,
            completion_status: entry.completion_status,
            client_signed: entry.client_signed,
            staff_signed: entry.staff_signed,
            document_date: entry.document_date,
            description: entry.description,
          })),
        ),
      )
      uploadForm.entries.forEach((entry) => body.append('files', entry.file))

      const uploaded = await apiRequest<PatientNoteSetDetail>('/patient-note-sets', {
        method: 'POST',
        body,
      })

      setUploadForm(
        createUploadForm({
          patient_id: uploaded.patient_id,
          upload_mode: 'update',
          level_of_care: uploaded.level_of_care,
          admission_date: uploaded.admission_date,
          discharge_date: uploaded.discharge_date,
          primary_clinician: uploaded.primary_clinician,
          upload_notes: '',
        }),
      )
      setSelectedNoteSet(uploaded)
      setSelectedNoteSetId(uploaded.id)
      setActiveView('reviews')
      await loadWorkspace()
      if (uploaded.review_chart_id) {
        await loadChartDetail(uploaded.review_chart_id)
      }
      setStatus(`Clinical notes uploaded for patient ${uploaded.patient_id}. The system review is ready for office-manager disposition.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleTransition(action: TransitionAction) {
    if (!selectedChart) return
    if (action.requiresComment && !decisionComment.trim()) {
      setError('Enter a manager comment before returning a chart to the counselor.')
      return
    }

    setIsBusy(true)
    setError('')
    setStatus(`${action.label} in progress for patient ${selectedChart.patient_id}...`)
    try {
      const updated = await apiRequest<ChartDetail>(`/charts/${selectedChart.id}/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_state: action.toState, comment: decisionComment }),
      })
      setSelectedChart(updated)
      setDecisionComment('')
      await loadWorkspace()
      setStatus(`Office-manager decision recorded for patient ${updated.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Transition failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleCreateUser(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<User>('/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUserForm),
      })
      setNewUserForm({ username: '', full_name: '', password: '', role: 'counselor' })
      await loadUsers()
      setStatus('User created successfully.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleSaveManagedUser(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser || !managedUserForm) return
    setIsBusy(true)
    setError('')
    try {
      const updated = await apiRequest<User>(`/users/${selectedManagedUser.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(managedUserForm),
      })
      await loadUsers()
      setSelectedManagedUserId(updated.id)
      setManagedUserForm({
        full_name: updated.full_name,
        role: updated.role,
        is_active: updated.is_active,
        is_locked: updated.is_locked,
        must_reset_password: updated.must_reset_password,
      })
      setStatus(`Updated user ${updated.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleAdminPasswordReset(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser || !adminPasswordReset.trim()) return
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<User>(`/users/${selectedManagedUser.id}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: adminPasswordReset, require_reset_on_login: true }),
      })
      setAdminPasswordReset('')
      await loadUsers()
      setStatus(`Password reset staged for ${selectedManagedUser.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to reset password')
    } finally {
      setIsBusy(false)
    }
  }

  function openRejectedPatientUpload(chart: ChartDetail) {
    setActiveView('uploads')
    setUploadForm(
      createUploadForm({
        patient_id: chart.patient_id,
        upload_mode: 'update',
        level_of_care: chart.level_of_care,
        admission_date: chart.admission_date,
        discharge_date: chart.discharge_date,
        primary_clinician: chart.primary_clinician,
        upload_notes: chart.manager_comment ? `Manager follow-up: ${chart.manager_comment}` : '',
      }),
    )
  }

  function handleSelectManagedUser(nextId: number) {
    setSelectedManagedUserId(nextId)
    const next = users.find((candidate) => candidate.id === nextId) || null
    setManagedUserForm(
      next
        ? {
            full_name: next.full_name,
            role: next.role,
            is_active: next.is_active,
            is_locked: next.is_locked,
            must_reset_password: next.must_reset_password,
          }
        : null,
    )
    setAdminPasswordReset('')
  }

  const totalPending = pendingManagerQueue.length
  const totalRejected = charts.filter((chart) => chart.state === 'Returned to Counselor').length
  const totalApproved = charts.filter((chart) => chart.state === 'Approved by Office Manager').length

  const linkedNoteSet =
    selectedChart?.source_note_set_id != null ? noteSets.find((noteSet) => noteSet.id === selectedChart.source_note_set_id) || null : null

  return (
    <main className='shell'>
      <section className='hero'>
        <div>
          <p className='eyebrow'>Clinical note analyzer</p>
          <h1>Upload notes, let the system audit them, then route the result to office-manager approval.</h1>
          <p className='hero-copy'>
            Counselors upload the latest clinical binder. The system evaluates the content against the audit rules, records every event in the
            forensic log, and places the result into a final approval queue for the office manager.
          </p>
        </div>
        <div className='status-card'>
          <h2>Current status</h2>
          <p>{status}</p>
          {error ? <p className='error-text'>{error}</p> : null}
          {user ? (
            <div className='status-meta'>
              <span>{user.full_name || user.username}</span>
              <span>{user.role}</span>
            </div>
          ) : null}
        </div>
      </section>

      {!token ? (
        <section className='auth-grid'>
          <form className='panel form-panel' onSubmit={handleLogin}>
            <h2>Sign in</h2>
            <label>
              Username
              <input value={loginForm.username} onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))} />
            </label>
            <label>
              Password
              <input
                type='password'
                value={loginForm.password}
                onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
              />
            </label>
            <button type='submit' disabled={isBusy}>
              {isBusy ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <div className='panel info-panel'>
            <h2>Workflow</h2>
            <ol>
              <li>Counselor uploads a patient note binder using patient ID.</li>
              <li>The app runs an automatic clinical-note checklist evaluation.</li>
              <li>The office manager approves or returns the chart for correction.</li>
              <li>Every read, write, approval, and change is written to the forensic log.</li>
            </ol>
          </div>
        </section>
      ) : mustResetPassword ? (
        <section className='panel form-panel narrow'>
          <h2>Password reset required</h2>
          <p>This applies to managed user accounts. The bootstrap admin password is fixed outside the app.</p>
          <form onSubmit={handlePasswordReset}>
            <label>
              New password
              <input
                type='password'
                placeholder='New password (min 12 chars)'
                value={resetForm.newPassword}
                onChange={(event) => setResetForm({ newPassword: event.target.value })}
              />
            </label>
            <button type='submit' disabled={isBusy}>
              {isBusy ? 'Saving...' : 'Reset password'}
            </button>
          </form>
        </section>
      ) : (
        <>
          <section className='metrics'>
            <article className='metric-card'>
              <span>Awaiting manager</span>
              <strong>{totalPending}</strong>
            </article>
            <article className='metric-card'>
              <span>Returned</span>
              <strong>{totalRejected}</strong>
            </article>
            <article className='metric-card'>
              <span>Approved</span>
              <strong>{totalApproved}</strong>
            </article>
            <article className='metric-card'>
              <span>Binders</span>
              <strong>{noteSets.length}</strong>
            </article>
          </section>

          <nav className='view-tabs'>
            {(['reviews', 'uploads'] as AppView[]).map((view) => (
              <button
                key={view}
                className={activeView === view ? 'tab-button tab-button--active' : 'tab-button'}
                onClick={() => setActiveView(view)}
                type='button'
              >
                {VIEW_LABELS[view]}
              </button>
            ))}
            {user?.role === 'admin'
              ? (['users', 'logs'] as AppView[]).map((view) => (
                  <button
                    key={view}
                    className={activeView === view ? 'tab-button tab-button--active' : 'tab-button'}
                    onClick={() => setActiveView(view)}
                    type='button'
                  >
                    {VIEW_LABELS[view]}
                  </button>
                ))
              : null}
          </nav>

          {activeView === 'reviews' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <h2>Automated review queue</h2>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
                {charts.length ? (
                  <ul className='queue-list'>
                    {charts.map((chart) => (
                      <li key={chart.id}>
                        <button
                          type='button'
                          className={selectedChartId === chart.id ? 'queue-item queue-item--active' : 'queue-item'}
                          onClick={() => void loadChartDetail(chart.id)}
                        >
                          <div>
                            <strong>{chart.patient_id}</strong>
                            <span>{chart.primary_clinician || 'Clinician pending'}</span>
                          </div>
                          <div className='queue-item-meta'>
                            <span className={`pill pill--${workflowTone(chart.state)}`}>{chart.state}</span>
                            <span>{chart.system_score}% ready</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className='empty-state'>No review charts yet. Upload a clinical note binder to generate the first automated review.</p>
                )}
              </aside>

              <section className='panel detail-panel'>
                {selectedChart ? (
                  <>
                    <div className='panel-heading'>
                      <div>
                        <h2>Patient {selectedChart.patient_id}</h2>
                        <p>{selectedChart.system_summary}</p>
                      </div>
                      <span className={`pill pill--${workflowTone(selectedChart.state)}`}>{selectedChart.state}</span>
                    </div>

                    <div className='detail-grid'>
                      <article className='mini-card'>
                        <span>Primary clinician</span>
                        <strong>{selectedChart.primary_clinician || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>Level of care</span>
                        <strong>{selectedChart.level_of_care || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>Admission</span>
                        <strong>{selectedChart.admission_date || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>System score</span>
                        <strong>{selectedChart.system_score}%</strong>
                      </article>
                    </div>

                    <section className='panel-subsection'>
                      <h3>Open issues</h3>
                      {openItems.length ? (
                        <ul className='issue-list'>
                          {openItems.map((item) => (
                            <li key={item.item_key} className={`issue issue--${checklistTone(item.status)}`}>
                              <div>
                                <strong>{item.label}</strong>
                                <p>{item.notes || item.instructions}</p>
                              </div>
                              <span>{STATUS_LABELS[item.status]}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className='empty-state'>No open issues detected in the current automated review.</p>
                      )}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Checklist findings</h3>
                      {groupedFindings.map(([section, items]) => (
                        <div key={section} className='finding-group'>
                          <h4>{section}</h4>
                          <div className='finding-list'>
                            {items.map((item) => (
                              <article key={item.item_key} className='finding-card'>
                                <div className='finding-card__header'>
                                  <strong>
                                    Step {item.step}. {item.label}
                                  </strong>
                                  <span className={`pill pill--${checklistTone(item.status)}`}>{STATUS_LABELS[item.status]}</span>
                                </div>
                                <p>{item.notes || item.instructions}</p>
                                <dl>
                                  <div>
                                    <dt>Evidence</dt>
                                    <dd>{item.evidence_location || 'System could not pin a precise location.'}</dd>
                                  </div>
                                  <div>
                                    <dt>Date</dt>
                                    <dd>{item.evidence_date || 'Not detected'}</dd>
                                  </div>
                                  <div>
                                    <dt>Policy note</dt>
                                    <dd>{item.policy_note || 'No extra policy note for this rule.'}</dd>
                                  </div>
                                </dl>
                              </article>
                            ))}
                          </div>
                        </div>
                      ))}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Office manager disposition</h3>
                      {selectedChart.manager_comment ? <p className='manager-comment'>{selectedChart.manager_comment}</p> : null}
                      {transitionActions.length ? (
                        <div className='decision-box'>
                          <label>
                            Manager comment
                            <textarea
                              value={decisionComment}
                              placeholder='Record final approval context or describe what the counselor needs to fix.'
                              onChange={(event) => setDecisionComment(event.target.value)}
                            />
                          </label>
                          <div className='decision-actions'>
                            {transitionActions.map((action) => (
                              <button key={action.toState} type='button' onClick={() => void handleTransition(action)} disabled={isBusy}>
                                {action.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : user?.role === 'counselor' && selectedChart.state === 'Returned to Counselor' ? (
                        <div className='decision-box'>
                          <p>The office manager returned this chart. Upload a corrected binder version to generate a fresh automated review.</p>
                          <button type='button' onClick={() => openRejectedPatientUpload(selectedChart)}>
                            Upload corrected notes
                          </button>
                        </div>
                      ) : (
                        <p className='empty-state'>No approval action is available for this chart in your current role.</p>
                      )}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Linked note binder</h3>
                      {linkedNoteSet ? (
                        <div className='linked-note'>
                          <p>
                            Version {linkedNoteSet.version} from {formatDateTime(linkedNoteSet.created_at)} with {linkedNoteSet.file_count} file(s).
                          </p>
                          <button type='button' className='ghost-button' onClick={() => void loadNoteSetDetail(linkedNoteSet.id)}>
                            Open binder details
                          </button>
                        </div>
                      ) : (
                        <p className='empty-state'>No uploaded binder is linked to this chart.</p>
                      )}
                    </section>
                  </>
                ) : (
                  <div className='empty-state-block'>
                    <h2>No automated review selected</h2>
                    <p>Upload a binder or choose a chart from the queue to inspect the system findings.</p>
                  </div>
                )}
              </section>
            </section>
          ) : null}

          {activeView === 'uploads' ? (
            <section className='workspace-grid'>
              <section className='panel detail-panel'>
                <h2>Upload clinical notes</h2>
                <p>
                  Use the patient ID as the source-of-truth key. Each upload creates a new immutable binder version and a new automated review record.
                </p>
                <form className='form-grid' onSubmit={handleUpload}>
                  <label>
                    Patient ID
                    <input value={uploadForm.patient_id} onChange={(event) => setUploadForm((current) => ({ ...current, patient_id: event.target.value }))} />
                  </label>
                  <label>
                    Upload mode
                    <select
                      value={uploadForm.upload_mode}
                      onChange={(event) =>
                        setUploadForm((current) => ({ ...current, upload_mode: event.target.value as NoteSetUploadMode }))
                      }
                    >
                      <option value='initial'>Initial binder</option>
                      <option value='update'>Updated binder</option>
                    </select>
                  </label>
                  <label>
                    Level of care
                    <input value={uploadForm.level_of_care} onChange={(event) => setUploadForm((current) => ({ ...current, level_of_care: event.target.value }))} />
                  </label>
                  <label>
                    Primary clinician
                    <input
                      value={uploadForm.primary_clinician}
                      onChange={(event) => setUploadForm((current) => ({ ...current, primary_clinician: event.target.value }))}
                    />
                  </label>
                  <label>
                    Admission date
                    <input
                      value={uploadForm.admission_date}
                      onChange={(event) => setUploadForm((current) => ({ ...current, admission_date: event.target.value }))}
                    />
                  </label>
                  <label>
                    Discharge date
                    <input
                      value={uploadForm.discharge_date}
                      onChange={(event) => setUploadForm((current) => ({ ...current, discharge_date: event.target.value }))}
                    />
                  </label>
                  <label className='full-width'>
                    Upload notes
                    <textarea
                      value={uploadForm.upload_notes}
                      onChange={(event) => setUploadForm((current) => ({ ...current, upload_notes: event.target.value }))}
                    />
                  </label>
                  <label className='full-width'>
                    Clinical note files
                    <input multiple type='file' onChange={handleFilesSelected} />
                  </label>
                  {uploadForm.entries.length ? (
                    <div className='full-width file-editor'>
                      <h3>Binder file metadata</h3>
                      {uploadForm.entries.map((entry, index) => (
                        <article key={`${entry.file.name}-${index}`} className='file-editor-row'>
                          <div className='file-editor-row__title'>
                            <strong>{entry.file.name}</strong>
                            <span>{Math.round(entry.file.size / 1024)} KB</span>
                          </div>
                          <div className='file-editor-row__fields'>
                            <label>
                              Label
                              <input value={entry.document_label} onChange={(event) => updateUploadEntry(index, 'document_label', event.target.value)} />
                            </label>
                            <label>
                              Bucket
                              <select
                                value={entry.alleva_bucket}
                                onChange={(event) => updateUploadEntry(index, 'alleva_bucket', event.target.value as AllevaBucket)}
                              >
                                <option value='custom_forms'>Custom Forms</option>
                                <option value='uploaded_documents'>Uploaded Documents</option>
                                <option value='portal_documents'>Portal Documents</option>
                                <option value='labs'>Labs</option>
                                <option value='medications'>Medications</option>
                                <option value='notes'>Notes</option>
                                <option value='other'>Other</option>
                              </select>
                            </label>
                            <label>
                              Completion
                              <select
                                value={entry.completion_status}
                                onChange={(event) => updateUploadEntry(index, 'completion_status', event.target.value as DocumentCompletionStatus)}
                              >
                                <option value='completed'>Completed</option>
                                <option value='incomplete'>Incomplete</option>
                                <option value='draft'>Draft</option>
                              </select>
                            </label>
                            <label>
                              Document date
                              <input value={entry.document_date} onChange={(event) => updateUploadEntry(index, 'document_date', event.target.value)} />
                            </label>
                            <label className='checkbox-row'>
                              <input
                                type='checkbox'
                                checked={entry.client_signed}
                                onChange={(event) => updateUploadEntry(index, 'client_signed', event.target.checked)}
                              />
                              Client signed
                            </label>
                            <label className='checkbox-row'>
                              <input
                                type='checkbox'
                                checked={entry.staff_signed}
                                onChange={(event) => updateUploadEntry(index, 'staff_signed', event.target.checked)}
                              />
                              Staff signed
                            </label>
                            <label className='full-width'>
                              Description
                              <input value={entry.description} onChange={(event) => updateUploadEntry(index, 'description', event.target.value)} />
                            </label>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : null}
                  <div className='full-width form-actions'>
                    <button type='submit' disabled={isBusy}>
                      {isBusy ? 'Uploading...' : 'Upload and run automated evaluation'}
                    </button>
                  </div>
                </form>
              </section>

              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <h2>Uploaded binders</h2>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
                {noteSets.length ? (
                  <ul className='queue-list'>
                    {noteSets.map((noteSet) => (
                      <li key={noteSet.id}>
                        <button
                          type='button'
                          className={selectedNoteSetId === noteSet.id ? 'queue-item queue-item--active' : 'queue-item'}
                          onClick={() => void loadNoteSetDetail(noteSet.id)}
                        >
                          <div>
                            <strong>{noteSet.patient_id}</strong>
                            <span>Version {noteSet.version}</span>
                          </div>
                          <div className='queue-item-meta'>
                            <span className='pill pill--neutral'>{NOTE_SET_STATUS_LABELS[noteSet.status]}</span>
                            <span>{noteSet.file_count} files</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className='empty-state'>No clinical note binders have been uploaded yet.</p>
                )}

                {selectedNoteSet ? (
                  <section className='panel-subsection'>
                    <h3>Binder details</h3>
                    <p>
                      Patient {selectedNoteSet.patient_id}, version {selectedNoteSet.version}, uploaded {formatDateTime(selectedNoteSet.created_at)}.
                    </p>
                    <p>{selectedNoteSet.upload_notes || 'No binder notes were entered.'}</p>
                    {selectedNoteSet.review_chart_id ? (
                      <button type='button' onClick={() => void loadChartDetail(selectedNoteSet.review_chart_id!)}>
                        Open automated review
                      </button>
                    ) : null}
                    <div className='document-list'>
                      {selectedNoteSet.documents.map((document) => (
                        <article key={document.id} className='document-card'>
                          <strong>{document.document_label}</strong>
                          <p>{document.original_filename}</p>
                          <p>{document.document_date || 'Date not supplied'}</p>
                          <span>{shortHash(document.sha256)}</span>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}
              </aside>
            </section>
          ) : null}

          {activeView === 'users' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <h2>User management</h2>
                  <button type='button' className='ghost-button' onClick={() => void loadUsers()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
                <ul className='queue-list'>
                  {users.map((managedUser) => (
                    <li key={managedUser.id}>
                      <button
                        type='button'
                        className={selectedManagedUserId === managedUser.id ? 'queue-item queue-item--active' : 'queue-item'}
                        onClick={() => handleSelectManagedUser(managedUser.id)}
                      >
                        <div>
                          <strong>{managedUser.full_name || managedUser.username}</strong>
                          <span>{managedUser.username}</span>
                        </div>
                        <div className='queue-item-meta'>
                          <span className='pill pill--neutral'>{managedUser.role}</span>
                          <span>{managedUser.is_active ? 'Active' : 'Inactive'}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              </aside>

              <section className='panel detail-panel'>
                <h2>Create user</h2>
                <form className='form-grid' onSubmit={handleCreateUser}>
                  <label>
                    Username
                    <input
                      value={newUserForm.username}
                      onChange={(event) => setNewUserForm((current) => ({ ...current, username: event.target.value }))}
                    />
                  </label>
                  <label>
                    Full name
                    <input
                      value={newUserForm.full_name}
                      onChange={(event) => setNewUserForm((current) => ({ ...current, full_name: event.target.value }))}
                    />
                  </label>
                  <label>
                    Role
                    <select value={newUserForm.role} onChange={(event) => setNewUserForm((current) => ({ ...current, role: event.target.value as Role }))}>
                      <option value='counselor'>Counselor</option>
                      <option value='manager'>Office manager</option>
                      <option value='admin'>Admin</option>
                    </select>
                  </label>
                  <label>
                    Temporary password
                    <input
                      type='password'
                      value={newUserForm.password}
                      onChange={(event) => setNewUserForm((current) => ({ ...current, password: event.target.value }))}
                    />
                  </label>
                  <div className='full-width form-actions'>
                    <button type='submit' disabled={isBusy}>
                      Create user
                    </button>
                  </div>
                </form>

                {selectedManagedUser && managedUserForm ? (
                  <>
                    <section className='panel-subsection'>
                      <h3>Edit selected user</h3>
                      <form className='form-grid' onSubmit={handleSaveManagedUser}>
                        <label>
                          Full name
                          <input
                            value={managedUserForm.full_name}
                            onChange={(event) => setManagedUserForm((current) => (current ? { ...current, full_name: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Role
                          <select
                            value={managedUserForm.role}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, role: event.target.value as Role } : current))
                            }
                          >
                            <option value='counselor'>Counselor</option>
                            <option value='manager'>Office manager</option>
                            <option value='admin'>Admin</option>
                          </select>
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.is_active}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, is_active: event.target.checked } : current))
                            }
                          />
                          Active
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.is_locked}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, is_locked: event.target.checked } : current))
                            }
                          />
                          Locked
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.must_reset_password}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, must_reset_password: event.target.checked } : current))
                            }
                          />
                          Force password reset at next login
                        </label>
                        <div className='full-width form-actions'>
                          <button type='submit' disabled={isBusy}>
                            Save changes
                          </button>
                        </div>
                      </form>
                    </section>

                    <section className='panel-subsection'>
                      <h3>Admin password reset</h3>
                      <form className='form-grid' onSubmit={handleAdminPasswordReset}>
                        <label className='full-width'>
                          New temporary password
                          <input type='password' value={adminPasswordReset} onChange={(event) => setAdminPasswordReset(event.target.value)} />
                        </label>
                        <div className='full-width form-actions'>
                          <button type='submit' disabled={isBusy}>
                            Reset password and require login reset
                          </button>
                        </div>
                      </form>
                      <p className='muted-text'>Last login: {formatDateTime(selectedManagedUser.last_login_at)}</p>
                    </section>
                  </>
                ) : (
                  <p className='empty-state'>Select a user to manage account status, role, and password recovery.</p>
                )}
              </section>
            </section>
          ) : null}

          {activeView === 'logs' && user?.role === 'admin' ? (
            <section className='panel detail-panel'>
              <div className='panel-heading'>
                <div>
                  <h2>Forensic audit logs</h2>
                  <p>Admin-only access to request, data-change, authentication, workflow, and upload events.</p>
                </div>
                <button type='button' className='ghost-button' onClick={() => void loadLogs()} disabled={isBusy}>
                  Refresh
                </button>
              </div>

              <form
                className='filter-row'
                onSubmit={(event) => {
                  event.preventDefault()
                  void loadLogs()
                }}
              >
                <label>
                  Patient ID
                  <input value={logFilters.patient_id} onChange={(event) => setLogFilters((current) => ({ ...current, patient_id: event.target.value }))} />
                </label>
                <label>
                  Action
                  <input value={logFilters.action} onChange={(event) => setLogFilters((current) => ({ ...current, action: event.target.value }))} />
                </label>
                <button type='submit' disabled={isBusy}>
                  Filter logs
                </button>
              </form>

              {logs.length ? (
                <div className='log-table'>
                  {logs.map((log) => (
                    <article key={log.event_id} className='log-row'>
                      <div className='log-row__meta'>
                        <strong>{log.action}</strong>
                        <span>{formatDateTime(log.timestamp_utc)}</span>
                      </div>
                      <p>{log.message}</p>
                      <div className='log-row__details'>
                        <span>Actor: {log.actor_username || log.actor_type}</span>
                        <span>Patient: {log.patient_id || 'n/a'}</span>
                        <span>IP: {log.source_ip || 'n/a'}</span>
                        <span>Request: {log.request_id}</span>
                        <span>{log.event_category}</span>
                        <span className={`pill pill--${log.outcome_status === 'success' ? 'success' : 'danger'}`}>{log.outcome_status}</span>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className='empty-state'>No audit logs matched the current filters.</p>
              )}
            </section>
          ) : null}
        </>
      )}
    </main>
  )
}

export default App
