export function HelpPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Help</p>
      <h2>Version 2.0 Beta workflow</h2>
      <p>Use Treatment Plans as the primary workbench. Patient names are excluded by default, and clinical narrative text does not enter forensic logs.</p>
      <ul>
        <li>Review the queue by status strip risk order.</li>
        <li>Select a treatment plan from an MRN row to inspect the full treatment-plan detail graph.</li>
        <li>Return, approve, comment, or override checklist criteria with required reason.</li>
        <li>Use API Testing Harness jobs for large pulls so the browser stays responsive.</li>
      </ul>
    </section>
  )
}
