import { ChangeEvent, FormEvent, useMemo, useState } from 'react'
import './app.css'

const API = import.meta.env.VITE_API_URL || '/api'

type Role = 'admin' | 'counselor' | 'manager'
type WorkflowState = 'Draft' | 'Submitted to Admin' | 'Returned for Update' | 'In Progress Review' | 'Completed' | 'Verified'
type ComplianceStatus = 'pending' | 'yes' | 'no' | 'na'
type NoteSetStatus = 'active' | 'superseded'
type NoteSetUploadMode = 'initial' | 'update'
type AllevaBucket = 'custom_forms' | 'uploaded_documents' | 'portal_documents' | 'labs' | 'medications' | 'notes' | 'other'
type DocumentCompletionStatus = 'completed' | 'incomplete' | 'draft'

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
  notes: string
  pending_items: number
  passed_items: number
  failed_items: number
  not_applicable_items: number
}
type ChartDetail = ChartSummary & { checklist_items: AuditItem[] }
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
type PatientNoteSetDetail = PatientNoteSetSummary & { documents: PatientNoteDocument[] }
type NoteUploadEntry = {
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
type NoteUploadForm = {
  patient_id: string
  upload_mode: NoteSetUploadMode
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  upload_notes: string
  entries: NoteUploadEntry[]
}
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
const NOTE_SET_STATUS_LABELS: Record<NoteSetStatus, string> = { active: 'Active', superseded: 'Superseded' }
const ALLEVA_BUCKET_LABELS: Record<AllevaBucket, string> = {
  custom_forms: 'Custom Forms',
  uploaded_documents: 'Uploaded Documents',
  portal_documents: 'Portal Documents',
  labs: 'Labs',
  medications: 'Medication',
  notes: 'Notes',
  other: 'Other',
}
const DOCUMENT_STATUS_LABELS: Record<DocumentCompletionStatus, string> = {
  completed: 'Completed',
  incomplete: 'Incomplete',
  draft: 'Draft',
}

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

function noteSetStatusClassName(status: NoteSetStatus) {
  return `note-set-chip note-set-chip--${status}`
}

function complianceClassName(status: ComplianceStatus) {
  return `segmented-choice segmented-choice--${status}`
}

function chartLabel(chart: Pick<ChartSummary, 'patient_id' | 'client_name'>) {
  return chart.patient_id || chart.client_name || 'Unassigned patient'
}

function createNewChartForm(auditorName = '', patientId = '') {
  return {
    patient_id: patientId,
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

function buildUploadEntry(file: File): NoteUploadEntry {
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

function createUploadForm(overrides?: Partial<Omit<NoteUploadForm, 'entries'>>) {
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

function copyChartDetail(detail: ChartDetail): ChartDetail {
  return {
    ...detail,
    checklist_items: detail.checklist_items.map((item) => ({ ...item })),
  }
}

function toChartSummary(detail: ChartDetail): ChartSummary {
  return {
    id: detail.id,
    patient_id: detail.patient_id,
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

function bytesLabel(sizeBytes: number) {
  if (sizeBytes >= 1024 * 1024) return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
  if (sizeBytes >= 1024) return `${Math.round(sizeBytes / 1024)} KB`
  return `${sizeBytes} B`
}

function findLinkedNoteSet(noteSets: PatientNoteSetSummary[], patientId: string) {
  if (!patientId) return null
  return noteSets.find((item) => item.patient_id === patientId && item.status === 'active')
    || noteSets.find((item) => item.patient_id === patientId)
    || null
}

export function App() {
  const [token, setToken] = useState('')
  const [status, setStatus] = useState('Ready to sign in. Enter your username and password to begin the chart audit workflow.')
  const [authState, setAuthState] = useState<AuthState>('anonymous')
  const [mustResetPassword, setMustResetPassword] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [chartSummaries, setChartSummaries] = useState<ChartSummary[]>([])
  const [templateSections, setTemplateSections] = useState<AuditTemplateSection[]>([])
  const [noteSetSummaries, setNoteSetSummaries] = useState<PatientNoteSetSummary[]>([])
  const [selectedChartId, setSelectedChartId] = useState<number | null>(null)
  const [selectedNoteSetId, setSelectedNoteSetId] = useState<number | null>(null)
  const [chartDetail, setChartDetail] = useState<ChartDetail | null>(null)
  const [chartDraft, setChartDraft] = useState<ChartDetail | null>(null)
  const [selectedNoteSetDetail, setSelectedNoteSetDetail] = useState<PatientNoteSetDetail | null>(null)
  const [showCreateAudit, setShowCreateAudit] = useState(false)
  const [showUploadWorkspace, setShowUploadWorkspace] = useState(false)
  const [transitionComment, setTransitionComment] = useState('')
  const [form, setForm] = useState({ username: 'admin', password: 'r3' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [newChartForm, setNewChartForm] = useState(createNewChartForm())
  const [uploadForm, setUploadForm] = useState<NoteUploadForm>(createUploadForm())

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])
  const playbookItems = useMemo(() => flattenPlaybook(templateSections), [templateSections])
  const groupedDraftItems = useMemo(() => groupedChecklist(chartDraft?.checklist_items || []), [chartDraft])

  function resetSession(message = 'Signed out. Session data cleared. Ready for a new login attempt.') {
    setToken('')
    setUser(null)
    setChartSummaries([])
    setTemplateSections([])
    setNoteSetSummaries([])
    setSelectedChartId(null)
    setSelectedNoteSetId(null)
    setChartDetail(null)
    setChartDraft(null)
    setSelectedNoteSetDetail(null)
    setShowCreateAudit(false)
    setShowUploadWorkspace(false)
    setTransitionComment('')
    setMustResetPassword(false)
    setAuthState('anonymous')
    setNewChartForm(createNewChartForm())
    setUploadForm(createUploadForm())
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

  async function fetchNoteSetDetail(currentToken: string, noteSetId: number) {
    const response = await fetch(`${API}/patient-note-sets/${noteSetId}`, {
      headers: { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' },
    })
    const payload = (await response.json().catch(() => null)) as ApiError | PatientNoteSetDetail | null
    if (!response.ok) {
      throw new Error(readErrorMessage(response.status, payload as ApiError | null))
    }
    return payload as PatientNoteSetDetail
  }

  function linkedNoteSetForPatient(patientId: string) {
    if (!patientId) return null
    return noteSetSummaries.find((item) => item.patient_id === patientId && item.status === 'active')
      || noteSetSummaries.find((item) => item.patient_id === patientId)
      || null
  }

  async function loadWorkspace(currentToken: string, currentUser: User, initialMessage?: string) {
    setAuthState('authenticated_loading_profile')
    setStatus(initialMessage || `Welcome ${currentUser.username}. Loading your audit queue, note sets, playbook, and review workspace...`)

    const headers = { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' }
    const [chartsResponse, templateResponse, noteSetsResponse] = await Promise.all([
      fetch(`${API}/charts`, { headers }),
      fetch(`${API}/audit-template`, { headers }),
      fetch(`${API}/patient-note-sets`, { headers }),
    ])

    const chartsPayload = (await chartsResponse.json().catch(() => null)) as ApiError | ChartSummary[] | null
    const templatePayload = (await templateResponse.json().catch(() => null)) as ApiError | AuditTemplateSection[] | null
    const noteSetsPayload = (await noteSetsResponse.json().catch(() => null)) as ApiError | PatientNoteSetSummary[] | null

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
    if (!noteSetsResponse.ok) {
      setAuthState('error')
      setStatus(`Patient note sets failed to load. ${readErrorMessage(noteSetsResponse.status, noteSetsPayload as ApiError | null)}`)
      return
    }

    const charts = (chartsPayload as ChartSummary[]) || []
    const sections = (templatePayload as AuditTemplateSection[]) || []
    const noteSets = (noteSetsPayload as PatientNoteSetSummary[]) || []

    setChartSummaries(charts)
    setTemplateSections(sections)
    setNoteSetSummaries(noteSets)
    setNewChartForm(createNewChartForm(currentUser.username))
    setUploadForm(createUploadForm())

    let initialChart: ChartDetail | null = null
    if (charts.length > 0) {
      initialChart = await fetchChartDetail(currentToken, charts[0].id)
      setSelectedChartId(initialChart.id)
      setChartDetail(initialChart)
      setChartDraft(copyChartDetail(initialChart))
      setShowCreateAudit(false)
      setShowUploadWorkspace(false)
      setTransitionComment('')
    } else {
      setSelectedChartId(null)
      setChartDetail(null)
      setChartDraft(null)
    }

    const preferredNoteSet = initialChart
      ? findLinkedNoteSet(noteSets, initialChart.patient_id)
      : noteSets[0] || null

    if (preferredNoteSet) {
      const detail = await fetchNoteSetDetail(currentToken, preferredNoteSet.id)
      setSelectedNoteSetId(detail.id)
      setSelectedNoteSetDetail(detail)
    } else {
      setSelectedNoteSetId(null)
      setSelectedNoteSetDetail(null)
    }

    if (charts.length > 0) {
      const playbookCount = sections.flatMap((section) => section.items).length
      setStatus(
        `Workspace ready. ${charts.length} audit${charts.length === 1 ? '' : 's'} in queue, ${noteSets.length} patient note set${noteSets.length === 1 ? '' : 's'} loaded, and ${playbookCount} checklist step${playbookCount === 1 ? '' : 's'} ready.`
      )
    } else if (preferredNoteSet) {
      setShowUploadWorkspace(true)
      setStatus('Workspace ready. No audits are open yet, but patient note sets are loaded. Review the latest note binder or start a chart audit from a patient ID.')
    } else {
      setShowCreateAudit(true)
      setStatus('Workspace ready. No chart audits or patient note sets are loaded yet, so start with a patient ID and create the first audit or upload a note set.')
    }

    setAuthState('authenticated_ready')
  }

  async function loadProfileAndWorkspace(currentToken: string, expectsReset: boolean) {
    setAuthState('authenticated_loading_profile')
    setStatus('Authentication succeeded. Loading profile, role permissions, and audit workspace...')

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

  async function refreshNoteSetQueue(currentToken: string, preferredNoteSetId?: number) {
    const response = await fetch(`${API}/patient-note-sets`, {
      headers: { Authorization: `Bearer ${currentToken}`, 'Content-Type': 'application/json' },
    })
    const payload = (await response.json().catch(() => null)) as ApiError | PatientNoteSetSummary[] | null
    if (!response.ok) {
      throw new Error(readErrorMessage(response.status, payload as ApiError | null))
    }
    const summaries = (payload as PatientNoteSetSummary[]) || []
    setNoteSetSummaries(summaries)

    const targetId = preferredNoteSetId ?? selectedNoteSetId ?? null
    if (targetId) {
      const detail = await fetchNoteSetDetail(currentToken, targetId)
      setSelectedNoteSetId(detail.id)
      setSelectedNoteSetDetail(detail)
    } else if (summaries.length === 0) {
      setSelectedNoteSetId(null)
      setSelectedNoteSetDetail(null)
    }
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

  async function loadLinkedNoteSet(currentToken: string, patientId: string, openWorkspace = false) {
    const linked = noteSetSummaries.find((item) => item.patient_id === patientId && item.status === 'active')
      || noteSetSummaries.find((item) => item.patient_id === patientId)
    if (!linked) {
      if (openWorkspace) {
        setSelectedNoteSetId(null)
        setSelectedNoteSetDetail(null)
      }
      return
    }

    const detail = await fetchNoteSetDetail(currentToken, linked.id)
    setSelectedNoteSetId(detail.id)
    setSelectedNoteSetDetail(detail)
    if (openWorkspace) setShowUploadWorkspace(true)
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
      setShowUploadWorkspace(false)
      setTransitionComment('')
      await loadLinkedNoteSet(token, detail.patient_id, false)
      setStatus(`Loaded chart audit for patient ${chartLabel(detail)}. Review the checklist and the linked clinical note binder together.`)
    } catch (error) {
      setAuthState('error')
      setStatus(`Unable to load chart audit. ${error instanceof Error ? error.message : 'Unexpected error.'}`)
    }
  }

  async function selectNoteSet(noteSetId: number) {
    if (!token) return
    setStatus('Loading patient note set...')
    try {
      const detail = await fetchNoteSetDetail(token, noteSetId)
      setSelectedNoteSetId(detail.id)
      setSelectedNoteSetDetail(detail)
      setShowCreateAudit(false)
      setShowUploadWorkspace(true)
      setUploadForm(
        createUploadForm({
          patient_id: detail.patient_id,
          upload_mode: 'update',
          level_of_care: detail.level_of_care,
          admission_date: detail.admission_date,
          discharge_date: detail.discharge_date,
          primary_clinician: detail.primary_clinician,
          upload_notes: `Updating version ${detail.version} for patient ${detail.patient_id}.`,
        })
      )
      setStatus(`Loaded patient note set version ${detail.version} for patient ${detail.patient_id}.`)
    } catch (error) {
      setAuthState('error')
      setStatus(`Unable to load patient note set. ${error instanceof Error ? error.message : 'Unexpected error.'}`)
    }
  }

  function openUploadWorkspace(prefillPatientId = '', linkedNoteSet?: PatientNoteSetSummary | PatientNoteSetDetail | null) {
    const sourceChart = chartDraft || chartDetail
    setShowCreateAudit(false)
    setShowUploadWorkspace(true)
    setUploadForm(
      createUploadForm({
        patient_id: prefillPatientId || sourceChart?.patient_id || linkedNoteSet?.patient_id || '',
        upload_mode: linkedNoteSet ? 'update' : 'initial',
        level_of_care: sourceChart?.level_of_care || linkedNoteSet?.level_of_care || '',
        admission_date: sourceChart?.admission_date || linkedNoteSet?.admission_date || '',
        discharge_date: sourceChart?.discharge_date || linkedNoteSet?.discharge_date || '',
        primary_clinician: sourceChart?.primary_clinician || linkedNoteSet?.primary_clinician || '',
        upload_notes: linkedNoteSet
          ? `Update patient ${linkedNoteSet.patient_id} after note set version ${linkedNoteSet.version}.`
          : '',
      })
    )
    setStatus('Patient note intake opened. Upload the Alleva clinical note binder as a first-time set or as a new immutable version.')
  }

  function startAuditFromNoteSet(noteSet: PatientNoteSetSummary | PatientNoteSetDetail) {
    if (!user) return
    setNewChartForm({
      patient_id: noteSet.patient_id,
      client_name: '',
      level_of_care: noteSet.level_of_care,
      admission_date: noteSet.admission_date,
      discharge_date: noteSet.discharge_date,
      primary_clinician: noteSet.primary_clinician,
      auditor_name: user.username,
      other_details: `Linked note set version ${noteSet.version} from ${noteSet.source_system}.`,
      notes: '',
    })
    setShowUploadWorkspace(false)
    setShowCreateAudit(true)
    setStatus(`New chart audit form opened for patient ${noteSet.patient_id}, prefilled from note set version ${noteSet.version}.`)
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
      setShowUploadWorkspace(false)
      setTransitionComment('')
      setNewChartForm(createNewChartForm(user?.username || detail.auditor_name))
      setAuthState('authenticated_ready')
      await loadLinkedNoteSet(token, detail.patient_id, false)
      setStatus(`Chart audit created for patient ${chartLabel(detail)}. Work top to bottom through the checklist before submitting it for review.`)
    } catch {
      setAuthState('error')
      setStatus('Chart creation failed: backend unreachable or request interrupted.')
    }
  }

  async function saveChart() {
    if (!chartDraft) return

    setStatus(`Saving audit for patient ${chartLabel(chartDraft)}...`)
    try {
      const response = await fetch(`${API}/charts/${chartDraft.id}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({
          patient_id: chartDraft.patient_id,
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
      setStatus(`Saved audit for patient ${chartLabel(detail)}. ${detail.failed_items} failed item(s) and ${detail.pending_items} pending item(s) remain.`)
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

    setStatus(`${action.label} in progress for patient ${chartLabel(chartDraft)}...`)
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
      setStatus(`Workflow updated. Patient ${chartLabel(detail)} is now "${detail.state}".`)
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

  function handleUploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || [])
    setUploadForm((current) => ({
      ...current,
      entries: files.map((file) => buildUploadEntry(file)),
    }))
  }

  function updateUploadField(field: keyof Omit<NoteUploadForm, 'entries'>, value: string) {
    setUploadForm((current) => ({ ...current, [field]: value }))
  }

  function updateUploadEntry(index: number, patch: Partial<Omit<NoteUploadEntry, 'file'>>) {
    setUploadForm((current) => ({
      ...current,
      entries: current.entries.map((entry, entryIndex) => (entryIndex === index ? { ...entry, ...patch } : entry)),
    }))
  }

  async function uploadPatientNotes(e: FormEvent) {
    e.preventDefault()
    if (!token) return
    if (!uploadForm.patient_id.trim()) {
      setStatus('Patient ID is required before uploading notes.')
      return
    }
    if (uploadForm.entries.length === 0) {
      setStatus('Select at least one clinical note or document before uploading.')
      return
    }

    const formData = new FormData()
    formData.append('patient_id', uploadForm.patient_id.trim())
    formData.append('upload_mode', uploadForm.upload_mode)
    formData.append('level_of_care', uploadForm.level_of_care)
    formData.append('admission_date', uploadForm.admission_date)
    formData.append('discharge_date', uploadForm.discharge_date)
    formData.append('primary_clinician', uploadForm.primary_clinician)
    formData.append('upload_notes', uploadForm.upload_notes)
    formData.append(
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
        }))
      )
    )
    uploadForm.entries.forEach((entry) => formData.append('files', entry.file))

    setStatus(`Uploading patient note set for ${uploadForm.patient_id.trim()}...`)
    try {
      const response = await fetch(`${API}/patient-note-sets`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const payload = (await response.json().catch(() => null)) as ApiError | PatientNoteSetDetail | null
      if (!response.ok) {
        setAuthState('error')
        setStatus(`Patient note upload failed. ${readErrorMessage(response.status, payload as ApiError | null)}`)
        return
      }

      const detail = payload as PatientNoteSetDetail
      await refreshNoteSetQueue(token, detail.id)
      setSelectedNoteSetId(detail.id)
      setSelectedNoteSetDetail(detail)
      setUploadForm(
        createUploadForm({
          patient_id: detail.patient_id,
          upload_mode: 'update',
          level_of_care: detail.level_of_care,
          admission_date: detail.admission_date,
          discharge_date: detail.discharge_date,
          primary_clinician: detail.primary_clinician,
          upload_notes: `Update patient ${detail.patient_id} after version ${detail.version}.`,
        })
      )
      setShowUploadWorkspace(true)
      setStatus(`Patient note set version ${detail.version} uploaded for patient ${detail.patient_id}. Files are preserved as a new immutable binder revision.`)
    } catch {
      setAuthState('error')
      setStatus('Patient note upload failed: backend unreachable or request interrupted.')
    }
  }

  async function downloadDocument(noteSetId: number, noteDocument: PatientNoteDocument) {
    if (!token) return
    setStatus(`Downloading ${noteDocument.document_label} for patient note set ${noteSetId}...`)
    try {
      const response = await fetch(`${API}/patient-note-sets/${noteSetId}/documents/${noteDocument.id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as ApiError | null
        setAuthState('error')
        setStatus(`Download failed. ${readErrorMessage(response.status, payload)}`)
        return
      }
      const blob = await response.blob()
      const href = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = href
      anchor.download = noteDocument.original_filename
      anchor.click()
      URL.revokeObjectURL(href)
      setStatus(`Downloaded ${noteDocument.original_filename}.`)
    } catch {
      setAuthState('error')
      setStatus('Download failed: backend unreachable or request interrupted.')
    }
  }

  const tone = statusTone(authState)
  const transitionActions = user && chartDraft ? availableTransitions(user.role, chartDraft.state) : []
  const activeSummary = chartDraft || chartDetail
  const openIssues = (chartDraft?.checklist_items || []).filter((item) => item.status === 'no' || item.status === 'pending')
  const linkedNoteSet = chartDraft ? linkedNoteSetForPatient(chartDraft.patient_id) : null
  const activePatientNoteCount = noteSetSummaries.filter((item) => item.status === 'active').length

  return (
    <div className='app-shell'>
      <header className='topbar'>
        <div>
          <p className='eyebrow'>Clinical Audit Workflow</p>
          <h1>Chart Review Workflow</h1>
          <p className='subtitle'>Checklist-driven audits with patient-ID-linked note binders, versioned uploads, and guided clinical review.</p>
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
          <p className='panel-lead'>Use your chart audit account to open the guided review queue, patient note binders, and checklist workspace.</p>
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
          <p className='panel-lead'>The system is validating credentials, loading role permissions, syncing patient note binders, and preparing the chart audit queue.</p>
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
                  setShowUploadWorkspace(false)
                  setSelectedChartId(null)
                  setChartDetail(null)
                  setChartDraft(null)
                  setTransitionComment('')
                  setNewChartForm(createNewChartForm(user.username))
                  setStatus('New chart audit form opened. Enter the patient ID and episode header before working through the checklist.')
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
                      className={`queue-card ${selectedChartId === chart.id && !showUploadWorkspace ? 'queue-card--active' : ''}`}
                      onClick={() => void selectChart(chart.id)}
                    >
                      <div className='queue-card__header'>
                        <strong>{chartLabel(chart)}</strong>
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
                  <p className='eyebrow'>Patient Notes</p>
                  <h2>Clinical Note Sets</h2>
                </div>
                <button className='secondary-button' onClick={() => openUploadWorkspace()}>Upload notes</button>
              </div>
              <div className='queue-summary'>
                <div>
                  <span className='metric-value'>{noteSetSummaries.length}</span>
                  <span className='metric-label'>Binder versions</span>
                </div>
                <div>
                  <span className='metric-value'>{activePatientNoteCount}</span>
                  <span className='metric-label'>Active binders</span>
                </div>
                <div>
                  <span className='metric-value'>{noteSetSummaries.reduce((sum, item) => sum + item.file_count, 0)}</span>
                  <span className='metric-label'>Stored files</span>
                </div>
              </div>
              <div className='queue-list'>
                {noteSetSummaries.length === 0 ? (
                  <div className='empty-queue'>
                    <strong>No patient note sets yet.</strong>
                    <p>Upload the first Alleva clinical note binder by patient ID to create an immutable review set.</p>
                  </div>
                ) : (
                  noteSetSummaries.map((noteSet) => (
                    <button
                      key={noteSet.id}
                      type='button'
                      className={`queue-card ${selectedNoteSetId === noteSet.id && showUploadWorkspace ? 'queue-card--active' : ''}`}
                      onClick={() => void selectNoteSet(noteSet.id)}
                    >
                      <div className='queue-card__header'>
                        <strong>{noteSet.patient_id}</strong>
                        <span className={noteSetStatusClassName(noteSet.status)}>{NOTE_SET_STATUS_LABELS[noteSet.status]}</span>
                      </div>
                      <p>{noteSet.level_of_care || 'Level of care not entered yet'}</p>
                      <div className='queue-card__meta'>
                        <span>Version {noteSet.version}</span>
                        <span>{noteSet.file_count} file{noteSet.file_count === 1 ? '' : 's'}</span>
                      </div>
                      <div className='queue-card__counts'>
                        <span>{noteSet.primary_clinician || 'No clinician listed'}</span>
                        <span>{ALLEVA_BUCKET_LABELS.custom_forms} workflow</span>
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
                <p className='panel-lead'>Capture the patient ID and episode header first. The full checklist will load immediately after creation.</p>
                <form className='editor-grid' onSubmit={createChart}>
                  <label>
                    Patient ID
                    <input value={newChartForm.patient_id} onChange={(event) => setNewChartForm({ ...newChartForm, patient_id: event.target.value })} placeholder='PAT-001' />
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
                    <textarea value={newChartForm.other_details} onChange={(event) => setNewChartForm({ ...newChartForm, other_details: event.target.value })} placeholder='Use this field for multi-LOC notes, note-set linkage, or episode-level context.' />
                  </label>
                  <label className='editor-grid__full'>
                    Initial audit summary
                    <textarea value={newChartForm.notes} onChange={(event) => setNewChartForm({ ...newChartForm, notes: event.target.value })} placeholder='Optional handoff summary or opening notes for the reviewer.' />
                  </label>
                  <div className='editor-actions editor-grid__full'>
                    <button type='submit'>Create audit and load checklist</button>
                    <button type='button' className='ghost-button' onClick={() => openUploadWorkspace(newChartForm.patient_id)}>Upload patient notes first</button>
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
            ) : showUploadWorkspace ? (
              <>
                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Intake</p>
                      <h2>Patient Note Intake</h2>
                    </div>
                    {selectedNoteSetDetail ? (
                      <button className='ghost-button' onClick={() => startAuditFromNoteSet(selectedNoteSetDetail)}>Start audit from note set</button>
                    ) : null}
                  </div>
                  <p className='panel-lead'>Upload the clinical note binder by patient ID. Updates create a new immutable version instead of overwriting the prior binder.</p>
                  <form className='section-stack' onSubmit={uploadPatientNotes}>
                    <div className='editor-grid'>
                      <label>
                        Patient ID
                        <input value={uploadForm.patient_id} onChange={(event) => updateUploadField('patient_id', event.target.value)} placeholder='PAT-001' />
                      </label>
                      <label>
                        Upload mode
                        <select value={uploadForm.upload_mode} onChange={(event) => updateUploadField('upload_mode', event.target.value)}>
                          <option value='initial'>First upload</option>
                          <option value='update'>Update existing set</option>
                        </select>
                      </label>
                      <label>
                        Level of care
                        <input value={uploadForm.level_of_care} onChange={(event) => updateUploadField('level_of_care', event.target.value)} placeholder='IOP, PHP, Residential...' />
                      </label>
                      <label>
                        Admission date
                        <input value={uploadForm.admission_date} onChange={(event) => updateUploadField('admission_date', event.target.value)} placeholder='MM/DD/YYYY' />
                      </label>
                      <label>
                        Discharge date
                        <input value={uploadForm.discharge_date} onChange={(event) => updateUploadField('discharge_date', event.target.value)} placeholder='MM/DD/YYYY' />
                      </label>
                      <label>
                        Primary clinician
                        <input value={uploadForm.primary_clinician} onChange={(event) => updateUploadField('primary_clinician', event.target.value)} placeholder='Primary clinician' />
                      </label>
                      <label className='editor-grid__full'>
                        Binder handoff notes
                        <textarea value={uploadForm.upload_notes} onChange={(event) => updateUploadField('upload_notes', event.target.value)} placeholder='Explain what was imported, what changed, or why this version is being uploaded.' />
                      </label>
                      <label className='editor-grid__full file-input-field'>
                        Files
                        <input type='file' multiple onChange={handleUploadFiles} />
                      </label>
                    </div>

                    {uploadForm.entries.length > 0 ? (
                      <div className='section-stack'>
                        {uploadForm.entries.map((entry, index) => (
                          <article key={`${entry.file.name}-${index}`} className='upload-card'>
                            <div className='checklist-card__header'>
                              <div>
                                <p className='eyebrow'>File {index + 1}</p>
                                <h3>{entry.file.name}</h3>
                                <p className='timeframe'>{bytesLabel(entry.file.size)}</p>
                              </div>
                              <span className={noteSetStatusClassName(uploadForm.upload_mode === 'initial' ? 'active' : 'superseded')}>
                                {uploadForm.upload_mode === 'initial' ? 'Initial' : 'Update'}
                              </span>
                            </div>
                            <div className='editor-grid editor-grid--compact'>
                              <label>
                                Document label
                                <input value={entry.document_label} onChange={(event) => updateUploadEntry(index, { document_label: event.target.value })} />
                              </label>
                              <label>
                                Alleva bucket
                                <select value={entry.alleva_bucket} onChange={(event) => updateUploadEntry(index, { alleva_bucket: event.target.value as AllevaBucket })}>
                                  {Object.entries(ALLEVA_BUCKET_LABELS).map(([value, label]) => (
                                    <option key={value} value={value}>{label}</option>
                                  ))}
                                </select>
                              </label>
                              <label>
                                Document type
                                <input value={entry.document_type} onChange={(event) => updateUploadEntry(index, { document_type: event.target.value })} placeholder='clinical_note, ROI, lab_result...' />
                              </label>
                              <label>
                                Completion status
                                <select value={entry.completion_status} onChange={(event) => updateUploadEntry(index, { completion_status: event.target.value as DocumentCompletionStatus })}>
                                  {Object.entries(DOCUMENT_STATUS_LABELS).map(([value, label]) => (
                                    <option key={value} value={value}>{label}</option>
                                  ))}
                                </select>
                              </label>
                              <label>
                                Document date
                                <input value={entry.document_date} onChange={(event) => updateUploadEntry(index, { document_date: event.target.value })} placeholder='MM/DD/YYYY' />
                              </label>
                              <label className='editor-grid__full'>
                                Description / evidence note
                                <textarea value={entry.description} onChange={(event) => updateUploadEntry(index, { description: event.target.value })} placeholder='Describe the document, its role in the audit, or any Alleva-specific context.' />
                              </label>
                            </div>
                            <div className='checkbox-row'>
                              <label className='checkbox-field'>
                                <input type='checkbox' checked={entry.client_signed} onChange={(event) => updateUploadEntry(index, { client_signed: event.target.checked })} />
                                <span>Client signature present</span>
                              </label>
                              <label className='checkbox-field'>
                                <input type='checkbox' checked={entry.staff_signed} onChange={(event) => updateUploadEntry(index, { staff_signed: event.target.checked })} />
                                <span>Staff signature present</span>
                              </label>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className='empty-queue'>
                        <strong>No files selected yet.</strong>
                        <p>Choose one or more documents from the Alleva export, then tag them with the bucket, status, signatures, and date.</p>
                      </div>
                    )}

                    <div className='editor-actions'>
                      <button type='submit'>Upload patient note set</button>
                      <button type='button' className='ghost-button' onClick={() => setUploadForm(createUploadForm({ patient_id: uploadForm.patient_id }))}>Clear files</button>
                      {selectedNoteSetDetail ? (
                        <button type='button' className='ghost-button' onClick={() => startAuditFromNoteSet(selectedNoteSetDetail)}>Create audit from this patient</button>
                      ) : null}
                    </div>
                  </form>
                </section>

                {selectedNoteSetDetail ? (
                  <section className='panel'>
                    <div className='panel-heading'>
                      <div>
                        <p className='eyebrow'>Binder Detail</p>
                        <h2>Patient {selectedNoteSetDetail.patient_id}</h2>
                      </div>
                      <div className='panel-heading__actions'>
                        <span className={noteSetStatusClassName(selectedNoteSetDetail.status)}>{NOTE_SET_STATUS_LABELS[selectedNoteSetDetail.status]}</span>
                        <button className='secondary-button' onClick={() => startAuditFromNoteSet(selectedNoteSetDetail)}>Start audit from binder</button>
                      </div>
                    </div>
                    <div className='queue-summary'>
                      <div>
                        <span className='metric-value'>v{selectedNoteSetDetail.version}</span>
                        <span className='metric-label'>Current version</span>
                      </div>
                      <div>
                        <span className='metric-value'>{selectedNoteSetDetail.file_count}</span>
                        <span className='metric-label'>Files in binder</span>
                      </div>
                      <div>
                        <span className='metric-value'>{selectedNoteSetDetail.primary_clinician || 'Unset'}</span>
                        <span className='metric-label'>Primary clinician</span>
                      </div>
                    </div>
                    {selectedNoteSetDetail.upload_notes ? (
                      <div className='hint-box'>
                        <strong>Version note</strong>
                        <p>{selectedNoteSetDetail.upload_notes}</p>
                      </div>
                    ) : null}
                    <div className='document-table-wrap'>
                      <table className='document-table'>
                        <thead>
                          <tr>
                            <th>Document</th>
                            <th>Bucket</th>
                            <th>Status</th>
                            <th>Date</th>
                            <th>Signatures</th>
                            <th>File</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {selectedNoteSetDetail.documents.map((document) => (
                            <tr key={document.id}>
                              <td>
                                <strong>{document.document_label}</strong>
                                <p>{document.description || document.document_type}</p>
                              </td>
                              <td>{ALLEVA_BUCKET_LABELS[document.alleva_bucket]}</td>
                              <td>{DOCUMENT_STATUS_LABELS[document.completion_status]}</td>
                              <td>{document.document_date || 'Not entered'}</td>
                              <td>
                                {document.client_signed ? 'Client' : 'No client'}
                                {' / '}
                                {document.staff_signed ? 'Staff' : 'No staff'}
                              </td>
                              <td>
                                <strong>{document.original_filename}</strong>
                                <p>{bytesLabel(document.size_bytes)} • {document.sha256.slice(0, 10)}...</p>
                              </td>
                              <td>
                                <button type='button' className='ghost-button' onClick={() => void downloadDocument(selectedNoteSetDetail.id, document)}>
                                  Download
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                ) : (
                  <section className='panel'>
                    <h2>Choose a Patient Note Set</h2>
                    <p className='panel-lead'>Select an existing binder from the sidebar or upload a new set to begin the patient note workflow.</p>
                  </section>
                )}
              </>
            ) : chartDraft && activeSummary ? (
              <>
                <section className='panel'>
                  <div className='panel-heading'>
                    <div>
                      <p className='eyebrow'>Active Audit</p>
                      <h2>Patient {chartLabel(chartDraft)}</h2>
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
                      Patient ID
                      <input value={chartDraft.patient_id} onChange={(event) => updateDraftField('patient_id', event.target.value)} />
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
                      <p className='eyebrow'>Clinical Notes</p>
                      <h2>Linked Note Binder</h2>
                    </div>
                    <div className='panel-heading__actions'>
                      <button className='ghost-button' onClick={() => openUploadWorkspace(chartDraft.patient_id, linkedNoteSet || selectedNoteSetDetail)}>
                        {linkedNoteSet ? 'Update note set' : 'Upload note set'}
                      </button>
                      {linkedNoteSet ? <button className='secondary-button' onClick={() => void selectNoteSet(linkedNoteSet.id)}>Open binder</button> : null}
                    </div>
                  </div>
                  {linkedNoteSet ? (
                    <div className='hint-box'>
                      <strong>Linked binder available</strong>
                      <p>
                        Patient {linkedNoteSet.patient_id} has note set version {linkedNoteSet.version} with {linkedNoteSet.file_count} file{linkedNoteSet.file_count === 1 ? '' : 's'}.
                        Use it while verifying releases, biopsychosocial documents, labs, medication entries, and signatures.
                      </p>
                    </div>
                  ) : (
                    <div className='empty-queue'>
                      <strong>No note binder linked to this patient yet.</strong>
                      <p>Upload the Alleva document set by patient ID so reviewers can cross-check the audit checklist against the source material.</p>
                    </div>
                  )}
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
                <h2>Choose a Chart Audit or Patient Note Set</h2>
                <p className='panel-lead'>Select an audit from the queue, open a patient note binder, or start a new workflow using a patient ID.</p>
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
