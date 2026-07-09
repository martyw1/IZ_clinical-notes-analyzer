<<<<<<< HEAD
import { useEffect, useState } from 'react'
import { getDashboard } from '../api/client'
import { ApiRequestError } from '../api/json'
import type { DashboardData } from '../api/types'

type DashboardPageProps = {
  readonly token: string
}

const metricLabels: Record<string, string> = {
  active_patient_ids: 'Active patient IDs',
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
  }, [token])

  if (error) {
    return <section className='panel error-banner' role='alert'>{error}</section>
  }

  if (!dashboard) {
    return <section className='panel muted'>Loading source readiness...</section>
  }

=======
import { dashboardMetrics, syntheticTreatmentPlan } from '../data'
import { StatusBadge } from '../components/StatusBadge'

export function DashboardPage() {
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
  return (
    <div className='page-grid'>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Status Dashboard</p>
            <h2>Source readiness</h2>
          </div>
<<<<<<< HEAD
          <span className='runtime-pill'>Backend-backed</span>
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
=======
          <StatusBadge status={syntheticTreatmentPlan.status} />
        </div>
        <div className='source-card-grid'>
          <article className='source-card'>
            <h3>Manual upload readiness</h3>
            <p>Ready for PDF, CSV, TSV, XLSX, TXT/MD, and manager metadata correction.</p>
          </article>
          <article className='source-card'>
            <h3>API readiness</h3>
            <p>Alleva/OpenAPI harness supports bounded testing and redacted reports.</p>
          </article>
          <article className='source-card source-card--blocked'>
            <h3>Alleva treatment-plan sync readiness</h3>
            <p>Live sync remains blocked pending R3/Alleva approval and endpoint mapping validation.</p>
          </article>
        </div>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
      </section>
      <section className='panel'>
        <h2>Risk metrics</h2>
        <div className='metric-grid'>
<<<<<<< HEAD
          {Object.entries(dashboard.metrics).map(([key, value]) => (
            <div key={key} className='metric-tile'>
              <dt>{metricLabels[key] ?? key}</dt>
=======
          {dashboardMetrics.map(([label, value]) => (
            <div key={label} className='metric-tile'>
              <dt>{label}</dt>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
              <dd>{value}</dd>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
