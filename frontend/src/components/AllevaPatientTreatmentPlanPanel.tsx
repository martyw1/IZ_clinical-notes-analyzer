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
  readonly onLoadActivePatients: () => void
  readonly isBusy: boolean
}

export function AllevaPatientTreatmentPlanPanel({ pullState, patientId, onPatientIdChange, onLoadPatient, onLoadActivePatients, isBusy }: Props) {
  const rows = pullState.result?.rows || []
  return (
    <section className='panel-subsection' aria-label='Alleva synced patient treatment-plan aggregate'>
      <div className='panel-heading'>
        <div>
          <h3>Alleva synced treatment-plan record</h3>
          <p>Patient-centered aggregate from the reviewed Alleva REST contract.</p>
        </div>
      </div>
      <form
        className='form-grid'
        onSubmit={(event) => {
          event.preventDefault()
          onLoadPatient()
        }}
      >
        <label>
          Alleva patient ID
          <input value={patientId} onChange={(event) => onPatientIdChange(event.target.value)} />
        </label>
        <button type='submit' disabled={isBusy || !patientId.trim()}>
          Load synced patient record
        </button>
        <button type='button' className='ghost-button' onClick={onLoadActivePatients} disabled={isBusy}>
          Load active patient-centered records
        </button>
      </form>
      <div className='compact-status-frame' role='status' aria-label='Alleva patient treatment-plan pull status'>
        <strong>{pullState.status}</strong>
        <pre>{pullState.message}</pre>
      </div>
      {pullState.result ? (
        <dl className='finding-card finding-card--compact'>
          <AllevaField label='report' value={pullState.result.report} />
          <AllevaField label='source_operation' value={pullState.result.source_operation} />
          <AllevaField label='client_query_parameter' value={pullState.result.client_query_parameter} />
          <AllevaField label='lowercase_clientId_used' value={pullState.result.lowercase_clientId_used} />
          <AllevaField label='returned_count' value={pullState.result.returned_count ?? rows.length} />
          <AllevaField label='total_records_seen' value={pullState.result.total_records_seen} />
          <AllevaField label='report_path' value={pullState.result.report_path} />
        </dl>
      ) : null}
      {rows.length ? (
        <div className='finding-list'>
          {rows.map((aggregate) => (
            <AllevaPatientTreatmentPlanAggregateCard aggregate={aggregate} key={aggregate.patient_id} />
          ))}
        </div>
      ) : pullState.status === 'ready' ? (
        <p className='empty-state'>No patient-centered aggregate rows returned.</p>
      ) : null}
    </section>
  )
}
