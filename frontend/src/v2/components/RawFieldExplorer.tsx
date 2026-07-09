import { useMemo, useState } from 'react'
import type { TreatmentPlanAggregate } from '../types/treatmentPlan'

type RawFieldExplorerProps = {
  readonly plan: TreatmentPlanAggregate
}

export function RawFieldExplorer({ plan }: RawFieldExplorerProps) {
  const [query, setQuery] = useState('')
  const fields = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    const filtered = normalized
      ? plan.observedFields.filter((field) => field.fieldPath.toLowerCase().includes(normalized))
      : plan.observedFields
    return filtered.slice(0, 100)
  }, [plan.observedFields, query])

  return (
    <section className='panel table-panel'>
      <div className='section-heading'>
        <div>
          <p className='eyebrow'>Bounded diagnostics</p>
          <h2>Raw Field Explorer</h2>
        </div>
        <label>
          Search fields
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search field path' />
        </label>
      </div>
      <table className='raw-field-table'>
        <thead>
          <tr>
            <th>Field path</th>
            <th>Type</th>
            <th>State</th>
            <th>Safe preview</th>
            <th>Checklist</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field.fieldPath}>
              <td data-label='Field path'>{field.fieldPath}</td>
              <td data-label='Type'>{field.valueType}</td>
              <td data-label='State'>{field.state}</td>
              <td data-label='Safe preview'>{field.sampleRedactedValue}</td>
              <td data-label='Checklist'>{field.usedByChecklist ? 'Used' : 'Unused'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className='muted'>Default display is capped at 100 paths. Long values are truncated to safe previews.</p>
    </section>
  )
}
