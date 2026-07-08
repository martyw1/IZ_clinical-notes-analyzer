import { useState } from 'react'
import { AppShell } from './components/AppShell'
import { ApiHarnessPage } from './pages/ApiHarnessPage'
import { DashboardPage } from './pages/DashboardPage'
import { ForensicLogsPage } from './pages/ForensicLogsPage'
import { HelpPage } from './pages/HelpPage'
import { ManualUploadPage } from './pages/ManualUploadPage'
import { SettingsPage } from './pages/SettingsPage'
import { TreatmentPlansPage } from './pages/TreatmentPlansPage'
import { UsersPage } from './pages/UsersPage'

function pageFor(view: string) {
  switch (view) {
    case 'Status Dashboard':
      return <DashboardPage />
    case 'Treatment Plans':
      return <TreatmentPlansPage />
    case 'Manual Upload':
      return <ManualUploadPage />
    case 'API Testing Harness':
      return <ApiHarnessPage />
    case 'Users':
      return <UsersPage />
    case 'Forensic Logs':
      return <ForensicLogsPage />
    case 'Settings':
      return <SettingsPage />
    case 'Help':
      return <HelpPage />
    default:
      return <DashboardPage />
  }
}

export function AppV2() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [activeView, setActiveView] = useState('Status Dashboard')

  if (!loggedIn) {
    return (
      <main className='login-page'>
        <section className='login-card'>
          <p className='eyebrow'>Version 2.0 Beta</p>
          <h1>IZ Clinical Notes Analyzer</h1>
          <p>Local treatment-plan workbench for synthetic V2 validation.</p>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setLoggedIn(true)
            }}
          >
            <label>
              Username
              <input name='username' defaultValue='admin' autoComplete='username' />
            </label>
            <label>
              Password
              <input name='password' type='password' autoComplete='current-password' />
            </label>
            <button type='submit'>Sign in</button>
          </form>
        </section>
      </main>
    )
  }

  return (
    <AppShell activeView={activeView} onNavigate={setActiveView}>
      {pageFor(activeView)}
    </AppShell>
  )
}
