import type { OperationalFilter, StatusSummary } from '../clinicalOperationsModel'

export type EvidenceTimelineStep = {
  readonly label: string
  readonly date: string
  readonly source: string
  readonly confidence: string
  readonly tone: string
}

export type SourceComparisonRow = {
  readonly field: string
  readonly manualUpload: string
  readonly api: string
  readonly allevaSync: string
  readonly result: string
  readonly tone: string
}

export type EvidenceLedgerEntry = {
  readonly label: string
  readonly detail: string
  readonly timestamp: string
  readonly tone: string
}

export type SourceReadinessCardModel = {
  readonly title: string
  readonly state: string
  readonly tone: string
  readonly description: string
  readonly facts: readonly { readonly label: string; readonly value: string }[]
  readonly blockers: readonly string[]
  readonly allowedActions: readonly string[]
  readonly disabledActions: readonly string[]
  readonly prerequisites: readonly string[]
}

type RiskStatusStripProps = {
  readonly summaries: readonly StatusSummary[]
  readonly activeFilter?: OperationalFilter
  readonly allCount?: number
  readonly onSelect?: (filter: OperationalFilter) => void
  readonly label?: string
  readonly className?: string
}

export function RiskStatusStrip({ summaries, activeFilter, allCount, onSelect, label = 'Risk status', className = '' }: RiskStatusStripProps) {
  const classes = ['risk-status-strip', className].filter(Boolean).join(' ')
  return (
    <div className={classes} aria-label={label}>
      {allCount != null ? (
        <button
          type='button'
          className={activeFilter === 'All' ? 'risk-status-segment risk-status-segment--active' : 'risk-status-segment'}
          aria-pressed={activeFilter === 'All'}
          onClick={() => onSelect?.('All')}
          disabled={!onSelect}
        >
          <span className='risk-status-segment__dot risk-status-segment__dot--all' />
          <span>All</span>
          <strong>{allCount}</strong>
        </button>
      ) : null}
      {summaries.map((summary) => (
        <button
          type='button'
          key={summary.status}
          title={summary.helper}
          className={activeFilter === summary.status ? 'risk-status-segment risk-status-segment--active' : 'risk-status-segment'}
          aria-pressed={activeFilter === summary.status}
          onClick={() => onSelect?.(summary.status)}
          disabled={!onSelect}
        >
          <span className={`risk-status-segment__dot risk-status-segment__dot--${summary.tone}`} />
          <span>{summary.label}</span>
          <strong>{summary.count}</strong>
        </button>
      ))}
    </div>
  )
}

export function EmptyTreatmentPlanDetail({
  onPull,
  onUpload,
  onReadiness,
  onSettings,
  canPull,
  canOpenSettings,
}: {
  readonly onPull: () => void
  readonly onUpload: () => void
  readonly onReadiness: () => void
  readonly onSettings: () => void
  readonly canPull: boolean
  readonly canOpenSettings: boolean
}) {
  return (
    <section className='workbench-empty-state' aria-label='No treatment-plan client selected'>
      <div>
        <h2>Select a client from the queue</h2>
        <p>Select a client from the queue to review due dates, source evidence, checklist findings, overrides, and audit history.</p>
      </div>
      <ol className='workbench-empty-steps'>
        <li>
          <strong>Load clients</strong>
          <span>Pull treatment plans from the approved source or upload a binder.</span>
        </li>
        <li>
          <strong>Select a risk row</strong>
          <span>Choose an overdue, urgent, or needs-review client from the queue.</span>
        </li>
        <li>
          <strong>Review source evidence</strong>
          <span>Confirm dates, checklist findings, source completeness, overrides, and audit history.</span>
        </li>
      </ol>
      <div className='button-row'>
        {canPull ? (
          <button type='button' onClick={onPull}>
            Pull treatment plans
          </button>
        ) : null}
        <button type='button' className='ghost-button' onClick={onUpload}>
          Upload binder
        </button>
        <button type='button' className='ghost-button' onClick={onReadiness}>
          Open API readiness
        </button>
        {canOpenSettings ? (
          <button type='button' className='ghost-button' onClick={onSettings}>
            Review settings
          </button>
        ) : null}
      </div>
    </section>
  )
}

export function DateEvidenceTimeline({ steps }: { readonly steps: readonly EvidenceTimelineStep[] }) {
  return (
    <section className='date-evidence-timeline' aria-label='Date evidence timeline'>
      <div className='panel-heading'>
        <div>
          <h3>Date evidence timeline</h3>
          <p>Admission, treatment-plan, LOC, and update dates in the order used for the current result.</p>
        </div>
      </div>
      <ol>
        {steps.map((step) => (
          <li key={step.label} className={`date-evidence-timeline__step date-evidence-timeline__step--${step.tone}`}>
            <span>{step.label}</span>
            <strong>{step.date}</strong>
            <small>{step.source}</small>
            <small>{step.confidence}</small>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function SourceComparisonTable({ rows }: { readonly rows: readonly SourceComparisonRow[] }) {
  return (
    <section className='source-comparison-table' aria-label='Source comparison'>
      <div className='panel-heading'>
        <div>
          <h3>Source comparison</h3>
          <p>Manual upload, API readiness, and Alleva sync evidence compared without exposing direct identifiers.</p>
        </div>
      </div>
      <div role='table'>
        <div className='source-comparison-table__head' role='row'>
          <span>Field</span>
          <span>Manual upload</span>
          <span>API</span>
          <span>Alleva sync</span>
          <span>Result</span>
        </div>
        {rows.map((row) => (
          <div key={row.field} className='source-comparison-table__row' role='row'>
            <span>{row.field}</span>
            <span>{row.manualUpload}</span>
            <span>{row.api}</span>
            <span>{row.allevaSync}</span>
            <span>
              <span className={`pill pill--${row.tone}`}>{row.result}</span>
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

export function EvidenceLedger({ entries, title = 'Evidence ledger' }: { readonly entries: readonly EvidenceLedgerEntry[]; readonly title?: string }) {
  return (
    <section className='evidence-ledger' aria-label={title}>
      <h3>{title}</h3>
      {entries.length ? (
        <div className='evidence-ledger__list'>
          {entries.map((entry) => (
            <article key={`${entry.label}-${entry.timestamp}`} className={`evidence-ledger__entry evidence-ledger__entry--${entry.tone}`}>
              <strong>{entry.label}</strong>
              <span>{entry.detail}</span>
              <time>{entry.timestamp}</time>
            </article>
          ))}
        </div>
      ) : (
        <p className='empty-state'>No evidence events are loaded yet.</p>
      )}
    </section>
  )
}

export function SourceReadinessCard({ source }: { readonly source: SourceReadinessCardModel }) {
  return (
    <article className={`source-readiness-card source-readiness-card--${source.tone}`}>
      <div className='finding-card__header'>
        <div>
          <h3>{source.title}</h3>
          <p>{source.description}</p>
        </div>
        <span className={`pill pill--${source.tone}`}>{source.state}</span>
      </div>
      <dl className='source-readiness-card__facts'>
        {source.facts.map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      <div className='source-readiness-card__lists'>
        <ReadinessList title='Blockers' items={source.blockers} emptyText='No blockers loaded.' />
        <ReadinessList title='Allowed actions' items={source.allowedActions} emptyText='No actions available.' />
        <ReadinessList title='Disabled actions' items={source.disabledActions} emptyText='No disabled actions.' />
        <ReadinessList title='Prerequisites' items={source.prerequisites} emptyText='No prerequisites loaded.' />
      </div>
    </article>
  )
}

function ReadinessList({ title, items, emptyText }: { readonly title: string; readonly items: readonly string[]; readonly emptyText: string }) {
  return (
    <section>
      <h4>{title}</h4>
      <ul className='compact-list'>
        {(items.length ? items : [emptyText]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  )
}
