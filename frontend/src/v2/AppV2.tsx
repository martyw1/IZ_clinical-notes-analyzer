import { useEffect, useState } from 'react'
import { ApiRequestError } from './api/json'
import { getCurrentUser, getNavigation, login } from './api/client'
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
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'The local V2 API did not respond as expected.'
}

function pageFor(
  view: string,
  token: string,
  user: UserProfile,
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
      return <PatientRosterPage token={token} user={user} onNavigate={onNavigate} onSelectPatient={onSelectPatient} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Patient Record Detail':
      return <PatientRecordDetailPage token={token} selection={patientSelection} onNavigate={onNavigate} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Manual Upload':
      return <ManualUploadPage token={token} onNavigate={onNavigate} />
    case 'Treatment Plan Detail':
      return <TreatmentPlanDetailPage token={token} user={user} selection={selection} onNavigate={onNavigate} />
    case 'Treatment Plans Roster':
      return <TreatmentPlansRosterPage token={token} user={user} onNavigate={onNavigate} onSelectPatient={onSelectPatient} onSelectTreatmentPlan={onSelectTreatmentPlan} />
    case 'Corrections':
      return <CorrectionsPage token={token} />
    case 'API Testing Harness':
      return <ApiHarnessPage token={token} onNavigate={onNavigate} />
    case 'Users':
      return <UsersPage token={token} />
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

  useEffect(() => {
    const storedToken = sessionStorage.getItem(tokenStorageKey)
    if (!storedToken) return

    let cancelled = false
    async function restoreSession(token: string) {
      try {
        const user = await getCurrentUser(token)
        const navigation = user.mustResetPassword ? { items: [] } : await getNavigation(token)
        if (!cancelled) setSession({ token, user, navigationItems: navigation.items })
      } catch (error) {
        sessionStorage.removeItem(tokenStorageKey)
        if (!cancelled) setAuthError(messageForError(error))
      }
    }
    void restoreSession(storedToken)
    return () => {
      cancelled = true
    }
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAuthError('')
    setIsSigningIn(true)
    const form = new FormData(event.currentTarget)
    const username = String(form.get('username') ?? '')
    const password = String(form.get('password') ?? '')
    try {
      const loginResult = await login(username, password)
      const user = await getCurrentUser(loginResult.accessToken)
      const navigation = user.mustResetPassword ? { items: [] } : await getNavigation(loginResult.accessToken)
      sessionStorage.setItem(tokenStorageKey, loginResult.accessToken)
      setActiveView(navigation.items[0] ?? 'Status Dashboard')
      setSelectedTreatmentPlan(null)
      setSelectedPatient(null)
      setSession({ token: loginResult.accessToken, user, navigationItems: navigation.items })
    } catch (error) {
      sessionStorage.removeItem(tokenStorageKey)
      setAuthError(messageForError(error))
    } finally {
      setIsSigningIn(false)
    }
  }

  function handleSignOut() {
    sessionStorage.removeItem(tokenStorageKey)
    setSession(null)
    setActiveView('Status Dashboard')
    setSelectedTreatmentPlan(null)
    setSelectedPatient(null)
  }

  async function refreshSessionUser(token: string) {
    if (!session) return
    const [user, navigation] = await Promise.all([getCurrentUser(token), getNavigation(token)])
    sessionStorage.setItem(tokenStorageKey, token)
    setSession({ token, user, navigationItems: navigation.items })
  }

  if (!session) {
    return (
      <main className='login-page'>
        <section className='login-card'>
          <p className='eyebrow'>Version 2.0 Beta</p>
          <h1>IZ Clinical Notes Analyzer</h1>
          <p>Local treatment-plan workbench for authenticated V2 validation.</p>
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
    setSelectedTreatmentPlan(selection)
    setActiveView('Treatment Plan Detail')
  }

  function handlePatientSelection(selection: PatientSelection) {
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
        setActiveView,
        selectedTreatmentPlan,
        selectedPatient,
        handlePatientSelection,
        handleTreatmentPlanSelection,
      )}
    </AppShell>
  )
}
