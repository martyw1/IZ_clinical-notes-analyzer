export function HelpPage() {
  return (
    <div className='page-grid'>
      <section className='panel'>
        <p className='eyebrow'>Help</p>
        <h2>Using IZ Clinical Notes Analyzer</h2>
        <p>Use this local app to find an exact patient record and saved plan version, compare source evidence with calculated dates, and record an authorized review. Check the evidence behind a status before acting.</p>
        <nav aria-label='Help topics'>
          <ul>
            <li><a href='#help-start'>Start and sign in</a></li>
            <li><a href='#help-find'>Find the right record</a></li>
            <li><a href='#help-dates'>Deadlines and statuses</a></li>
            <li><a href='#help-review'>Review and correct</a></li>
            <li><a href='#help-import'>Import records</a></li>
            <li><a href='#help-access'>Accounts and access</a></li>
            <li><a href='#help-problems'>Troubleshooting</a></li>
          </ul>
        </nav>
      </section>

      <section className='panel' id='help-start'>
        <h2>Start and sign in</h2>
        <ol>
          <li>Use the desktop or Start Menu shortcut. If the app is already running, open <code>http://localhost:8000</code> on this laptop.</li>
          <li>Sign in with your assigned app account. Change a temporary password when prompted.</li>
          <li>Open Status Dashboard to see saved records, attention counts, source readiness, and unresolved blockers.</li>
        </ol>
        <p>The current source candidate is 1.0.0 · build 2026.09.21.2 · stable-local-desktop. The footer identifies the version actually running. After an approved update, refresh the browser and check it before reporting a problem. Full production qualification remains pending.</p>
      </section>

      <section className='panel' id='help-find'>
        <h2>Find the right record</h2>
        <ol>
          <li>Search Patient Roster by MRN, name, plan ID, reference, or service date. Open patient detail for the full source record.</li>
          <li>Use Treatment Plans Roster to filter plans by source and status, then open the exact plan. Both rosters initially show all sources.</li>
          <li>Check source, patient record number, plan ID, and saved version ID. MRNs and external IDs can repeat across sources or facilities.</li>
          <li>On Treatment Plan Detail, use the saved-version selector to inspect history. A new import does not silently replace your selection.</li>
        </ol>
        <p>Missing names, references, and service dates are shown as unavailable or not supplied. Do not infer identity from a name alone.</p>
      </section>

      <section className='panel' id='help-dates'>
        <h2>Deadlines and statuses</h2>
        <p>The versioned rules check an initial plan on admission Day 1, a signed master plan within 30 calendar days of admission, recurring PHP reviews every 30 calendar days, and recurring IOP/OP reviews every 60 calendar days. The recurring clock starts from the latest valid signed review, or admission if none exists. Plan detail compares its calculated date with the source Next Review Due date.</p>
        <dl>
          <div><dt>Overdue</dt><dd>A confirmed deadline has passed, including a late master-plan signature. Open the checklist to see which requirement caused it.</dd></div>
          <div><dt>Urgent or Due Soon</dt><dd>The recurring due date is today or tomorrow, or within the next two to seven days.</dd></div>
          <div><dt>Current/Compliant</dt><dd>Evaluated timing evidence is currently in window. This does not replace review of every checklist criterion and source document.</dd></div>
          <div><dt>Missing Data</dt><dd>Required dates, typed signatures, or plan evidence are absent.</dd></div>
          <div><dt>Conflicting Evidence</dt><dd>Source dates or other required evidence disagree with the calculation.</dd></div>
          <div><dt>Unable to Evaluate</dt><dd>A date or level of care cannot be interpreted under the active rules.</dd></div>
          <div><dt>Needs Review</dt><dd>A person must resolve an issue such as an LOC change or a Day-1 signature mismatch.</dd></div>
        </dl>
        <div className='warning-band'>An LOC change is a separate unresolved rule. The displayed seven-calendar-day date is a provisional candidate, not an enforced deadline. LOC-change cases remain Needs Review until R3/Marleigh confirms the days, calendar/business basis, and clock start. Do not mark a case compliant solely from that candidate.</div>
        <p>Settings shows active timing values from the versioned rule package. Clinical intervals cannot be changed on the Settings screen.</p>
      </section>

      <section className='panel' id='help-review'>
        <h2>Review and correct a plan</h2>
        <ol>
          <li>Open the exact saved plan and compare source due date, computed due date, signatures, LOC history, and data-quality warnings.</li>
          <li>Search the 42-step checklist for the criterion behind a status. Open a row to inspect safe evidence and its source path.</li>
          <li>Check the original source when data is missing or conflicting. Use correction, return, comment, approval, or override only when your role permits it.</li>
          <li>Give a reason for an override. It records a review decision; it does not change the source document or establish an unconfirmed clinical policy.</li>
        </ol>
        <p>CSV exports include filtered results, including off-screen rows, but omit names and narrative content. Verify your selection before sharing through an approved channel.</p>
      </section>

      <section className='panel' id='help-import'>
        <h2>Import records</h2>
        <h3>Manual upload</h3>
        <p>Choose approved binder files and provide an MRN correction only when needed. Review processing warnings and open the saved plan afterward. Secure storage does not mean a file was parsed or found compliant.</p>
        <h3>Alleva patient and treatment-plan pulls</h3>
        <p>Authorized administrators can use Pull patient roster in Patient Roster and Pull full treatment plans in Treatment Plans Roster. The latter requires a saved connection and explicit approved read-only import settings. Watch each job through completion; a connection test alone does not prove every patient or plan page was retrieved.</p>
        <p>API Testing Harness provides bounded diagnostics and redacted previews. It does not replace checking imported records in the rosters. Review warnings and failed-record counts before treating a pull as complete.</p>
      </section>

      <section className='panel' id='help-access'>
        <h2>Accounts and access</h2>
        <p>Open Account to change your password or generate a replacement recovery code. Keep the code privately; it is shown once and works once. If locked out, use Forgot password with your username and saved code, or ask an authorized administrator for a reset. Administrators manage staff accounts in Users; navigation and actions vary by role.</p>
        <p>Settings controls organization, facility timezone, and the authorized API connection. Clinical rule values are shown for reference only. Forensic Logs is an administrator view of audited actions.</p>
      </section>

      <section className='panel' id='help-problems'>
        <h2>Troubleshooting and support</h2>
        <dl>
          <div><dt>The page will not open</dt><dd>Check that the app launcher is running, then try <code>http://localhost:8000</code>. If it still fails, contact R3 support.</dd></div>
          <div><dt>A roster looks empty or old</dt><dd>Clear filters, check the Source selector, refresh the roster, and inspect the last pull job and warnings.</dd></div>
          <div><dt>A plan status looks wrong</dt><dd>Open the exact version, compare source and computed dates, then inspect the checklist criterion and LOC history.</dd></div>
          <div><dt>An API pull fails</dt><dd>Record the job time, phase, and non-sensitive error summary. Do not repeatedly start imports while a job is running.</dd></div>
        </dl>
        <p>For support, send the app version, approximate time, screen name, and a non-PHI error message through the approved R3 channel. Keep patient content, passwords, recovery codes, raw logs, and API credentials out of ordinary chat or email. Sign out and lock Windows when finished.</p>
      </section>
    </div>
  )
}
