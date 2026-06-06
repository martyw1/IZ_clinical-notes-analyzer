import './treatment-plan-timeliness-video.css'

type Tone = 'good' | 'warn' | 'urgent' | 'quiet'

const client = {
  name: 'Synthetic Client',
  age: 41,
  status: 'Active',
  admissionDate: '02/26/2026',
  currentLoc: 'IOP 5',
  clinician: 'Synthetic Therapist',
  score: 82,
}

const locRows = [
  { level: 'IOP 5', facility: 'R3 Recovery Services', admission: '03/30/2026', discharge: '-', cadence: '60 days', active: true },
  { level: 'PHP', facility: 'R3 Recovery Services', admission: '02/26/2026', discharge: '03/30/2026', cadence: '30 days', active: false },
]

const evidenceRows = [
  {
    kind: 'Initial',
    source: 'Treatment Plan tab',
    documentDate: '02/26/2026',
    staffSigned: '02/26/2026',
    clientSigned: '02/26/2026',
    due: '02/26/2026',
    status: 'Compliant',
    tone: 'good' as Tone,
  },
  {
    kind: 'Master',
    source: 'Treatment Plan tab',
    documentDate: '03/03/2026',
    staffSigned: '03/03/2026',
    clientSigned: '03/03/2026',
    due: '03/28/2026',
    status: 'Compliant',
    tone: 'good' as Tone,
  },
  {
    kind: 'Review',
    source: 'Treatment Plan Reviews',
    documentDate: '04/02/2026',
    staffSigned: '04/02/2026',
    clientSigned: 'Optional',
    due: '05/29/2026',
    status: 'Needs Review',
    tone: 'warn' as Tone,
  },
]

const ruleRows = [
  {
    label: 'Displayed next due date',
    value: '05/29/2026',
    detail: 'Visible in Treatment Plan Review note',
    tone: 'warn' as Tone,
  },
  {
    label: 'Signature anchor calculation',
    value: '06/01/2026',
    detail: '04/02/2026 staff signature + 60 days',
    tone: 'quiet' as Tone,
  },
  {
    label: 'LOC anchor calculation',
    value: '05/29/2026',
    detail: '03/30/2026 IOP 5 effective date + 60 days',
    tone: 'good' as Tone,
  },
]

function StatusBadge({ tone, children }: { tone: Tone; children: string }) {
  return <span className={`tpv-badge tpv-badge--${tone}`}>{children}</span>
}

function IconButton({ label, icon }: { label: string; icon: string }) {
  return (
    <button type="button" className="tpv-icon-button" aria-label={label} title={label}>
      {icon}
    </button>
  )
}

export function TreatmentPlanTimelinessVideoMockup() {
  return (
    <main className="tpv-app-shell">
      <aside className="tpv-sidebar" aria-label="Client navigation">
        <div className="tpv-operator">
          <div className="tpv-avatar" aria-hidden="true">MJ</div>
          <div>
            <strong>Clinical Admin</strong>
            <span>R3 Recovery Services</span>
          </div>
        </div>
        <nav className="tpv-nav">
          {['Dashboard', 'Client chart', 'Calendar', 'Documents', 'Notes', 'Treatment Plan', 'Timeliness'].map((item) => (
            <button key={item} type="button" className={item === 'Timeliness' ? 'is-active' : ''}>
              <span aria-hidden="true">{item === 'Timeliness' ? '!' : '+'}</span>
              {item}
            </button>
          ))}
        </nav>
      </aside>

      <section className="tpv-workspace">
        <header className="tpv-topbar">
          <div className="tpv-brand">
            <IconButton label="Open menu" icon="=" />
            <span className="tpv-logo-mark" aria-hidden="true" />
            <strong>IZ Clinical Notes Analyzer</strong>
          </div>
          <label className="tpv-search">
            <span>Search clients</span>
            <input type="search" placeholder="Client, level of care, due date" />
          </label>
          <div className="tpv-actions">
            <IconButton label="Calendar" icon="[]" />
            <IconButton label="Help" icon="?" />
            <IconButton label="Notifications" icon="!" />
          </div>
        </header>

        <section className="tpv-page-title">
          <div>
            <p>Current overview</p>
            <h1>Treatment plan timeliness</h1>
          </div>
          <button type="button" className="tpv-primary-action">Export task list</button>
        </section>

        <section className="tpv-client-summary" aria-label="Selected client summary">
          <div className="tpv-client-photo" aria-hidden="true">SC</div>
          <div className="tpv-client-main">
            <div className="tpv-client-heading">
              <div>
                <h2>{client.name}</h2>
                <p>{client.age} years | Admission {client.admissionDate}</p>
              </div>
              <StatusBadge tone="good">{client.status}</StatusBadge>
            </div>
            <dl className="tpv-facts">
              <div>
                <dt>Current level</dt>
                <dd>{client.currentLoc}</dd>
              </div>
              <div>
                <dt>Primary clinician</dt>
                <dd>{client.clinician}</dd>
              </div>
              <div>
                <dt>Tracker confidence</dt>
                <dd>{client.score}%</dd>
              </div>
            </dl>
          </div>
          <div className="tpv-next-due">
            <span>Next review due</span>
            <strong>05/29/2026</strong>
            <StatusBadge tone="warn">Needs Review</StatusBadge>
          </div>
        </section>

        <section className="tpv-grid">
          <section className="tpv-panel" aria-label="Evidence queue">
            <div className="tpv-panel-title">
              <h2>Verification queue</h2>
              <p>Initial, master, and review evidence from the video workflow.</p>
            </div>
            <div className="tpv-table tpv-evidence-table">
              <div className="tpv-table-head">
                <span>Type</span>
                <span>Source</span>
                <span>Document</span>
                <span>Staff</span>
                <span>Client</span>
                <span>Due</span>
                <span>Status</span>
                <span>Action</span>
              </div>
              {evidenceRows.map((row) => (
                <div className="tpv-table-row" key={row.kind}>
                  <strong>{row.kind}</strong>
                  <span>{row.source}</span>
                  <span>{row.documentDate}</span>
                  <span>{row.staffSigned}</span>
                  <span>{row.clientSigned}</span>
                  <span>{row.due}</span>
                  <StatusBadge tone={row.tone}>{row.status}</StatusBadge>
                  <IconButton label={`View ${row.kind} evidence`} icon=">" />
                </div>
              ))}
            </div>
          </section>

          <section className="tpv-panel" aria-label="Rule comparison">
            <div className="tpv-panel-title">
              <h2>Date comparison</h2>
              <p>Keep this visible until R3 confirms the LOC-change anchor.</p>
            </div>
            <div className="tpv-rule-stack">
              {ruleRows.map((row) => (
                <article className="tpv-rule-row" key={row.label}>
                  <div>
                    <h3>{row.label}</h3>
                    <p>{row.detail}</p>
                  </div>
                  <StatusBadge tone={row.tone}>{row.value}</StatusBadge>
                </article>
              ))}
            </div>
            <div className="tpv-warning">
              <strong>Unvalidated rule</strong>
              <p>Visible due date matches the LOC effective-date anchor, while the current signature-date calculation lands later. Show both and require review.</p>
            </div>
          </section>
        </section>

        <section className="tpv-panel" aria-label="Level of care history">
          <div className="tpv-panel-title">
            <h2>Level of care history</h2>
            <p>Active level is the latest row without a discharge date.</p>
          </div>
          <div className="tpv-table tpv-loc-table">
            <div className="tpv-table-head">
              <span>Level</span>
              <span>Facility</span>
              <span>Admission / effective</span>
              <span>Discharge</span>
              <span>Cadence</span>
              <span>State</span>
            </div>
            {locRows.map((row) => (
              <div className="tpv-table-row" key={row.level}>
                <strong>{row.level}</strong>
                <span>{row.facility}</span>
                <span>{row.admission}</span>
                <span>{row.discharge}</span>
                <span>{row.cadence}</span>
                <StatusBadge tone={row.active ? 'good' : 'quiet'}>{row.active ? 'Current' : 'Ended'}</StatusBadge>
              </div>
            ))}
          </div>
        </section>

        <section className="tpv-document-shell" aria-label="Evidence document preview">
          <div className="tpv-document-title">
            <h2>Treatment Plan Review</h2>
            <div>
              <IconButton label="Print evidence" icon="P" />
              <IconButton label="Close preview" icon="X" />
            </div>
          </div>
          <div className="tpv-document">
            <header>
              <div className="tpv-clinic-mark" aria-hidden="true">R3</div>
              <h3>R3 Recovery Services</h3>
              <p>Treatment Plan Review</p>
            </header>
            <section>
              <h4>Review note</h4>
              <p>Synthetic review note summary. The source video shows this document section immediately above the next-review due field.</p>
            </section>
            <section className="tpv-due-evidence">
              <h4>Next Review Due</h4>
              <strong>05/29/2026</strong>
            </section>
            <section>
              <h4>Staff Signature</h4>
              <div className="tpv-signature-line" aria-hidden="true" />
              <p>Synthetic Therapist, BA</p>
              <p>Apr 2 2026 9:02AM</p>
            </section>
            <section>
              <h4>Client Signature</h4>
              <p>Optional for ongoing reviews in the video workflow.</p>
            </section>
          </div>
        </section>
      </section>
    </main>
  )
}
