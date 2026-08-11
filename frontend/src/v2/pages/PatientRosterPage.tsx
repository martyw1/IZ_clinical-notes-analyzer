import { useEffect, useMemo, useState } from 'react'
import { getPatientRoster } from '../api/client'
import { getApiConfiguration } from '../api/settingsClient'
import { ApiRequestError } from '../api/json'
import type { ApiConfiguration, PatientRosterData, PatientSelection, TreatmentPlanSelection, UserProfile } from '../api/types'
import { PatientRosterPullCard } from '../components/PatientRosterPullCard'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'

type PatientRosterPageProps = {
  readonly token: string
  readonly user: UserProfile
  readonly onNavigate: (view: string) => void
  readonly onSelectPatient: (selection: PatientSelection) => void
  readonly onSelectTreatmentPlan: (selection: TreatmentPlanSelection) => void
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the patient roster.'
}

export function PatientRosterPage({ token, user, onNavigate, onSelectPatient, onSelectTreatmentPlan }: PatientRosterPageProps) {
  const [roster, setRoster] = useState<PatientRosterData | null>(null)
  const [apiConfig, setApiConfig] = useState<ApiConfiguration | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [refreshNumber, setRefreshNumber] = useState(0)
  const visibleItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return (roster?.items ?? []).filter((item) => (
      !normalizedQuery
      || item.mrn.toLowerCase().includes(normalizedQuery)
      || item.fullName.toLowerCase().includes(normalizedQuery)
      || item.treatmentPlans.some((plan) => plan.treatmentPlanId.toLowerCase().includes(normalizedQuery))
    ))
  }, [query, roster?.items])

  useEffect(() => {
    let cancelled = false
    void getPatientRoster(token).then((result) => {
      if (!cancelled) setRoster(result)
    }).catch((loadError: unknown) => {
      if (!cancelled) setError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [refreshNumber, token])

  useEffect(() => {
    if (user.role !== 'admin') return
    let cancelled = false
    void getApiConfiguration(token).then((config) => {
      if (!cancelled) setApiConfig(config)
    }).catch((loadError: unknown) => {
      if (!cancelled) setError(messageForError(loadError))
    })
    return () => { cancelled = true }
  }, [token, user.role])

  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (!roster) return <section className='panel muted'>Loading patient roster...</section>

  return (
    <div className='treatment-workbench'>
      {user.role === 'admin' && (
        <PatientRosterPullCard
          config={apiConfig}
          token={token}
          onNavigate={onNavigate}
          onCompleted={() => setRefreshNumber((current) => current + 1)}
        />
      )}
      <section className='panel table-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Patient Roster</p>
            <h2>Patient roster</h2>
            <p className='muted'>MRN is the primary patient identifier. Open any patient record or select any available treatment plan.</p>
          </div>
          <button type='button' onClick={() => setRefreshNumber((current) => current + 1)}>Refresh roster</button>
        </div>
        <label>
          Search MRN, patient name, or treatment plan ID
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='MRN, patient name, or treatment plan ID' />
        </label>
        <table>
          <thead><tr role='row'><th id='patient-roster-mrn' role='columnheader'>MRN</th><th id='patient-roster-plans' role='columnheader'>Treatment Plans</th><th id='patient-roster-lifecycle' role='columnheader'>Lifecycle</th><th id='patient-roster-loc' role='columnheader'>LOC</th><th id='patient-roster-source' role='columnheader'>Source</th><th id='patient-roster-last-seen' role='columnheader'>Last seen</th></tr></thead>
          <tbody>
            {visibleItems.map((item) => (
              <tr key={`${item.mrn}:${item.sourceMode}`} role='row'>
                <td role='cell' data-label='MRN' headers='patient-roster-mrn'>
                  <button
                    type='button'
                    className='link-button patient-record-link'
                    aria-label={`Open patient record for ${item.fullName || 'Name unavailable'}, MRN ${item.mrn}`}
                    onClick={() => onSelectPatient({ mrn: item.mrn, patientKey: item.mrn, sourceMode: item.sourceMode })}
                  >
                    {item.mrn}
                  </button>
                  <span className='patient-name-secondary'>{item.fullName || 'Name unavailable'}</span>
                </td>
                <td role='cell' data-label='Treatment Plans' headers='patient-roster-plans'>
                  <select
                    aria-label={`Treatment plans for MRN ${item.mrn}`}
                    defaultValue=''
                    disabled={item.treatmentPlans.length === 0}
                    onChange={(event) => {
                      const plan = item.treatmentPlans.find((candidate) => candidate.treatmentPlanId === event.currentTarget.value)
                      if (!plan) return
                      onSelectTreatmentPlan({
                        mrn: item.mrn,
                        patientKey: item.mrn,
                        treatmentPlanId: plan.treatmentPlanId,
                        sourceMode: item.sourceMode,
                      })
                    }}
                  >
                    <option value=''>{item.treatmentPlans.length ? 'Select a treatment plan' : 'No treatment plans'}</option>
                    {item.treatmentPlans.map((plan) => (
                      <option key={plan.treatmentPlanId} value={plan.treatmentPlanId}>
                        {`(#${plan.treatmentPlanId}) ${formatDateTime24Hour(plan.lastUpdated)}`}
                      </option>
                    ))}
                  </select>
                </td>
                <td role='cell' data-label='Lifecycle' headers='patient-roster-lifecycle'>{item.lifecycleState}</td>
                <td role='cell' data-label='LOC' headers='patient-roster-loc'>{item.currentLevelOfCare}</td>
                <td role='cell' data-label='Source' headers='patient-roster-source'>{item.sourceMode}</td>
                <td role='cell' data-label='Last seen' headers='patient-roster-last-seen'><time dateTime={item.lastSeenAt}>{formatDateTime24Hour(item.lastSeenAt)}</time></td>
              </tr>
            ))}
            {visibleItems.length === 0 && <tr role='row'><td role='cell' colSpan={6} className='muted'>No roster entries match the current search.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}
