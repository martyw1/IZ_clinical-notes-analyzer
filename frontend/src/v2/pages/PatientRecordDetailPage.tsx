import { useEffect, useMemo, useState } from 'react'
import { getPatientRecordDetail } from '../api/client'
import { ApiRequestError } from '../api/json'
import { composePatientRecordSections } from '../api/patientRecordMapper'
import type { PatientRecordDetail, PatientSelection, TreatmentPlanSelection } from '../api/types'
import { formatDateTime24Hour } from '../components/treatmentPlanFormatting'

type PatientRecordDetailPageProps = {
  readonly token: string
  readonly selection: PatientSelection | null
  readonly onNavigate: (view: string) => void
  readonly onSelectTreatmentPlan: (selection: TreatmentPlanSelection) => void
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to load the selected patient record.'
}

export function PatientRecordDetailPage({
  token,
  selection,
  onNavigate,
  onSelectTreatmentPlan,
}: PatientRecordDetailPageProps) {
  const [detail, setDetail] = useState<PatientRecordDetail | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const sections = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return composePatientRecordSections(detail?.patientRecord ?? {})
      .map((section) => ({
        ...section,
        fields: section.fields.filter((field) => (
          !normalized
          || field.label.toLowerCase().includes(normalized)
          || field.path.toLowerCase().includes(normalized)
          || field.value.toLowerCase().includes(normalized)
        )),
      }))
      .filter((section) => section.fields.length > 0)
  }, [detail?.patientRecord, query])

  useEffect(() => {
    if (!selection) {
      setDetail(null)
      setError('')
      return
    }
    let cancelled = false
    setDetail(null)
    setError('')
    void getPatientRecordDetail(token, selection.patientKey, selection.sourceMode)
      .then((record) => {
        if (!cancelled) setDetail(record)
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(messageForError(loadError))
      })
    return () => { cancelled = true }
  }, [selection, token])

  if (!selection) {
    return (
      <section className='panel empty-detail-panel'>
        <p className='eyebrow'>Patient Record Detail</p>
        <h2>Select a patient record</h2>
        <p>Choose an MRN from Patient Roster or Treatment Plans Roster to view the complete patient record.</p>
        <div className='button-row'>
          <button type='button' onClick={() => onNavigate('Patient Roster')}>Open Patient Roster</button>
          <button type='button' className='secondary-button' onClick={() => onNavigate('Treatment Plans Roster')}>Open Treatment Plans Roster</button>
        </div>
      </section>
    )
  }
  if (error) return <section className='panel error-banner' role='alert'>{error}</section>
  if (!detail) return <section className='panel muted'>Loading patient record...</section>

  return (
    <div className='detail-grid patient-record-document'>
      <section className='panel detail-identity-panel'>
        <p className='eyebrow'>Patient Record Detail</p>
        <h2>{detail.fullName || 'Name unavailable'}</h2>
        <p className='patient-primary-id'>MRN {detail.mrn}</p>
        <dl className='plan-fact-grid'>
          <div><dt>Level of care</dt><dd>{detail.currentLevelOfCare}</dd></div>
          <div><dt>Lifecycle</dt><dd>{detail.lifecycleState}</dd></div>
          <div><dt>Source</dt><dd>{detail.sourceMode}</dd></div>
          <div><dt>Source last updated</dt><dd>{formatDateTime24Hour(detail.sourceLastUpdated)}</dd></div>
          <div><dt>First synchronized</dt><dd>{formatDateTime24Hour(detail.firstSeenAt)}</dd></div>
          <div><dt>Last synchronized</dt><dd>{formatDateTime24Hour(detail.lastSeenAt)}</dd></div>
        </dl>
      </section>

      <section className='panel patient-plan-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Linked records</p>
            <h2>Treatment plans</h2>
          </div>
          <span>{detail.treatmentPlans.length} available</span>
        </div>
        <select
          aria-label={`Treatment plans for MRN ${detail.mrn}`}
          defaultValue=''
          disabled={detail.treatmentPlans.length === 0}
          onChange={(event) => {
            const plan = detail.treatmentPlans.find((candidate) => candidate.treatmentPlanId === event.currentTarget.value)
            if (!plan) return
            onSelectTreatmentPlan({
              mrn: detail.mrn,
              patientKey: selection.patientKey,
              treatmentPlanId: plan.treatmentPlanId,
              sourceMode: detail.sourceMode,
            })
          }}
        >
          <option value=''>{detail.treatmentPlans.length ? 'Select a treatment plan' : 'No treatment plans'}</option>
          {detail.treatmentPlans.map((plan) => (
            <option key={plan.treatmentPlanId} value={plan.treatmentPlanId}>
              {`(#${plan.treatmentPlanId}) ${formatDateTime24Hour(plan.lastUpdated)}`}
            </option>
          ))}
        </select>
      </section>

      <section className='panel patient-record-search'>
        <label>
          Search patient information
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder='Field name or value' />
        </label>
      </section>

      {sections.map((section) => (
        <section className='panel patient-record-section' key={section.title}>
          <h2>{section.title}</h2>
          <dl className='patient-record-field-grid'>
            {section.fields.map((field) => (
              <div key={field.path}>
                <dt>{field.label}</dt>
                <dd>{field.value}</dd>
                <span className='field-path'>{field.path}</span>
              </div>
            ))}
          </dl>
        </section>
      ))}
      {sections.length === 0 && (
        <section className='panel muted'>No patient fields match the current search.</section>
      )}
    </div>
  )
}
