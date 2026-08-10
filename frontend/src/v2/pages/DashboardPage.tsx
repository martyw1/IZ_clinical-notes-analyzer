import { useEffect, useState } from 'react'
import { getDashboard } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { DashboardData } from '../api/types'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'

type DashboardPageProps = {
  readonly token: string
}

const metricLabels: Record<string, string> = {
  active_patient_ids: 'Active MRNs',
  overdue_plans: 'Overdue',
  urgent_plans: 'Urgent',
  due_soon_plans: 'Due soon',
  needs_review: 'Needs review',
  missing_data: 'Missing data',
  returned: 'Returned',
  conflicting: 'Conflicting',
  unable: 'Unable',
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load dashboard data.'
}

export function DashboardPage({ token }: DashboardPageProps) {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function loadDashboard() {
      try {
        const payload = await getDashboard(token)
        if (!cancelled) setDashboard(payload)
      } catch (loadError) {
        if (!cancelled) setError(messageForError(loadError))
      }
    }
    void loadDashboard()
    return () => {
      cancelled = true
    }
  }, [refreshNumber, token])

  if (error) {
    return <section className='panel error-banner' role='alert'>{error}</section>
  }

  if (!dashboard) {
    return <section className='panel muted'>Loading source readiness...</section>
  }

  return (
    <div className='page-grid'>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Status Dashboard</p>
            <h2>Source readiness</h2>
          </div>
          <span className='runtime-pill'>Backend-backed</span>
        </div>
        <div className='button-row'>
          <time dateTime={dashboard.refreshedAt}>Refreshed {formatDateTime24Hour(dashboard.refreshedAt)}</time>
          <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh dashboard</button>
        </div>
        <div className='source-card-grid'>
          {dashboard.sourceCards.map((card) => (
            <article key={card.label} className={card.status === 'blocked' ? 'source-card source-card--blocked' : 'source-card'}>
              <h3>{card.label}</h3>
              <p className='runtime-pill'>{card.status}</p>
              <p>{card.detail}</p>
            </article>
          ))}
        </div>
        {dashboard.blockers.length > 0 && (
          <div className='warning-band'>
            {dashboard.blockers.map((blocker) => <p key={blocker}>{blocker}</p>)}
          </div>
        )}
      </section>
      <section className='panel'>
        <h2>Risk metrics</h2>
        <div className='metric-grid'>
          {Object.entries(dashboard.metrics).map(([key, value]) => (
            <div key={key} className='metric-tile'>
              <dt>{metricLabels[key] ?? key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
