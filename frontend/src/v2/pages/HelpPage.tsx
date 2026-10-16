export function HelpPage() {
  return (
    <div className='page-grid'>
      <section className='panel'>
        <p className='eyebrow'>Help</p>
        <h2>Using R3 Treatment Plan Audit Application</h2>
        <p>Use this local app to find an exact patient record and saved plan version, compare source evidence with calculated dates, and record an authorized review. Check the evidence behind a status before acting.</p>
        <nav aria-label='Help topics'>
          <ul>
            <li><a href='#help-start'>Start and sign in</a></li>
            <li><a href='#help-find'>Find the right record</a></li>
            <li><a href='#help-dates'>Deadlines and statuses</a></li>
            <li><a href='#help-review'>Review and correct</a></li>
            <li><a href='#help-import'>Import records</a></li>
            <li><a href='#help-access'>Accounts and access</a></li>
            <li><a href='#help-backup'>OneDrive ZIP backup and restore</a></li>
            <li><a href='#help-problems'>Troubleshooting</a></li>
          </ul>
        </nav>
      </section>

      <section className='panel' id='help-start'>
        <h2>Start and sign in</h2>
        <ol>
          <li>Double-click <strong>(1) Start IZ Clinical Notes Analyzer</strong> on the desktop and wait for the browser to open. The app runs in the background. If it is already running, open <code>http://localhost:8000</code> on this laptop.</li>
          <li>Sign in with your assigned app account. Change a temporary password when prompted.</li>
          <li>At Protect your account, enter your current password to create a recovery code. Save it privately, select <strong>I have saved my recovery code in a secure place.</strong>, then continue. The code is shown once and works once.</li>
          <li>Open Status Dashboard to see saved records, attention counts, source readiness, and unresolved blockers.</li>
        </ol>
        <p>The current source candidate is 1.0.2 · build 2026.10.16.1 · stable-local-desktop. The footer identifies the version actually running. After an approved update, refresh the browser and check it before reporting a problem. Full production qualification remains pending.</p>
        <p>Normal daily use needs the app and OneDrive only. ChatGPT, Codex, and development tools do not need to run. OneDrive does not replace an approved backup of the app’s local patient data.</p>
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
          <div><dt>Due Soon</dt><dd>The next update deadline is today or within 10 business days (Monday–Friday, no holiday exclusions). The deadline uses the latest plan’s last updated date plus its LOC interval: PHP 30 calendar days; IOP/Outpatient 60 calendar days.</dd></div>
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
        <p>CSV exports include filtered results, including off-screen rows, but omit names and narrative content. Patient identifiers and dates can still be sensitive. Verify your selection before sharing through an approved channel.</p>
      </section>

      <section className='panel' id='help-import'>
        <h2>Import records</h2>
        <h3>Manual upload</h3>
        <p>Choose approved binder files and provide an MRN correction only when needed. A batch can contain up to 40 files, with a maximum of 50 MiB per file and 250 MiB total. Review processing warnings and open the saved plan afterward. Secure storage does not mean a file was parsed or found compliant. If a format is stored without readable evidence, obtain a supported readable source before reviewing its clinical content.</p>
        <h3>Alleva patient and treatment-plan pulls</h3>
        <p>Live Alleva imports are gated off by default. They require R3/Alleva approval and validated tenant configuration and mapping. When approved and enabled, authorized administrators can use Pull patient roster in Patient Roster and Pull full treatment plans in Treatment Plans Roster. Office managers should ask their administrator when these controls are unavailable. Watch each job through completion; a connection test alone does not prove every patient or plan page was retrieved.</p>
        <p>On Status Dashboard, administrators can use Update patients and treatment plans to refresh the patient roster first, then pull and evaluate treatment plans. An incomplete patient pull stops the sequence before treatment plans. You can navigate and use saved records while the update runs; returning to the dashboard reconnects to saved job status. Cancel local update requests cancellation of local work, not a reset of Alleva.</p>
        <p>Progress percentages describe the current named phase. While the total is unknown, a moving indicator and received-record counts are shown. The still-running status message is informational. After an app or laptop restart, saved credentials and completed job history remain available; interrupted jobs are marked interrupted and can be retried after reviewing results.</p>
        <p>API Testing Harness provides bounded diagnostics and redacted previews. It does not replace checking imported records in the rosters. Review warnings and failed-record counts before treating a pull as complete.</p>
      </section>

      <section className='panel' id='help-access'>
        <h2>Accounts and access</h2>
        <p>Open Account to change your password or generate a replacement recovery code. Keep the code privately; it is shown once and works once. If locked out, use Forgot password with your username and saved code, or ask an authorized administrator for a reset. Administrators manage staff accounts in Users; navigation and actions vary by role.</p>
        <p>Authorized administrators use Settings for organization, facility timezone, and the API connection. Clinical rule values are shown for reference only. Forensic Logs is an administrator view of audited actions. Detailed diagnostics and audit records help support investigate activity; they are not a substitute for reviewing source evidence.</p>
      </section>

      <section className='panel' id='help-backup'>
        <h2>OneDrive ZIP backup and restore — configured source laptop</h2>
        <p>This laptop uses a separate portable ZIP workflow, not the encrypted .izcnabackup restore tool. ZIPs are not password protected: they include the database, local settings and encryption keys, uploads, logs and exports. Treat the entire ZIP as sensitive clinical data and credentials. Keep its OneDrive folder private under R3 access controls; do not email or share it publicly.</p>
        <h3>Create and check a backup</h3>
        <ol>
          <li>Save your work and wait for uploads and API jobs to finish. Double-click <strong>(8) Back Up IZ Data to OneDrive</strong>. The app briefly stops and restarts if it was running. Do not use Start during backup.</li>
          <li>Wait for the verified-success message. The archive is named <code>IZ-local-data-YYYYMMDD-HHMMSS-microsecondsZ.zip</code>; its timestamp is UTC. Open your organization OneDrive folder, then <strong>IZ Clinical Notes Analyzer Backups</strong>.</li>
          <li>Confirm a new ZIP exists and OneDrive reports that synchronization is complete. A local ZIP or successful task alone does not prove cloud upload. Check the file through OneDrive on the web before relying on it for computer-loss protection.</li>
          <li>The task <strong>IZ Local Data ZIP Backup</strong> runs every three days at 6 PM while the configuring Windows user is signed in. Missed runs are attempted when available. A failed run leaves older ZIPs intact; retry manually when idle. Check <code>%LOCALAPPDATA%\IZ Backup Status\last-result.json</code> for the most recent success/failure. No older backups are automatically deleted.</li>
        </ol>
        <p>The ZIP covers the active profile's settings, databases, uploads and other local files. Existing backup folders, diagnostics bundles and transient SQLite journals are excluded; databases are copied using consistent SQLite snapshots. App binaries, Python, project code and OneDrive itself are not inside this data backup. The script checks file hashes, SQLite integrity, the app schema and encrypted payloads in an isolated extraction before publishing the archive.</p>
        <h3>Restore on this laptop or a replacement computer</h3>
        <ol>
          <li>Download a complete ZIP from OneDrive. Keep the original archive unchanged. Use R3 support to prepare the same app version/build first; newer versions require a separately validated upgrade. This source workflow requires the matching project, built frontend, and its working Python runtime.</li>
          <li>On a new Windows account, start the prepared app once, then stop it. On an existing account, save all work and let uploads and imports finish. Restore replaces the entire profile as of the backup date, including accounts and passwords; it does not merge records.</li>
          <li>Double-click <strong>(9) Restore IZ Data from ZIP</strong>, select the downloaded ZIP, and type <code>RESTORE</code>. If the shortcut is absent, support opens PowerShell in the matching project folder and runs <code>powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore-onedrive-zip.ps1</code>.</li>
          <li>The script stops the app, validates and stages the complete archive, and preserves the current data in <code>%LOCALAPPDATA%\IZ Clinical Notes Analyzer-before-restore-TIMESTAMP</code> before activating the restored profile. It refuses a corrupted archive. Do not extract individual files over live data or use the .izcnabackup Restore command for these ZIPs.</li>
          <li>Use Start and sign in with the password valid at the backup date. Confirm expected records, settings, latest dates, and opening an uploaded document. Recovery codes also reflect the backup date. Keep the preserved profile until R3 confirms restoration. If checks fail, stop the app and have support preserve the failed profile and rename the before-restore folder back to <code>IZ Clinical Notes Analyzer</code>; never merge the two folders.</li>
          <li>On a replacement computer, recreate desktop shortcuts and register the backup task for its Windows account. Desktop shortcuts and Task Scheduler registration are not restored by the data ZIP.</li>
        </ol>
        <p>Synthetic restore tests verify portability without Windows-account encryption. A physical replacement-device rehearsal and OneDrive cloud-upload verification remain separate checks. If custom database or profile paths are configured, these scripts refuse backup and support must migrate that configuration first.</p>
      </section>

      <section className='panel' id='help-problems'>
        <h2>Troubleshooting and support</h2>
        <dl>
          <div><dt>The page will not open</dt><dd>Use the Start desktop shortcut once, wait for startup, then try <code>http://localhost:8000</code>. Closing the browser does not stop the background app. If startup reports an error, record its non-sensitive summary and contact R3 support. Do not reinstall or delete app files to troubleshoot.</dd></div>
          <div><dt>I forgot my password</dt><dd>Select Forgot password on the sign-in screen and use your username and saved recovery code. After resetting, sign in with the new password and save a replacement code. If the code is missing or already used, ask an authorized administrator for a reset.</dd></div>
          <div><dt>My session expired or I cannot open a screen</dt><dd>Sign in again after a session-expired message. A permission-denied message may mean your account role does not allow the action; ask an administrator. Do not share an administrator account.</dd></div>
          <div><dt>A roster looks empty or old</dt><dd>Clear filters, check the Source selector, refresh the roster, and inspect the last pull job and warnings.</dd></div>
          <div><dt>A plan status looks wrong</dt><dd>Open the exact version, compare source and computed dates, then inspect the checklist criterion and LOC history.</dd></div>
          <div><dt>An API pull fails</dt><dd>Record the job time, phase, and non-sensitive error summary. Do not repeatedly start imports while a job is running.</dd></div>
          <div><dt>The app seems slow</dt><dd>Wait for an active upload or pull to finish before starting another. Keep the laptop plugged in, check OneDrive for a large sync in progress, and close other applications. If the problem continues, record the screen, approximate record count, time, and app version for support.</dd></div>
          <div><dt>The version looks old after an update</dt><dd>Refresh the browser with Ctrl+F5 and check the footer. If it still shows the older version, send both the displayed version and build to support. Do not launch a second release folder.</dd></div>
        </dl>
        <p>For the illustrated offline instructions, use the desktop User Guide shortcut. For an authorized support session, use <strong>(3) Collect IZ Diagnostics</strong> and <strong>(4) Quick Assist - R3 Support</strong> as directed by R3. Treat the diagnostics bundle as sensitive and review it before transferring through an approved channel.</p>
        <p>Before restarting, wait for active jobs to finish and save your work. Sign out, use <strong>(2) Stop IZ Clinical Notes Analyzer</strong>, then start it again with shortcut (1). Ask support to handle backup or restore; do not move the local data folder into OneDrive. A backup must be verified and recoverable before replacing a laptop or Windows account.</p>
        <p>For support, send the app version, approximate time, screen name, and a non-PHI error message through the approved R3 channel. Keep patient content, passwords, recovery codes, raw logs, and API credentials out of ordinary chat or email. Sign out and lock Windows when finished.</p>
      </section>
    </div>
  )
}
