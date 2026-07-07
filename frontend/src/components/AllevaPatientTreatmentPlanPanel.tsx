import {
  AllevaField,
  AllevaPatientTreatmentPlanAggregateCard,
} from './AllevaPatientTreatmentPlanCards'
import type { AllevaTreatmentPlanAggregate } from '../types/allevaTreatmentPlan'

export type AllevaPatientCenteredTreatmentPlanReport =
  | 'patient_centered_treatment_plans'
  | 'active_patient_centered_treatment_plans'
  | 'single_patient_treatment_plans'

export type AllevaPatientCenteredTreatmentPlanHarnessResult = {
  readonly status: string
  readonly message: string
  readonly report: AllevaPatientCenteredTreatmentPlanReport
  readonly source_operation?: string
  readonly returned_count?: number
  readonly total_records_seen?: number
  readonly patient_selection?: 'all' | 'active' | 'single'
  readonly client_query_parameter?: 'ClientId' | string
  readonly lowercase_clientId_used?: boolean
  readonly rows?: readonly AllevaTreatmentPlanAggregate[]
  readonly report_path?: string
}

export type AllevaPatientPlanPullState = {
  readonly status: 'idle' | 'loading' | 'ready' | 'error'
  readonly message: string
  readonly result: AllevaPatientCenteredTreatmentPlanHarnessResult | null
  readonly selectedPatientId: string
}

type Props = {
  readonly pullState: AllevaPatientPlanPullState
  readonly patientId: string
  readonly onPatientIdChange: (patientId: string) => void
  readonly onLoadPatient: () => void
  readonly onLoadAllPatients: () => void
  readonly onLoadActivePatients: () => void
  readonly isBusy: boolean
}

export function AllevaPatientTreatmentPlanPanel({ pullState, patientId, onPatientIdChange, onLoadPatient, onLoadAllPatients, onLoadActivePatients, isBusy }: Props) {
  const rows = pullState.result?.rows || []
  return (
    <section className='panel-subsection alleva-lookup-panel' aria-label='Alleva synced patient treatment-plan aggregate'>
      <div className='panel-heading'>
        <div>
          <h3>Alleva patient-centered treatment plans</h3>
          <p>Uses Patient ID (/clients.id / LeadId) with case-sensitive ClientId treatment-plan queries.</p>
        </div>
        <div className='compact-status-frame compact-status-frame--lookup' role='status' aria-label='Alleva patient treatment-plan pull status'>
          <strong>{pullState.status}</strong>
          <pre>{pullState.message}</pre>
        </div>
      </div>
      <form
        className='form-grid alleva-lookup-form'
        onSubmit={(event) => {
          event.preventDefault()
          onLoadPatient()
        }}
      >
        <label>
          Patient ID (/clients.id / LeadId)
          <input value={patientId} onChange={(event) => onPatientIdChange(event.target.value)} />
        </label>
        <button type='submit' disabled={isBusy || !patientId.trim()}>
          Load one patient
        </button>
        <button type='button' className='ghost-button' onClick={onLoadAllPatients} disabled={isBusy}>
          Load all patient-centered records
        </button>
        <button type='button' className='ghost-button' onClick={onLoadActivePatients} disabled={isBusy}>
          Load only active patient-centered records
        </button>
      </form>
      {pullState.result ? (
        <dl className='finding-card finding-card--compact alleva-lookup-summary'>
          <AllevaField label='Report run' value={pullState.result.report} />
          <AllevaField label='Source operation' value={pullState.result.source_operation} />
          <AllevaField label='Patient-plan query parameter' value={pullState.result.client_query_parameter} />
          <AllevaField label='Lowercase clientId used' value={pullState.result.lowercase_clientId_used} />
          <AllevaField label='Patient rows returned' value={pullState.result.returned_count ?? rows.length} />
          <AllevaField label='Total records fetched' value={pullState.result.total_records_seen} />
          <AllevaField label='Saved report path' value={pullState.result.report_path} />
        </dl>
      ) : null}
      {rows.length ? (
        <section className='alleva-lookup-results' aria-label='Alleva lookup result rows'>
          <div className='finding-list'>
            {rows.map((aggregate) => (
              <AllevaPatientTreatmentPlanAggregateCard aggregate={aggregate} key={aggregate.patient_id} />
            ))}
          </div>
        </section>
      ) : pullState.status === 'ready' ? (
        <p className='empty-state'>No patient-centered aggregate rows returned.</p>
      ) : null}
    </section>
  )
}
