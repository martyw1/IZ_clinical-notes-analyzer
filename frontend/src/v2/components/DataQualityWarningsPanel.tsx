type DataQualityWarningsPanelProps = {
  readonly warnings: readonly string[]
}

export function DataQualityWarningsPanel({ warnings }: DataQualityWarningsPanelProps) {
  return (
    <section className='panel'>
      <h2>Data Quality Warnings</h2>
      {warnings.length ? (
        <ul className='artifact-list'>
          {warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      ) : (
        <p className='muted'>No data-quality warnings were returned for this treatment plan.</p>
      )}
    </section>
  )
}
