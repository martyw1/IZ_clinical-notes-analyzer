import type { ReactNode } from 'react'

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
  return (
    <div className='v2-shell'>
      <header className='v2-topbar'>
        <div>
          <p className='eyebrow'>IZ Clinical Notes Analyzer</p>
          <h1>Version 2.0 Beta</h1>
        </div>
        <p className='runtime-pill'>Active runtime: V2</p>
      </header>
      <nav className='v2-nav' aria-label='Primary navigation'>
        {navigation.map((item) => (
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
