import type { SourceFilter } from '../types/identity'

export function SourceFilterControl({ value, onChange }: { readonly value: SourceFilter; readonly onChange: (value: SourceFilter) => void }) {
  return <label>Source filter
    <select value={value} onChange={(event) => {
      switch (event.currentTarget.value) {
        case 'all': onChange('all'); break
        case 'manual_upload': onChange('manual_upload'); break
        case 'alleva_rest_api': onChange('alleva_rest_api'); break
      }
    }}>
      <option value='all'>All sources</option>
      <option value='manual_upload'>Manual</option>
      <option value='alleva_rest_api'>Alleva</option>
    </select>
  </label>
}
