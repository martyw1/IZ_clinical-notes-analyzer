type DataQualityWarningsProps = {
  warnings?: string[]
  idJoinWarnings?: string[]
  dischargeConflict?: boolean
  idJoinConfidence?: string | null
  identifiers?: {
    sourceId?: string | null
    leadId?: string | null
    clientId?: string | null
    uniqueId?: string | null
    mrn?: string | null
  }
}

function labelWarning(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function maskIdentifier(value?: string | null) {
  if (!value) return ''
  const trimmed = String(value).trim()
  if (trimmed.length <= 5) return trimmed
  return `${trimmed.slice(0, 2)}...${trimmed.slice(-3)}`
}

export function DataQualityWarnings({ warnings = [], idJoinWarnings = [], dischargeConflict = false, idJoinConfidence, identifiers }: DataQualityWarningsProps) {
  const combinedWarnings = Array.from(
    new Set([
      ...(dischargeConflict ? ['active_status_discharge_field_conflict'] : []),
      ...warnings,
      ...idJoinWarnings,
    ].filter(Boolean)),
  )
  const idRows: Array<[string, string | null | undefined]> = ([
    ['Source', identifiers?.sourceId],
    ['Lead', identifiers?.leadId],
    ['Client', identifiers?.clientId],
    ['Unique', identifiers?.uniqueId],
    ['MRN', identifiers?.mrn],
  ] satisfies Array<[string, string | null | undefined]>).filter(([, value]) => Boolean(value))

  if (!combinedWarnings.length && !idJoinConfidence && !idRows.length) return null

  return (
    <section className='data-quality-panel' aria-label='Alleva treatment-plan data quality'>
      <div className='data-quality-panel__heading'>
        <div>
          <h3>Alleva data quality</h3>
          <p>Active-patient and treatment-plan linkage checks for this record.</p>
        </div>
        {idJoinConfidence ? <span className='pill pill--neutral'>ID match: {idJoinConfidence}</span> : null}
      </div>
      {combinedWarnings.length ? (
        <ul className='data-quality-list'>
          {combinedWarnings.map((warning) => (
            <li key={warning}>{labelWarning(warning)}</li>
          ))}
        </ul>
      ) : (
        <p className='muted-text'>No active-patient or ID-linkage warnings are currently recorded.</p>
      )}
      {idRows.length ? (
        <dl className='identifier-grid'>
          {idRows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{maskIdentifier(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  )
}
