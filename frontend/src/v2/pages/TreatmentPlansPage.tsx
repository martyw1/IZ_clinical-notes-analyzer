import { syntheticTreatmentPlan } from '../data'
import { TreatmentPlanDetailViewer } from '../components/TreatmentPlanDetailViewer'
import { StatusBadge } from '../components/StatusBadge'
import { statusOrder } from '../types/treatmentPlan'

export function TreatmentPlansPage() {
  return (
    <div className='treatment-workbench'>
      <section className='sticky-toolbar'>
        <div>
          <p className='eyebrow'>Treatment Plans Workbench</p>
          <h2>Focused V2 treatment-plan review queue</h2>
        </div>
        <label>
          Evaluation date
          <input type='date' defaultValue='2026-07-08' />
        </label>
        <label>
          Search
          <input placeholder='Patient ID or status' />
        </label>
        <button type='button'>Refresh</button>
        <button type='button' className='secondary-button'>Manual upload</button>
      </section>
      <section className='status-strip' aria-label='Treatment Plans status strip'>
        {statusOrder.map((status) => (
          <button key={status} type='button' className='status-segment'>
            <StatusBadge status={status} />
            <span>{status === syntheticTreatmentPlan.status ? '1' : status === 'Missing Data' ? '3' : '0'}</span>
          </button>
        ))}
      </section>
      <section className='queue-and-detail'>
        <article className='panel queue-panel'>
          <h2>Queue</h2>
          <table>
            <thead>
              <tr>
                <th>Patient</th>
                <th>LOC</th>
                <th>Admission</th>
                <th>Next due</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{syntheticTreatmentPlan.patientDisplayLabel}</td>
                <td>{syntheticTreatmentPlan.currentLevelOfCare}</td>
                <td>{syntheticTreatmentPlan.admissionDate}</td>
                <td>{syntheticTreatmentPlan.dueDate}</td>
                <td><StatusBadge status={syntheticTreatmentPlan.status} /></td>
                <td>{syntheticTreatmentPlan.sourceMode}</td>
              </tr>
            </tbody>
          </table>
        </article>
        <TreatmentPlanDetailViewer plan={syntheticTreatmentPlan} />
      </section>
    </div>
  )
}
