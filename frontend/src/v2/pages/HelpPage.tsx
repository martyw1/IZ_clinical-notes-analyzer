export function HelpPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Help</p>
      <h2>Version 2.0 Beta workflow</h2>
      <p>Start with Patient Roster to find every patient by MRN and full name. Patient names and clinical narrative text never enter forensic logs.</p>
      <ul>
        <li>Select an MRN to open the complete Patient Record Detail.</li>
        <li>Select any treatment plan from a patient row to open its complete Treatment Plan Detail.</li>
        <li>Use Treatment Plans Roster to browse every linked or unlinked plan in the source system.</li>
        <li>Return, approve, comment, or override checklist criteria with required reason.</li>
        <li>Use API Testing Harness jobs for large pulls so the browser stays responsive.</li>
      </ul>
    </section>
  )
}
