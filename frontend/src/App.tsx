import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
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
type AppView = 'dashboard' | 'reviews' | 'uploads' | 'profile' | 'users' | 'logs' | 'settings'

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
  created_at: string | null
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
  details: string
  outcome_status: string
  severity: string
}

type AppSettings = {
  organization_name: string
  access_intel_enabled: boolean
  access_geo_lookup_url: string
  access_reputation_url: string
  access_reputation_api_key_configured: boolean
  access_lookup_timeout_seconds: number
  llm_enabled: boolean
  llm_provider_name: string
  llm_base_url: string
  llm_model: string
  llm_api_key_configured: boolean
  llm_use_for_access_review: boolean
  llm_use_for_evaluation_gap_analysis: boolean
  llm_analysis_instructions: string
  updated_by_id: number | null
  updated_at: string | null
}

type AppSettingsForm = {
  organization_name: string
  access_intel_enabled: boolean
  access_geo_lookup_url: string
  access_reputation_url: string
  access_reputation_api_key: string
  clear_access_reputation_api_key: boolean
  access_lookup_timeout_seconds: number
  llm_enabled: boolean
  llm_provider_name: string
  llm_base_url: string
  llm_model: string
  llm_api_key: string
  clear_llm_api_key: boolean
  llm_use_for_access_review: boolean
  llm_use_for_evaluation_gap_analysis: boolean
  llm_analysis_instructions: string
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

type PatientIdDetection = {
  patient_id: string | null
  confidence: string
  source_filename: string | null
  source_kind: string | null
  match_text: string | null
  reason: string
  was_autofilled: boolean
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
  event_category: string
}

type UserFilters = {
  query: string
  role: 'all' | Role
}

type ProfileForm = {
  full_name: string
}

type PasswordChangeForm = {
  current_password: string
  new_password: string
}

type TrendPoint = {
  label: string
  count: number
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
  dashboard: 'Summary dashboard',
  reviews: 'Review queue',
  uploads: 'Upload clinical notes',
  profile: 'My account',
  users: 'User management',
  logs: 'Forensic logs',
  settings: 'Settings',
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

function createSettingsForm(settings: AppSettings): AppSettingsForm {
  return {
    organization_name: settings.organization_name,
    access_intel_enabled: settings.access_intel_enabled,
    access_geo_lookup_url: settings.access_geo_lookup_url,
    access_reputation_url: settings.access_reputation_url,
    access_reputation_api_key: '',
    clear_access_reputation_api_key: false,
    access_lookup_timeout_seconds: settings.access_lookup_timeout_seconds,
    llm_enabled: settings.llm_enabled,
    llm_provider_name: settings.llm_provider_name,
    llm_base_url: settings.llm_base_url,
    llm_model: settings.llm_model,
    llm_api_key: '',
    clear_llm_api_key: false,
    llm_use_for_access_review: settings.llm_use_for_access_review,
    llm_use_for_evaluation_gap_analysis: settings.llm_use_for_evaluation_gap_analysis,
    llm_analysis_instructions: settings.llm_analysis_instructions,
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

function parseLogDetails(details: string) {
  try {
    const parsed = JSON.parse(details)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
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

function copyChartDetail(detail: ChartDetail): ChartDetail {
  return {
    ...detail,
    checklist_items: detail.checklist_items.map((item) => ({ ...item })),
  }
}

function toChartUpdatePayload(detail: ChartDetail) {
  return {
    patient_id: detail.patient_id,
    client_name: detail.client_name,
    level_of_care: detail.level_of_care,
    admission_date: detail.admission_date,
    discharge_date: detail.discharge_date,
    primary_clinician: detail.primary_clinician,
    auditor_name: detail.auditor_name,
    other_details: detail.other_details,
    notes: detail.notes,
    checklist_items: detail.checklist_items.map((item) => ({
      item_key: item.item_key,
      status: item.status,
      notes: item.notes,
      evidence_location: item.evidence_location,
      evidence_date: item.evidence_date,
      expiration_date: item.expiration_date,
    })),
  }
}

function isBootstrapAdmin(user: User | null) {
  return user?.username === 'admin'
}

function userStatusLabel(candidate: Pick<User, 'is_active' | 'is_locked'>) {
  if (!candidate.is_active) return 'Inactive'
  if (candidate.is_locked) return 'Locked'
  return 'Active'
}

function userStatusTone(candidate: Pick<User, 'is_active' | 'is_locked'>) {
  if (!candidate.is_active || candidate.is_locked) return 'danger'
  return 'success'
}

function validateCreateUserForm(form: CreateUserForm) {
  if (!form.username.trim()) return 'Username is required.'
  if (form.password.trim().length < 12) return 'Temporary password must be at least 12 characters.'
  return ''
}

function buildTrend(points: (string | null | undefined)[], lookbackDays = 7): TrendPoint[] {
  const now = new Date()
  const dayKeys: string[] = []
  const counts = new Map<string, number>()

  for (let offset = lookbackDays - 1; offset >= 0; offset -= 1) {
    const day = new Date(now)
    day.setHours(0, 0, 0, 0)
    day.setDate(now.getDate() - offset)
    const key = day.toISOString().slice(0, 10)
    dayKeys.push(key)
    counts.set(key, 0)
  }

  points.forEach((raw) => {
    if (!raw) return
    const day = new Date(raw)
    if (Number.isNaN(day.getTime())) return
    const key = day.toISOString().slice(0, 10)
    if (!counts.has(key)) return
    counts.set(key, (counts.get(key) || 0) + 1)
  })

  return dayKeys.map((key) => {
    const day = new Date(`${key}T00:00:00`)
    return {
      label: day.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      count: counts.get(key) || 0,
    }
  })
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
  const [activeView, setActiveView] = useState<AppView>('dashboard')

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [decisionComment, setDecisionComment] = useState('')
  const [reviewDirty, setReviewDirty] = useState(false)
  const [selectedFindingKey, setSelectedFindingKey] = useState('')

  const [charts, setCharts] = useState<ChartSummary[]>([])
  const [selectedChartId, setSelectedChartId] = useState<number | null>(null)
  const [selectedChart, setSelectedChart] = useState<ChartDetail | null>(null)

  const [noteSets, setNoteSets] = useState<PatientNoteSetSummary[]>([])
  const [selectedNoteSetId, setSelectedNoteSetId] = useState<number | null>(null)
  const [selectedNoteSet, setSelectedNoteSet] = useState<PatientNoteSetDetail | null>(null)
  const [uploadForm, setUploadForm] = useState<UploadFormState>(createUploadForm())
  const [patientIdDetection, setPatientIdDetection] = useState<PatientIdDetection | null>(null)
  const [patientIdTouched, setPatientIdTouched] = useState(false)
  const [lastAutoFilledPatientId, setLastAutoFilledPatientId] = useState('')
  const uploadPatientIdRef = useRef('')
  const patientIdTouchedRef = useRef(false)
  const lastAutoFilledPatientIdRef = useRef('')

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
  const [deleteUserConfirmation, setDeleteUserConfirmation] = useState('')
  const [userFilters, setUserFilters] = useState<UserFilters>({ query: '', role: 'all' })

  const [logs, setLogs] = useState<AuditLogRecord[]>([])
  const [logFilters, setLogFilters] = useState<LogFilters>({ patient_id: '', action: '', event_category: '' })
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [settingsForm, setSettingsForm] = useState<AppSettingsForm | null>(null)

  const [profileForm, setProfileForm] = useState<ProfileForm>({ full_name: '' })
  const [passwordChangeForm, setPasswordChangeForm] = useState<PasswordChangeForm>({ current_password: '', new_password: '' })

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
  const canEditCriteria = user?.role === 'admin' || user?.role === 'manager'

  const selectedManagedUser = useMemo(
    () => users.find((candidate) => candidate.id === selectedManagedUserId) || null,
    [users, selectedManagedUserId],
  )
  const selectedManagedUserIsBootstrap = isBootstrapAdmin(selectedManagedUser)
  const selectedManagedUserIsCurrentUser = selectedManagedUser?.id === user?.id
  const selectedManagedUserCanDelete = Boolean(selectedManagedUser && !selectedManagedUserIsBootstrap && !selectedManagedUserIsCurrentUser)

  const filteredUsers = useMemo(() => {
    const query = userFilters.query.trim().toLowerCase()
    return users.filter((candidate) => {
      const matchesRole = userFilters.role === 'all' || candidate.role === userFilters.role
      const matchesQuery =
        !query ||
        candidate.username.toLowerCase().includes(query) ||
        candidate.full_name.toLowerCase().includes(query)
      return matchesRole && matchesQuery
    })
  }, [userFilters, users])

  const accessAttemptLogs = useMemo(() => logs.filter((entry) => entry.event_category === 'access_attempt'), [logs])

  const selectedCriterion = useMemo(() => {
    if (!selectedChart) return null
    return selectedChart.checklist_items.find((item) => item.item_key === selectedFindingKey) || selectedChart.checklist_items[0] || null
  }, [selectedChart, selectedFindingKey])

  const totalOpen = useMemo(
    () => charts.filter((chart) => chart.state !== 'Approved by Office Manager').length,
    [charts],
  )
  const totalAwaiting = pendingManagerQueue.length
  const totalWaitingReverification = useMemo(
    () => charts.filter((chart) => chart.state === 'Returned to Counselor').length,
    [charts],
  )
  const totalApproved = useMemo(
    () => charts.filter((chart) => chart.state === 'Approved by Office Manager').length,
    [charts],
  )
  const activeBinders = useMemo(() => noteSets.filter((noteSet) => noteSet.status === 'active').length, [noteSets])
  const activeUserCount = useMemo(() => users.filter((entry) => entry.is_active).length, [users])
  const lockedUserCount = useMemo(() => users.filter((entry) => entry.is_locked).length, [users])
  const resetRequiredCount = useMemo(() => users.filter((entry) => entry.must_reset_password).length, [users])

  const newEvaluationTrend = useMemo(
    () => buildTrend(charts.map((chart) => chart.system_generated_at || chart.created_at)),
    [charts],
  )
  const approvalTrend = useMemo(
    () => buildTrend(charts.filter((chart) => chart.state === 'Approved by Office Manager').map((chart) => chart.reviewed_at)),
    [charts],
  )
  const reverificationTrend = useMemo(
    () => buildTrend(charts.filter((chart) => chart.state === 'Returned to Counselor').map((chart) => chart.reviewed_at)),
    [charts],
  )
  const uploadTrend = useMemo(
    () => buildTrend(noteSets.map((noteSet) => noteSet.created_at)),
    [noteSets],
  )

  const linkedNoteSet =
    selectedChart?.source_note_set_id != null ? noteSets.find((noteSet) => noteSet.id === selectedChart.source_note_set_id) || null : null

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

  function syncSelectedManagedUser(nextUsers: User[], preferredId?: number | null) {
    const selectedId = preferredId ?? selectedManagedUserId ?? nextUsers[0]?.id ?? null
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
    setDeleteUserConfirmation('')
  }

  async function loadChartDetail(chartId: number) {
    const detail = copyChartDetail(await apiRequest<ChartDetail>(`/charts/${chartId}`))
    setSelectedChart(detail)
    setSelectedChartId(detail.id)
    setSelectedFindingKey((current) => {
      if (current && detail.checklist_items.some((item) => item.item_key === current)) return current
      return detail.checklist_items[0]?.item_key || ''
    })
    setReviewDirty(false)

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

  async function loadUsers(preferredId?: number | null) {
    if (user?.role !== 'admin') return
    const nextUsers = await apiRequest<User[]>('/users')
    setUsers(nextUsers)
    syncSelectedManagedUser(nextUsers, preferredId)
  }

  async function loadSettings() {
    if (user?.role !== 'admin') return
    const payload = await apiRequest<AppSettings>('/settings')
    setAppSettings(payload)
    setSettingsForm(createSettingsForm(payload))
  }

  async function loadLogs() {
    if (user?.role !== 'admin') return
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (logFilters.patient_id.trim()) params.set('patient_id', logFilters.patient_id.trim())
    if (logFilters.action.trim()) params.set('action', logFilters.action.trim())
    if (logFilters.event_category.trim()) params.set('event_category', logFilters.event_category.trim())
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
      setProfileForm({ full_name: profile.full_name })
      setCharts(chartList)
      setNoteSets(noteSetList)

      if (profile.role === 'admin') {
        const [directory, configuredSettings] = await Promise.all([apiRequest<User[]>('/users'), apiRequest<AppSettings>('/settings')])
        setUsers(directory)
        syncSelectedManagedUser(directory, selectedManagedUserId)
        setAppSettings(configuredSettings)
        setSettingsForm(createSettingsForm(configuredSettings))
      } else {
        setUsers([])
        setSelectedManagedUserId(null)
        setManagedUserForm(null)
        setAppSettings(null)
        setSettingsForm(null)
        setDeleteUserConfirmation('')
      }

      const firstChartId = selectedChartId && chartList.some((chart) => chart.id === selectedChartId) ? selectedChartId : chartList[0]?.id ?? null
      const firstNoteSetId =
        selectedNoteSetId && noteSetList.some((noteSet) => noteSet.id === selectedNoteSetId) ? selectedNoteSetId : noteSetList[0]?.id ?? null

      if (firstChartId) {
        await loadChartDetail(firstChartId)
      } else {
        setSelectedChart(null)
        setSelectedChartId(null)
        setSelectedFindingKey('')
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
      setPatientIdDetection(null)
      setPatientIdTouched(false)
      setLastAutoFilledPatientId('')

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

  useEffect(() => {
    if (activeView === 'settings' && token && user?.role === 'admin' && !mustResetPassword) {
      void loadSettings()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    uploadPatientIdRef.current = uploadForm.patient_id
  }, [uploadForm.patient_id])

  useEffect(() => {
    patientIdTouchedRef.current = patientIdTouched
  }, [patientIdTouched])

  useEffect(() => {
    lastAutoFilledPatientIdRef.current = lastAutoFilledPatientId
  }, [lastAutoFilledPatientId])

  async function detectPatientId(entries: UploadEntry[]) {
    try {
      const body = new FormData()
      entries.forEach((entry) => body.append('files', entry.file))
      const detected = await apiRequest<Omit<PatientIdDetection, 'was_autofilled'>>('/patient-note-sets/detect-patient-id', {
        method: 'POST',
        body,
      })

      const shouldApply =
        Boolean(detected.patient_id) &&
        (!uploadPatientIdRef.current.trim() ||
          !patientIdTouchedRef.current ||
          uploadPatientIdRef.current.trim() === lastAutoFilledPatientIdRef.current)

      if (shouldApply && detected.patient_id) {
        setUploadForm((current) => ({ ...current, patient_id: detected.patient_id || current.patient_id }))
        setLastAutoFilledPatientId(detected.patient_id)
      }

      setPatientIdDetection({ ...detected, was_autofilled: shouldApply })
    } catch {
      setPatientIdDetection({
        patient_id: null,
        confidence: 'none',
        source_filename: null,
        source_kind: null,
        match_text: null,
        reason: 'Automatic patient ID detection was unavailable. Enter the patient ID manually.',
        was_autofilled: false,
      })
    }
  }

  function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || [])
    const entries = files.map((file) => buildUploadEntry(file))
    setUploadForm((current) => ({
      ...current,
      entries,
    }))
    if (!entries.length) {
      setPatientIdDetection(null)
      return
    }
    void detectPatientId(entries)
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

  function updateSelectedCriterion(patch: Partial<AuditItem>) {
    if (!selectedChart || !selectedCriterion) return
    setSelectedChart((current) => {
      if (!current) return current
      return {
        ...current,
        checklist_items: current.checklist_items.map((item) => (item.item_key === selectedCriterion.item_key ? { ...item, ...patch } : item)),
      }
    })
    setReviewDirty(true)
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
      setProfileForm({ full_name: profile.full_name })
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
      await apiRequest('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: resetForm.newPassword }),
      })
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
      setPatientIdDetection(null)
      setPatientIdTouched(false)
      setLastAutoFilledPatientId('')
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

  async function handleSaveReviewChanges() {
    if (!selectedChart || !canEditCriteria) return
    setIsBusy(true)
    setError('')
    setStatus(`Saving criterion review changes for patient ${selectedChart.patient_id}...`)
    try {
      const updated = await apiRequest<ChartDetail>(`/charts/${selectedChart.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toChartUpdatePayload(selectedChart)),
      })
      setSelectedChart(copyChartDetail(updated))
      setReviewDirty(false)
      await loadWorkspace()
      setStatus(`Criterion review changes saved for patient ${updated.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save review changes')
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
      setSelectedChart(copyChartDetail(updated))
      setDecisionComment('')
      setReviewDirty(false)
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
    const validationError = validateCreateUserForm(newUserForm)
    if (validationError) {
      setError(validationError)
      return
    }
    setIsBusy(true)
    setError('')
    try {
      const created = await apiRequest<User>('/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUserForm),
      })
      setNewUserForm({ username: '', full_name: '', password: '', role: 'counselor' })
      setUserFilters({ query: '', role: 'all' })
      setAdminPasswordReset('')
      await loadUsers(created.id)
      setStatus(`User ${created.username} created successfully.`)
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
      await loadUsers(updated.id)
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
      await loadUsers(selectedManagedUser.id)
      setStatus(`Password reset staged for ${selectedManagedUser.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to reset password')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleDeleteManagedUser(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser) return
    if (deleteUserConfirmation.trim() !== selectedManagedUser.username) {
      setError(`Type ${selectedManagedUser.username} exactly to confirm deletion.`)
      return
    }

    const username = selectedManagedUser.username
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<{ status: string }>(`/users/${selectedManagedUser.id}`, {
        method: 'DELETE',
      })
      setDeleteUserConfirmation('')
      await loadUsers()
      setStatus(`Deleted user ${username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleProfileSave(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      const updated = await apiRequest<User>('/users/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileForm),
      })
      setUser(updated)
      setProfileForm({ full_name: updated.full_name })
      setStatus('Your profile has been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update profile')
    } finally {
      setIsBusy(false)
    }
  }

  async function handlePasswordChange(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      await apiRequest('/users/me/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(passwordChangeForm),
      })
      setPasswordChangeForm({ current_password: '', new_password: '' })
      setStatus('Your password has been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to change password')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleSettingsSave(event: FormEvent) {
    event.preventDefault()
    if (!settingsForm) return
    setIsBusy(true)
    setError('')
    try {
      const payload = await apiRequest<AppSettings>('/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm),
      })
      setAppSettings(payload)
      setSettingsForm(createSettingsForm(payload))
      setStatus('Application settings have been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update application settings')
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
    setDeleteUserConfirmation('')
  }

  function renderTrendCard(title: string, points: TrendPoint[]) {
    const max = Math.max(1, ...points.map((point) => point.count))
    return (
      <article className='trend-card'>
        <div className='trend-card__header'>
          <strong>{title}</strong>
          <span>Last 7 days</span>
        </div>
        <div className='trend-strip'>
          {points.map((point) => (
            <div key={`${title}-${point.label}`} className='trend-strip__point'>
              <span className='trend-strip__count'>{point.count}</span>
              <div className='trend-strip__bar'>
                <div className='trend-strip__fill' style={{ height: `${(point.count / max) * 100}%` }} />
              </div>
              <span className='trend-strip__label'>{point.label}</span>
            </div>
          ))}
        </div>
      </article>
    )
  }

  return (
    <main className='shell'>
      <section className='hero'>
        <div>
          <p className='eyebrow'>Clinical note analyzer</p>
          <h1>Upload notes, review each criterion interactively, and route final approval through the office manager.</h1>
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
              <input
                required
                autoComplete='username'
                value={loginForm.username}
                onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))}
              />
            </label>
            <label>
              Password
              <input
                type='password'
                required
                autoComplete='current-password'
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
              <li>The reviewer can drill into any criterion and mark it ok or not ok.</li>
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
              <span>Current open</span>
              <strong>{totalOpen}</strong>
            </article>
            <article className='metric-card'>
              <span>Awaiting approval</span>
              <strong>{totalAwaiting}</strong>
            </article>
            <article className='metric-card'>
              <span>Waiting re-verification</span>
              <strong>{totalWaitingReverification}</strong>
            </article>
            <article className='metric-card'>
              <span>Approved</span>
              <strong>{totalApproved}</strong>
            </article>
          </section>

          <nav className='view-tabs'>
            {(['dashboard', 'reviews', 'uploads', 'profile'] as AppView[]).map((view) => (
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
              ? (['users', 'logs', 'settings'] as AppView[]).map((view) => (
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

          {activeView === 'dashboard' ? (
            <section className='dashboard-grid'>
              <section className='panel detail-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Summary dashboard</h2>
                    <p>Queue health, recent throughput, and approval trends for the current workspace.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='dashboard-metrics'>
                  <article className='mini-card'>
                    <span>Active binders</span>
                    <strong>{activeBinders}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Manager queue</span>
                    <strong>{totalAwaiting}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Returned for correction</span>
                    <strong>{totalWaitingReverification}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Current user</span>
                    <strong>{user?.full_name || user?.username}</strong>
                  </article>
                </div>

                <div className='trend-grid'>
                  {renderTrendCard('New evaluations', newEvaluationTrend)}
                  {renderTrendCard('Approvals', approvalTrend)}
                  {renderTrendCard('Re-verification queue', reverificationTrend)}
                  {renderTrendCard('Binder uploads', uploadTrend)}
                </div>
              </section>

              <aside className='panel queue-panel'>
                <section className='panel-subsection'>
                  <h3>Quick actions</h3>
                  <div className='quick-actions'>
                    <button type='button' onClick={() => setActiveView('uploads')}>
                      Upload binder
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('reviews')}>
                      Open review queue
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('profile')}>
                      My account
                    </button>
                    {user?.role === 'admin' ? (
                      <>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('users')}>
                          User management
                        </button>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('logs')}>
                          Forensic logs
                        </button>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('settings')}>
                          Settings
                        </button>
                      </>
                    ) : null}
                  </div>
                </section>

                <section className='panel-subsection'>
                  <h3>Current queue</h3>
                  {charts.length ? (
                    <ul className='queue-list'>
                      {charts.slice(0, 5).map((chart) => (
                        <li key={chart.id}>
                          <button type='button' className='queue-item' onClick={() => void loadChartDetail(chart.id)}>
                            <div>
                              <strong>{chart.patient_id}</strong>
                              <span>{chart.primary_clinician || 'Clinician pending'}</span>
                            </div>
                            <div className='queue-item-meta'>
                              <span className={`pill pill--${workflowTone(chart.state)}`}>{chart.state}</span>
                              <span>{chart.system_score}%</span>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className='empty-state'>No automated reviews are in the queue yet.</p>
                  )}
                </section>

                {user?.role === 'admin' ? (
                  <section className='panel-subsection admin-banner'>
                    <h3>Administrator controls</h3>
                    <p>
                      User management and forensic log review are available only to the administrator. Active: {activeUserCount}, locked:{' '}
                      {lockedUserCount}, password reset required: {resetRequiredCount}.
                    </p>
                  </section>
                ) : null}
              </aside>
            </section>
          ) : null}

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
                      <h3>Criterion review workbench</h3>
                      <div className='criteria-grid'>
                        <div className='criteria-list'>
                          {selectedChart.checklist_items.map((item) => (
                            <button
                              key={item.item_key}
                              type='button'
                              className={selectedFindingKey === item.item_key ? 'criterion-chip criterion-chip--active' : 'criterion-chip'}
                              onClick={() => setSelectedFindingKey(item.item_key)}
                            >
                              <span>Step {item.step}</span>
                              <strong>{item.label}</strong>
                              <small>{STATUS_LABELS[item.status]}</small>
                            </button>
                          ))}
                        </div>

                        {selectedCriterion ? (
                          <div className='criterion-workbench'>
                            <div className='finding-card__header'>
                              <strong>
                                Step {selectedCriterion.step}. {selectedCriterion.label}
                              </strong>
                              <span className={`pill pill--${checklistTone(selectedCriterion.status)}`}>{STATUS_LABELS[selectedCriterion.status]}</span>
                            </div>
                            <p>{selectedCriterion.instructions}</p>
                            <p className='muted-text'>Evidence hint: {selectedCriterion.evidence_hint}</p>
                            {selectedCriterion.policy_note ? <p className='muted-text'>Policy note: {selectedCriterion.policy_note}</p> : null}

                            <div className='segmented-actions'>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => updateSelectedCriterion({ status: 'yes' })}
                                disabled={!canEditCriteria}
                              >
                                Mark OK
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => updateSelectedCriterion({ status: 'no' })}
                                disabled={!canEditCriteria}
                              >
                                Mark not OK
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => updateSelectedCriterion({ status: 'pending' })}
                                disabled={!canEditCriteria}
                              >
                                Needs follow-up
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => updateSelectedCriterion({ status: 'na' })}
                                disabled={!canEditCriteria}
                              >
                                N/A
                              </button>
                            </div>

                            <div className='form-grid'>
                              <label className='full-width'>
                                Reviewer notes
                                <textarea
                                  aria-label='Reviewer notes'
                                  value={selectedCriterion.notes}
                                  onChange={(event) => updateSelectedCriterion({ notes: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Evidence location
                                <input
                                  aria-label='Evidence location'
                                  value={selectedCriterion.evidence_location}
                                  onChange={(event) => updateSelectedCriterion({ evidence_location: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Evidence date
                                <input
                                  aria-label='Evidence date'
                                  value={selectedCriterion.evidence_date}
                                  onChange={(event) => updateSelectedCriterion({ evidence_date: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Expiration date
                                <input
                                  aria-label='Expiration date'
                                  value={selectedCriterion.expiration_date}
                                  onChange={(event) => updateSelectedCriterion({ expiration_date: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                            </div>

                            {canEditCriteria ? (
                              <div className='decision-actions'>
                                <button type='button' onClick={() => void handleSaveReviewChanges()} disabled={isBusy || !reviewDirty}>
                                  Save criterion review changes
                                </button>
                                {reviewDirty ? <span className='muted-text'>Unsaved criterion review changes</span> : null}
                              </div>
                            ) : (
                              <p className='muted-text'>Criterion drill-down is visible to you, but only admins and managers can change the review result.</p>
                            )}
                          </div>
                        ) : null}
                      </div>
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
                                <div className='decision-actions'>
                                  <button type='button' className='ghost-button' onClick={() => setSelectedFindingKey(item.item_key)}>
                                    Dig deeper
                                  </button>
                                </div>
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
                              aria-label='Manager comment'
                              value={decisionComment}
                              placeholder='Record final approval context or describe what the counselor needs to fix.'
                              onChange={(event) => setDecisionComment(event.target.value)}
                            />
                          </label>
                          <div className='decision-actions'>
                            {transitionActions.map((action) => (
                              <button key={action.toState} type='button' onClick={() => void handleTransition(action)} disabled={isBusy || reviewDirty}>
                                {action.label}
                              </button>
                            ))}
                            {reviewDirty ? <span className='muted-text'>Save criterion changes before recording the final decision.</span> : null}
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
                    <input
                      value={uploadForm.patient_id}
                      onChange={(event) => {
                        const nextValue = event.target.value
                        setPatientIdTouched(true)
                        if (nextValue.trim() !== lastAutoFilledPatientId) {
                          setLastAutoFilledPatientId('')
                        }
                        setUploadForm((current) => ({ ...current, patient_id: nextValue }))
                      }}
                    />
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
                  {patientIdDetection ? (
                    <div className={`full-width detection-card ${patientIdDetection.patient_id ? 'detection-card--success' : 'detection-card--neutral'}`}>
                      <div>
                        <strong>
                          {patientIdDetection.patient_id
                            ? `Detected patient ID ${patientIdDetection.patient_id}`
                            : 'Patient ID could not be read automatically'}
                        </strong>
                        <p>{patientIdDetection.reason}</p>
                        {patientIdDetection.source_filename ? (
                          <p className='detection-card__meta'>
                            Source: {patientIdDetection.source_filename}
                            {patientIdDetection.confidence !== 'none' ? ` · Confidence: ${patientIdDetection.confidence}` : ''}
                          </p>
                        ) : null}
                      </div>
                      {patientIdDetection.patient_id && uploadForm.patient_id !== patientIdDetection.patient_id ? (
                        <button
                          type='button'
                          className='ghost-button'
                          onClick={() => {
                            setUploadForm((current) => ({ ...current, patient_id: patientIdDetection.patient_id || current.patient_id }))
                            setPatientIdTouched(false)
                            setLastAutoFilledPatientId(patientIdDetection.patient_id || '')
                            setPatientIdDetection((current) => (current ? { ...current, was_autofilled: true } : current))
                          }}
                        >
                          Use detected ID
                        </button>
                      ) : patientIdDetection.was_autofilled ? (
                        <span className='pill pill--success'>Auto-filled</span>
                      ) : null}
                    </div>
                  ) : null}
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

          {activeView === 'profile' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <section className='panel-subsection'>
                  <h2>My account</h2>
                  <div className='fact-list'>
                    <div>
                      <dt>Username</dt>
                      <dd>{user?.username}</dd>
                    </div>
                    <div>
                      <dt>Role</dt>
                      <dd>{user?.role}</dd>
                    </div>
                    <div>
                      <dt>Last login</dt>
                      <dd>{formatDateTime(user?.last_login_at)}</dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDateTime(user?.created_at)}</dd>
                    </div>
                  </div>
                </section>
              </aside>

              <section className='panel detail-panel'>
                <section className='panel-subsection'>
                  <h2>User profile</h2>
                  <form className='form-grid' onSubmit={handleProfileSave}>
                    <label className='full-width'>
                      Full name
                      <input value={profileForm.full_name} onChange={(event) => setProfileForm({ full_name: event.target.value })} />
                    </label>
                    <div className='full-width form-actions'>
                      <button type='submit' disabled={isBusy}>
                        Save profile
                      </button>
                    </div>
                  </form>
                </section>

                <section className='panel-subsection'>
                  <h3>Change password</h3>
                  {isBootstrapAdmin(user) ? (
                    <p className='muted-text'>The bootstrap admin password is static and managed outside the app.</p>
                  ) : (
                    <form className='form-grid' onSubmit={handlePasswordChange}>
                      <label>
                        Current password
                        <input
                          type='password'
                          value={passwordChangeForm.current_password}
                          onChange={(event) =>
                            setPasswordChangeForm((current) => ({ ...current, current_password: event.target.value }))
                          }
                        />
                      </label>
                      <label>
                        New password
                        <input
                          type='password'
                          value={passwordChangeForm.new_password}
                          onChange={(event) => setPasswordChangeForm((current) => ({ ...current, new_password: event.target.value }))}
                        />
                      </label>
                      <div className='full-width form-actions'>
                        <button type='submit' disabled={isBusy}>
                          Change password
                        </button>
                      </div>
                    </form>
                  )}
                </section>
              </section>
            </section>
          ) : null}

          {activeView === 'users' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>User management</h2>
                    <p>Select a user to edit access, reset their password, or delete the account.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadUsers()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='dashboard-metrics'>
                  <article className='mini-card'>
                    <span>Total users</span>
                    <strong>{users.length}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Active</span>
                    <strong>{activeUserCount}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Locked</span>
                    <strong>{lockedUserCount}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Reset required</span>
                    <strong>{resetRequiredCount}</strong>
                  </article>
                </div>

                <div className='filter-row'>
                  <label>
                    Search
                    <input value={userFilters.query} onChange={(event) => setUserFilters((current) => ({ ...current, query: event.target.value }))} />
                  </label>
                  <label>
                    Role
                    <select
                      value={userFilters.role}
                      onChange={(event) => setUserFilters((current) => ({ ...current, role: event.target.value as UserFilters['role'] }))}
                    >
                      <option value='all'>All roles</option>
                      <option value='admin'>Admin</option>
                      <option value='manager'>Office manager</option>
                      <option value='counselor'>Counselor</option>
                    </select>
                  </label>
                </div>

                <ul className='queue-list'>
                  {filteredUsers.map((managedUser) => (
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
                          {managedUser.must_reset_password ? <span className='pill pill--warning'>Reset required</span> : null}
                          <span className={`pill pill--${userStatusTone(managedUser)}`}>{userStatusLabel(managedUser)}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              </aside>

              <section className='panel detail-panel'>
                <section className='panel-subsection'>
                  <h2>Manage selected user</h2>
                  <p className='muted-text'>The selected user can be edited below. New accounts sign in with the temporary password once, then must choose a new password.</p>

                  {selectedManagedUser && managedUserForm ? (
                    <>
                      <article className='finding-card'>
                        <div className='finding-card__header'>
                          <div>
                            <strong>{selectedManagedUser.full_name || selectedManagedUser.username}</strong>
                            <p>{selectedManagedUser.username}</p>
                          </div>
                          <div className='quick-actions'>
                            <span className='pill pill--neutral'>{selectedManagedUser.role}</span>
                            {selectedManagedUser.must_reset_password ? <span className='pill pill--warning'>Reset required</span> : null}
                            <span className={`pill pill--${userStatusTone(selectedManagedUser)}`}>{userStatusLabel(selectedManagedUser)}</span>
                          </div>
                        </div>
                        <dl className='detail-grid'>
                          <div>
                            <dt>Last login</dt>
                            <dd>{formatDateTime(selectedManagedUser.last_login_at)}</dd>
                          </div>
                          <div>
                            <dt>Created</dt>
                            <dd>{formatDateTime(selectedManagedUser.created_at)}</dd>
                          </div>
                          <div>
                            <dt>Editable role</dt>
                            <dd>{selectedManagedUserIsBootstrap ? 'Bootstrap admin is fixed' : 'Yes'}</dd>
                          </div>
                          <div>
                            <dt>Deletion</dt>
                            <dd>
                              {selectedManagedUserCanDelete
                                ? 'Available when no historical records are attached'
                                : selectedManagedUserIsBootstrap
                                  ? 'Bootstrap admin cannot be deleted'
                                  : 'You cannot delete the signed-in account'}
                            </dd>
                          </div>
                        </dl>
                      </article>

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
                            disabled={isBusy || selectedManagedUserIsBootstrap}
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
                            disabled={isBusy || selectedManagedUserIsBootstrap}
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
                            disabled={isBusy || selectedManagedUserIsBootstrap}
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
                            disabled={isBusy || selectedManagedUserIsBootstrap}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, must_reset_password: event.target.checked } : current))
                            }
                          />
                          Force password reset at next login
                        </label>
                        <div className='full-width form-actions'>
                          <button type='submit' disabled={isBusy}>
                            Save selected user
                          </button>
                        </div>
                      </form>

                      <section className='panel-subsection'>
                        <h3>Admin password reset</h3>
                        {selectedManagedUserIsBootstrap ? (
                          <p className='muted-text'>The bootstrap admin password is fixed outside the app.</p>
                        ) : (
                          <form className='form-grid' onSubmit={handleAdminPasswordReset}>
                            <label className='full-width'>
                              New temporary password
                              <input
                                type='password'
                                minLength={12}
                                value={adminPasswordReset}
                                onChange={(event) => setAdminPasswordReset(event.target.value)}
                              />
                            </label>
                            <div className='full-width form-actions'>
                              <button type='submit' disabled={isBusy}>
                                Reset password and require login reset
                              </button>
                            </div>
                          </form>
                        )}
                      </section>

                      <section className='panel-subsection'>
                        <h3>Delete user</h3>
                        {selectedManagedUserCanDelete ? (
                          <form className='form-grid' onSubmit={handleDeleteManagedUser}>
                            <label className='full-width'>
                              Type username to confirm
                              <input
                                value={deleteUserConfirmation}
                                onChange={(event) => setDeleteUserConfirmation(event.target.value)}
                                placeholder={selectedManagedUser.username}
                              />
                            </label>
                            <div className='full-width form-actions'>
                              <button type='submit' className='danger-button' disabled={isBusy || deleteUserConfirmation.trim() !== selectedManagedUser.username}>
                                Delete user
                              </button>
                            </div>
                            <p className='muted-text'>
                              Deletion is permanent and only works when the account has no linked charts, uploads, workflow history, or audit trail.
                            </p>
                          </form>
                        ) : (
                          <p className='muted-text'>
                            {selectedManagedUserIsBootstrap
                              ? 'The bootstrap admin account cannot be deleted.'
                              : 'The signed-in admin account cannot delete itself.'}
                          </p>
                        )}
                      </section>
                    </>
                  ) : (
                    <p className='empty-state'>Select a user to edit details, reset a password, or delete the account.</p>
                  )}
                </section>

                <section className='panel-subsection'>
                  <h2>Create user</h2>
                  <p className='muted-text'>Create a managed user account with a temporary password of at least 12 characters. The user will be prompted to reset it after the first sign-in.</p>
                  <form className='form-grid' onSubmit={handleCreateUser}>
                    <label>
                      Username
                      <input
                        required
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
                        minLength={12}
                        required
                        autoComplete='new-password'
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
                </section>
              </section>
            </section>
          ) : null}

          {activeView === 'settings' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Application settings</h2>
                    <p>Configure external access intelligence and the LLM used for gap-filling analysis.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadSettings()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='fact-list'>
                  <div>
                    <dt>Organization</dt>
                    <dd>{appSettings?.organization_name || 'Not configured'}</dd>
                  </div>
                  <div>
                    <dt>LLM configured</dt>
                    <dd>{appSettings?.llm_api_key_configured ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt>Reputation API configured</dt>
                    <dd>{appSettings?.access_reputation_api_key_configured ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatDateTime(appSettings?.updated_at)}</dd>
                  </div>
                </div>
              </aside>

              <section className='panel detail-panel'>
                {settingsForm ? (
                  <form className='form-grid' onSubmit={handleSettingsSave}>
                    <label className='full-width'>
                      Organization name
                      <input
                        value={settingsForm.organization_name}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, organization_name: event.target.value } : current))}
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.access_intel_enabled}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_intel_enabled: event.target.checked } : current))
                        }
                      />
                      Enable access intelligence lookups
                    </label>
                    <label>
                      Geolocation URL
                      <input
                        value={settingsForm.access_geo_lookup_url}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_geo_lookup_url: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      Reputation URL
                      <input
                        value={settingsForm.access_reputation_url}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_reputation_url: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      Reputation API key
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.access_reputation_api_key}
                        placeholder={appSettings?.access_reputation_api_key_configured ? 'Configured. Enter a new key to replace it.' : 'Optional'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  access_reputation_api_key: event.target.value,
                                  clear_access_reputation_api_key: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_access_reputation_api_key}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, clear_access_reputation_api_key: event.target.checked } : current))
                        }
                      />
                      Clear stored reputation API key
                    </label>
                    <label>
                      Lookup timeout (seconds)
                      <input
                        type='number'
                        min={1}
                        max={30}
                        value={settingsForm.access_lookup_timeout_seconds}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current ? { ...current, access_lookup_timeout_seconds: Number(event.target.value || 1) } : current
                          )
                        }
                      />
                    </label>

                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_enabled}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_enabled: event.target.checked } : current))}
                      />
                      Enable LLM-assisted analysis
                    </label>
                    <label>
                      LLM provider label
                      <input
                        value={settingsForm.llm_provider_name}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_provider_name: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      LLM base URL
                      <input
                        value={settingsForm.llm_base_url}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_base_url: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      LLM model
                      <input
                        value={settingsForm.llm_model}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_model: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      LLM API key
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.llm_api_key}
                        placeholder={appSettings?.llm_api_key_configured ? 'Configured. Enter a new key to replace it.' : 'Required to enable LLM analysis'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  llm_api_key: event.target.value,
                                  clear_llm_api_key: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_llm_api_key}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, clear_llm_api_key: event.target.checked } : current))}
                      />
                      Clear stored LLM API key
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_use_for_access_review}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_use_for_access_review: event.target.checked } : current))
                        }
                      />
                      Use LLM for dangerous-IP access summaries
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_use_for_evaluation_gap_analysis}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current ? { ...current, llm_use_for_evaluation_gap_analysis: event.target.checked } : current
                          )
                        }
                      />
                      Use LLM to fill note-analysis gaps
                    </label>
                    <label className='full-width'>
                      Analysis instructions
                      <textarea
                        value={settingsForm.llm_analysis_instructions}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_analysis_instructions: event.target.value } : current))
                        }
                      />
                    </label>
                    <div className='full-width form-actions'>
                      <button type='submit' disabled={isBusy}>
                        Save settings
                      </button>
                    </div>
                  </form>
                ) : (
                  <p className='empty-state'>Settings are loading.</p>
                )}
              </section>
            </section>
          ) : null}

          {activeView === 'logs' && user?.role === 'admin' ? (
            <section className='panel detail-panel'>
              <div className='panel-heading'>
                <div>
                  <h2>Forensic audit logs</h2>
                  <p>Admin-only access to request, data-change, access-attempt, workflow, and upload events.</p>
                </div>
                <button type='button' className='ghost-button' onClick={() => void loadLogs()} disabled={isBusy}>
                  Refresh
                </button>
              </div>

              <div className='dashboard-metrics'>
                <article className='mini-card'>
                  <span>Access attempts loaded</span>
                  <strong>{accessAttemptLogs.length}</strong>
                </article>
                <article className='mini-card'>
                  <span>Total logs loaded</span>
                  <strong>{logs.length}</strong>
                </article>
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
                <label>
                  Category
                  <select
                    value={logFilters.event_category}
                    onChange={(event) => setLogFilters((current) => ({ ...current, event_category: event.target.value }))}
                  >
                    <option value=''>All categories</option>
                    <option value='access_attempt'>Access attempts</option>
                    <option value='data_change'>Data changes</option>
                    <option value='forensic_access'>Forensic access</option>
                    <option value='http_request'>HTTP requests</option>
                    <option value='workflow'>Workflow</option>
                  </select>
                </label>
                <button type='submit' disabled={isBusy}>
                  Filter logs
                </button>
              </form>

              {logs.length ? (
                <div className='log-table'>
                  {logs.map((log) => {
                    const details = parseLogDetails(log.details)
                    const geolocation = details.geolocation as Record<string, unknown> | undefined
                    return (
                      <article key={log.event_id} className='log-row'>
                        <div className='log-row__meta'>
                          <strong>{log.action}</strong>
                          <span>{formatDateTime(log.timestamp_utc)}</span>
                        </div>
                        <p>{log.message}</p>
                        {log.event_category === 'access_attempt' && typeof details.danger_summary === 'string' ? (
                          <p className='muted-text'>
                            {details.danger_summary}
                            {typeof geolocation?.city === 'string' || typeof geolocation?.country === 'string'
                              ? ` Location: ${[geolocation?.city, geolocation?.region, geolocation?.country].filter(Boolean).join(', ')}.`
                              : ''}
                          </p>
                        ) : null}
                        <div className='log-row__details'>
                          <span>Actor: {log.actor_username || log.actor_type}</span>
                          <span>Patient: {log.patient_id || 'n/a'}</span>
                          <span>IP: {log.source_ip || 'n/a'}</span>
                          <span>Request: {log.request_id}</span>
                          <span>{log.event_category}</span>
                          <span className={`pill pill--${log.outcome_status === 'success' ? 'success' : 'danger'}`}>{log.outcome_status}</span>
                        </div>
                      </article>
                    )
                  })}
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
