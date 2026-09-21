export function HelpPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Help</p>
      <h2>Production 1.0 workflow</h2>
      <p>App 1.0.0 · build 2026.09.21.1 · stable-local-desktop. Production 1.0 uses the local-client runtime. Full production qualification remains pending. Checklist content remains version 1.2.0.</p>
      <h3>Passwords and recovery</h3>
      <p>Open Account to change your password or create a replacement recovery code. Save the code privately; it is shown once and works once. Use Forgot password on the sign-in screen with your username and saved code, then sign in and save a replacement code. Authorized administrators can reset staff passwords from Users. Initial and administrator-issued temporary passwords must be replaced before using the workspace.</p>
      <h3>Find and review the exact saved plan</h3>
      <p>Start with either roster to find authorized records by MRN, patient name, plan ID, or original plan reference. Names and search text stay out of CSV exports and forensic logs.</p>
      <ul>
        <li>Both rosters start with All sources. Use the Source filter to show only Manual or Alleva records.</li>
        <li>MRNs and external plan IDs can repeat across sources or facilities. Use the displayed source, patient record number, and saved version ID to select the exact record.</li>
        <li>Rosters show the latest saved version for each exact patient record and plan. The detail page’s Saved treatment-plan version selector opens history explicitly; a new import never silently replaces your selection.</li>
        <li>Export treatment plans and statuses includes all filtered results, including rows below the viewport. An empty filter result produces a header-only CSV.</li>
        <li>Manual names, original references, and service dates are optional. Missing names show Name unavailable; missing original references and service dates show Not supplied.</li>
        <li>Return, approve, comment, or override checklist criteria with required reason.</li>
        <li>Use API Testing Harness jobs for large diagnostic pulls so the browser stays responsive. After the live read-only approval gate is satisfied, use Pull full treatment plans in Treatment Plans Roster for plan imports. Pull patient roster in Patient Roster refreshes patient records and does not require treatment plans.</li>
      </ul>
      <h3>Manual upload and unresolved evidence</h3>
      <p>Open Manual Upload, select approved binder files, and supply an MRN override only when needed. Confirm any correction against the source before retrying. Review processing warnings and then open the exact imported plan; secure storage alone does not mean a file was parsed or found compliant.</p>
      <p>Missing Data, Needs Review, Conflicting Evidence, and Unable to Evaluate remain unresolved outcomes. Check source evidence and dates before taking a manager action. The configurable 7-calendar-day LOC-change preset remains unvalidated until R3/Marleigh confirms the rule.</p>
      <h3>Connection, session, and support</h3>
      <p>Live Alleva sync is off by default and requires approved tenant access, endpoint mapping, and explicit read-only authorization in Settings. A successful connectivity test does not establish production approval. Optional LLM features are off by default and are not required for deterministic checklist or timeliness decisions.</p>
      <p>If your session expires, sign in again before continuing. Sign out and lock Windows when finished. For support, provide the version, time, and non-PHI error message through the approved R3 channel. Keep passwords, patient content, raw logs, and backups out of ordinary email or chat.</p>
    </section>
  )
}
