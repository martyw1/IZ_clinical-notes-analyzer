import { dashboardMetrics, syntheticTreatmentPlan } from '../data'
import { StatusBadge } from '../components/StatusBadge'

export function DashboardPage() {
  return (
    <div className='page-grid'>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Status Dashboard</p>
            <h2>Source readiness</h2>
          </div>
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
      </section>
      <section className='panel'>
        <h2>Risk metrics</h2>
        <div className='metric-grid'>
          {dashboardMetrics.map(([label, value]) => (
            <div key={label} className='metric-tile'>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
