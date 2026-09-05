import { useEffect, useRef, useState } from 'react'
import { ApiRequestError } from './api/json'
import { getCurrentUser, getNavigation, login } from './api/client'
import { beginRequestSession, endRequestSession } from './api/request'
import type { PatientSelection, TreatmentPlanSelection, UserProfile } from './api/types'
import { AppShell } from './components/AppShell'
import { ApiHarnessPage } from './pages/ApiHarnessPage'
import { CorrectionsPage } from './pages/CorrectionsPage'
import { DashboardPage } from './pages/DashboardPage'
import { ForensicLogsPage } from './pages/ForensicLogsPage'
import { HelpPage } from './pages/HelpPage'
import { ManualUploadPage } from './pages/ManualUploadPage'
import { PatientRosterPage } from './pages/PatientRosterPage'
import { PatientRecordDetailPage } from './pages/PatientRecordDetailPage'
import { PasswordResetPage } from './pages/PasswordResetPage'
import { SettingsPage } from './pages/SettingsPage'
import { TreatmentPlanDetailPage } from './pages/TreatmentPlanDetailPage'
import { TreatmentPlansRosterPage } from './pages/TreatmentPlansRosterPage'
import { UsersPage } from './pages/UsersPage'

const tokenStorageKey = 'iz-cna-v2-access-token'

type Session = {
  readonly token: string
  readonly user: UserProfile
  readonly navigationItems: readonly string[]
  readonly isCurrent: () => boolean
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  return 'The local V2 API did not respond as expected.'
}

async function readSession(token: string, isCurrent: () => boolean): Promise<Session | null> {
  const user = await getCurrentUser(token)
  if (!isCurrent()) return null
  const navigation = user.mustResetPassword ? { items: [] } : await getNavigation(token)
  return isCurrent() ? { token, user, navigationItems: navigation.items, isCurrent } : null
}

function pageFor(
  view: string,
  token: string,
  user: UserProfile,
  isSessionCurrent: () => boolean,
  onNavigate: (view: string) => void,
  selection: TreatmentPlanSelection | null,
  patientSelection: PatientSelection | null,
  onSelectPatient: (selection: PatientSelection) => void,
  onSelectTreatmentPlan: (selection: TreatmentPlanSelection) => void,
) {
  switch (view) {
    case 'Status Dashboard':
      return <DashboardPage token={token} />
    case 'Patient Roster':
      return <PatientRosterPage isSessionCurrent={isSessionCurrent} token={token} user={user} onNavigate={onNavigate} onSelectPatient={onSelectPatient} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Patient Record Detail':
      return <PatientRecordDetailPage isSessionCurrent={isSessionCurrent} token={token} selection={patientSelection} onNavigate={onNavigate} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Manual Upload':
      return <ManualUploadPage token={token} onNavigate={onNavigate} />
    case 'Treatment Plan Detail':
      return <TreatmentPlanDetailPage token={token} user={user} selection={selection} onNavigate={onNavigate} onSelectTreatmentPlan={onSelectTreatmentPlan} isSessionCurrent={isSessionCurrent} />
    case 'Treatment Plans Roster':
      return <TreatmentPlansRosterPage isSessionCurrent={isSessionCurrent} token={token} user={user} onNavigate={onNavigate} onSelectPatient={onSelectPatient} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Corrections':
      return <CorrectionsPage token={token} isSessionCurrent={isSessionCurrent} />
    case 'API Testing Harness':
      return <ApiHarnessPage token={token} onNavigate={onNavigate} />
    case 'Users':
      return <UsersPage token={token} isSessionCurrent={isSessionCurrent} />
    case 'Forensic Logs':
      return <ForensicLogsPage token={token} />
    case 'Settings':
      return <SettingsPage token={token} />
    case 'Help':
      return <HelpPage />
    default:
      return <DashboardPage token={token} />
  }
}

export function AppV2() {
  const [session, setSession] = useState<Session | null>(null)
  const [activeView, setActiveView] = useState('Status Dashboard')
  const [selectedTreatmentPlan, setSelectedTreatmentPlan] = useState<TreatmentPlanSelection | null>(null)
  const [selectedPatient, setSelectedPatient] = useState<PatientSelection | null>(null)
  const [authError, setAuthError] = useState('')
  const [isSigningIn, setIsSigningIn] = useState(false)
  const authAttempt = useRef(0)
  const signInPending = useRef(false)

  useEffect(() => {
    const storedToken = sessionStorage.getItem(tokenStorageKey)
    if (storedToken) {
      const isCurrent = beginRequestSession(storedToken, handleSessionExpired)
      void readSession(storedToken, isCurrent).then((restored) => {
        if (restored) setSession(restored)
      }).catch((error: unknown) => {
        if (isCurrent()) setAuthError(messageForError(error))
      })
    }
    return () => {
      authAttempt.current += 1
      endRequestSession()
    }
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (signInPending.current) return
    const form = new FormData(event.currentTarget)
    const username = String(form.get('username') ?? '').trim()
    const password = String(form.get('password') ?? '')
    if (!username || !password.trim()) {
      setAuthError('Enter your username and password before signing in.')
      return
    }
    const attempt = ++authAttempt.current
    signInPending.current = true
    endRequestSession()
    setAuthError('')
    setIsSigningIn(true)
    try {
      const loginResult = await login(username, password)
      if (attempt !== authAttempt.current) return
      const restored = await readSession(loginResult.accessToken, beginRequestSession(loginResult.accessToken, handleSessionExpired))
      if (!restored) return
      sessionStorage.setItem(tokenStorageKey, loginResult.accessToken)
      setActiveView(restored.navigationItems[0] ?? 'Status Dashboard')
      setSelectedTreatmentPlan(null)
      setSelectedPatient(null)
      setSession(restored)
    } catch (error) {
      if (attempt === authAttempt.current) setAuthError(messageForError(error))
    } finally {
      if (attempt === authAttempt.current) {
        signInPending.current = false
        setIsSigningIn(false)
      }
    }
  }

  function handleSignOut() {
    authAttempt.current += 1
    signInPending.current = false
    endRequestSession()
    sessionStorage.removeItem(tokenStorageKey)
    setSession(null)
    setIsSigningIn(false)
    setActiveView('Status Dashboard')
    setSelectedTreatmentPlan(null)
    setSelectedPatient(null)
  }

  function handleSessionExpired() {
    handleSignOut()
    setAuthError('Your session has expired. Sign in again to continue.')
  }

  async function refreshSessionUser(token: string) {
    if (!session?.isCurrent()) return
    const isCurrent = beginRequestSession(token, handleSessionExpired)
    sessionStorage.setItem(tokenStorageKey, token)
    setSession({ ...session, token, isCurrent })
    const restored = await readSession(token, isCurrent)
    if (restored) setSession(restored)
  }

  if (!session) {
    return (
      <main className='login-page'>
        <section className='login-card'>
          <p className='eyebrow'>Version 2.0 Beta</p>
          <h1>IZ Clinical Notes Analyzer</h1>
          <p>Review treatment plans, track deadlines, and follow up on corrections.</p>
          <form onSubmit={handleSubmit}>
            <label>
              Username
              <input name='username' defaultValue='admin' autoComplete='username' />
            </label>
            <label>
              Password
              <input name='password' type='password' autoComplete='current-password' />
            </label>
            {authError && <p role='alert' className='error-banner'>{authError}</p>}
            <button type='submit' disabled={isSigningIn}>
              {isSigningIn ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </section>
      </main>
    )
  }

  if (session.user.mustResetPassword) return <PasswordResetPage token={session.token} onChanged={refreshSessionUser} />

  function handleTreatmentPlanSelection(selection: TreatmentPlanSelection) {
    if (!session?.isCurrent()) return
    setSelectedTreatmentPlan(selection)
    setActiveView('Treatment Plan Detail')
  }

  function handlePatientSelection(selection: PatientSelection) {
    if (!session?.isCurrent()) return
    setSelectedPatient(selection)
    setActiveView('Patient Record Detail')
  }

  return (
    <AppShell
      activeView={activeView}
      navigationItems={session.navigationItems}
      user={session.user}
      onNavigate={setActiveView}
      onSignOut={handleSignOut}
    >
      {pageFor(
        activeView,
        session.token,
        session.user,
        session.isCurrent,
        setActiveView,
        selectedTreatmentPlan,
        selectedPatient,
        handlePatientSelection,
        handleTreatmentPlanSelection,
      )}
    </AppShell>
  )
}
