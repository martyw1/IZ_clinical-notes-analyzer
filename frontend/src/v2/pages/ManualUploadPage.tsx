export function ManualUploadPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Manual Upload</p>
      <h2>Point-in-time treatment-plan evidence</h2>
      <p>Manual uploads normalize into the same V2 aggregate and content graph used by API evidence.</p>
      <div className='source-card-grid'>
        <article className='source-card'><h3>Supported files</h3><p>PDF, CSV, TSV, XLSX, TXT, and MD.</p></article>
        <article className='source-card'><h3>Metadata correction</h3><p>Office managers can supply patient ID, LOC, signature dates, and missing source dates.</p></article>
        <article className='source-card'><h3>Fingerprinting</h3><p>Unchanged batches are skipped unless explicitly reprocessed.</p></article>
      </div>
    </section>
  )
}
