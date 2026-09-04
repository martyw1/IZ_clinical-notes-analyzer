export function HelpPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Help</p>
      <h2>Version 2.0 Beta workflow</h2>
      <p>Start with either roster to find authorized records by MRN, patient name, plan ID, or original plan reference. Names and search text stay out of CSV exports and forensic logs.</p>
      <ul>
        <li>Both rosters start with All sources. Use the Source filter to show only Manual or Alleva records.</li>
        <li>MRNs and external plan IDs can repeat across sources or facilities. Use the displayed source, patient record number, and saved version ID to select the exact record.</li>
        <li>Rosters show the latest saved version for each exact patient record and plan. The detail page’s Saved treatment-plan version selector opens history explicitly; a new import never silently replaces your selection.</li>
        <li>Export treatment plans and statuses includes all filtered results, including rows below the viewport. An empty filter result produces a header-only CSV.</li>
        <li>Manual names, original references, and service dates are optional; missing metadata is shown as Not supplied.</li>
        <li>Return, approve, comment, or override checklist criteria with required reason.</li>
        <li>Use API Testing Harness jobs for large pulls so the browser stays responsive.</li>
      </ul>
    </section>
  )
}
