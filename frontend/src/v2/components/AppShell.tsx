import type { ReactNode } from 'react'
<<<<<<< HEAD
import type { UserProfile } from '../api/types'

type AppShellProps = {
  readonly activeView: string
  readonly navigationItems: readonly string[]
  readonly user: UserProfile
  readonly onNavigate: (view: string) => void
  readonly onSignOut: () => void
  readonly children: ReactNode
}

export function AppShell({ activeView, navigationItems, user, onNavigate, onSignOut, children }: AppShellProps) {
=======

type AppShellProps = {
  readonly activeView: string
  readonly onNavigate: (view: string) => void
  readonly children: ReactNode
}

const navigation = [
  'Status Dashboard',
  'Treatment Plans',
  'Manual Upload',
  'API Testing Harness',
  'Users',
  'Forensic Logs',
  'Settings',
  'Help',
] as const

export function AppShell({ activeView, onNavigate, children }: AppShellProps) {
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
  return (
    <div className='v2-shell'>
      <header className='v2-topbar'>
        <div>
          <p className='eyebrow'>IZ Clinical Notes Analyzer</p>
          <h1>Version 2.0 Beta</h1>
        </div>
<<<<<<< HEAD
        <div className='topbar-actions'>
          <p className='runtime-pill'>Active runtime: V2 | {user.role}</p>
          <button type='button' className='secondary-button' onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>
      <nav className='v2-nav' aria-label='Primary navigation'>
        {navigationItems.map((item) => (
=======
        <p className='runtime-pill'>Active runtime: V2</p>
      </header>
      <nav className='v2-nav' aria-label='Primary navigation'>
        {navigation.map((item) => (
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
          <button
            key={item}
            type='button'
            className='nav-button'
            aria-pressed={activeView === item}
            onClick={() => onNavigate(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      <main>{children}</main>
      <footer className='v2-footer'>Version 2.0 Beta | 2.0.0-beta.1 | beta-local-desktop-v2</footer>
    </div>
  )
}
