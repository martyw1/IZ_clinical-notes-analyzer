import { useEffect, useState } from 'react'
import { getDashboard } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { DashboardData } from '../api/types'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'
import { RosterUpdateCard } from '../components/RosterUpdateCard'

type DashboardPageProps = { readonly token: string; readonly isAdmin?: boolean; readonly onNavigate?: (view: string) => void }

const metricGroups = [
  { label: 'Timeliness', keys: ['overdue_plans', 'urgent_plans', 'due_soon_plans'] },
  { label: 'Review and data quality', keys: ['needs_review', 'missing_data', 'conflicting', 'unable'] },
  { label: 'Workload', keys: ['active_patient_ids', 'returned'] },
]

const metricLabels: Record<string, string> = {
  active_patient_ids: 'Patient records with plans',
  overdue_plans: 'Overdue plans',
  urgent_plans: 'Urgent plans',
  due_soon_plans: 'Due soon plans',
  needs_review: 'Plans needing review',
  missing_data: 'Missing Data criteria',
  returned: 'Open correction items',
  conflicting: 'Plans with conflicting evidence',
  unable: 'Plans unable to evaluate',
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load dashboard data.'
}

export function DashboardPage({ token, isAdmin = false, onNavigate }: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function loadDashboard() {
      setError('')
      setIsRefreshing(true)
      try {
        const payload = await getDashboard(token)
        if (!cancelled) setDashboard(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      } finally {
        if (!cancelled) setIsRefreshing(false)
      }
    }
    void loadDashboard()
    return () => { cancelled = true }
  }, [refreshNumber, token])

  return (
    <div className='dashboard-page'>
      <header className='section-heading dashboard-heading'>
        <div>
          <h2>Status dashboard</h2>
          <p className='muted'>Treatment-plan priorities and source readiness.</p>
          {dashboard && <time dateTime={dashboard.refreshedAt}>Counts calculated {formatDateTime24Hour(dashboard.refreshedAt)}</time>}
        </div>
        <button type='button' disabled={isRefreshing} onClick={() => setRefreshNumber((current) => current + 1)}>
          {isRefreshing ? 'Refreshing dashboard...' : 'Refresh dashboard'}
        </button>
      </header>
      {error && <section className='panel error-banner' role='alert'>
        <p>{error}</p>
        {dashboard && <p>Showing the last successful update. Refresh to get current counts.</p>}
      </section>}
      {!dashboard && isRefreshing && <p className='muted' role='status'>Loading source readiness...</p>}
      {dashboard && <>
        <section className='panel dashboard-metrics' aria-busy={isRefreshing}>
          <h2>At a glance</h2>
          {metricGroups.map((group) => <section className='metric-group' key={group.label} aria-label={group.label}>
          <h3>{group.label}</h3>
          <dl className='metric-grid'>
            {group.keys.map((key) => (
              <div key={key} className='metric-tile' data-metric={key}>
                <dt>{metricLabels[key] ?? key}</dt>
                <dd>{dashboard.metrics[key] ?? 0}</dd>
              </div>
            ))}
          </dl>
          </section>)}
          <details className='metric-explanation'>
            <summary>How these counts are calculated</summary>
            <p className='muted'>Authorized patient records with plans, not active-client lifecycle counts. Plan statuses and Missing Data criteria use the latest version of each source plan for each patient record.</p>
            <p className='muted'>Open correction items include authorized, linked items on historical versions. These patient, plan, criterion, and correction-item counts are not a partition and should not be added together.</p>
          </details>
        </section>
        {isAdmin && <RosterUpdateCard token={token} onNavigate={onNavigate} onCompleted={() => setRefreshNumber((current) => current + 1)} />}
        <section className='panel'>
          <h2>Source readiness</h2>
          <div className='source-card-grid'>
            {dashboard.sourceCards.map((card) => (
              <article key={card.label} className={card.status === 'blocked' ? 'source-card source-card--blocked' : 'source-card'}>
                <div className='section-heading'>
                  <h3>{card.label}</h3>
                  <span className='runtime-pill'>{card.status}</span>
                </div>
                <p>{card.detail}</p>
              </article>
            ))}
          </div>
          {dashboard.blockers.length > 0 && <div className='warning-band'>
            {dashboard.blockers.map((blocker) => <p key={blocker}>{blocker}</p>)}
          </div>}
        </section>
      </>}
    </div>
  )
}
