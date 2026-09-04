import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { getPatientRecordDetail, getPatientRoster, getTreatmentPlanRoster } from './client'
import { readPlanIdentity } from './identity'
import { mapTreatmentPlanAggregate, mapTreatmentPlanList } from './treatmentPlanMapper'
import { sourceLabel } from '../types/identity'
import { TreatmentPlansRosterPage } from '../pages/TreatmentPlansRosterPage'
import type { UserProfile } from './types'

const wire = { patient_record_id: 31, plan_version_id: 91, source_mode: 'synthetic_fixture', treatment_plan_id: 'db-envelope-plan' }
const patient = { ...wire, patient_id: 'SYNTHETIC-ROW', mrn: 'SYNTHETIC-ROW', patient_key: 'SYNTHETIC-ROW', linked_to_mrn: true, treatment_plans: [wire] }
const manager: UserProfile = { id: 1, username: 'synthetic-manager', fullName: 'Synthetic Manager', role: 'office_manager', isActive: true, isLocked: false, mustResetPassword: false, authState: 'active', lockedUntil: '', facilityIds: [1] }
function respond(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }) }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

test.each([undefined, '', 'different-clinical-plan'])('retains authoritative envelope ID when snapshot ID is %s', (snapshotId) => {
  // Given: the selected database identity and independently supplied clinical snapshot content.
  const payload = { ...wire, source_mode: 'manual_upload', overall_status: 'Missing Data',
    content_snapshot: snapshotId === undefined ? {} : { plan_id: snapshotId } }
  const before = JSON.stringify(payload)
  // When: the API envelope is mapped for selection.
  const result = mapTreatmentPlanAggregate(payload)
  // Then: neither missing nor differing clinical content replaces or mutates the authoritative ID.
  expect(result.treatmentPlanId).toBe('db-envelope-plan')
  expect(result.status).toBe('Missing Data')
  expect(JSON.stringify(payload)).toBe(before)
})

test('preserves a valid stored synthetic plan in the current list', () => {
  // Given: a supported persisted source with exact numeric IDs.
  const payload = { items: [patient] }
  // When: the current list is mapped.
  const result = mapTreatmentPlanList(payload)
  // Then: source and exact identities survive without a Manual/Alleva relabel.
  expect(result.items[0]).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'synthetic_fixture', treatmentPlanId: 'db-envelope-plan' })
  expect(result.items).toHaveLength(1)
  for (const item of result.items) expect(sourceLabel(item.sourceMode)).toBe('Synthetic fixture')
})

test('preserves a valid stored synthetic detail and its status', () => {
  // Given: a supported stored synthetic detail envelope.
  const payload = { ...patient, overall_status: 'Unable to Evaluate', content_snapshot: { plan_id: 'clinical-other' } }
  // When: mapping the exact detail.
  const result = mapTreatmentPlanAggregate(payload)
  // Then: real source and envelope identity survive without changing clinical decisions.
  expect(result).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'synthetic_fixture', treatmentPlanId: 'db-envelope-plan', status: 'Unable to Evaluate' })
})

test('retains stored synthetic identities in both roster boundaries independently', async () => {
  // Given: supported synthetic patient and treatment-plan roster responses.
  vi.stubGlobal('fetch', vi.fn(async () => respond({ items: [patient] })))
  // When: both HTTP response boundaries are parsed.
  const patients = await getPatientRoster('token')
  const plans = await getTreatmentPlanRoster('token')
  // Then: every independent consumer keeps the row, source and nested version.
  expect(patients.items[0]).toMatchObject({ patientRecordId: 31, sourceMode: 'synthetic_fixture',
    treatmentPlans: [{ patientRecordId: 31, planVersionId: 91, sourceMode: 'synthetic_fixture', treatmentPlanId: 'db-envelope-plan' }] })
  expect(plans.items[0]).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'synthetic_fixture', treatmentPlanId: 'db-envelope-plan' })
})

test('reads a selected synthetic patient using its exact row and source query', async () => {
  // Given: an explicit stored synthetic selection, never an intake request.
  const selection = { ...readPlanIdentity({ ...wire, source_mode: 'manual_upload' }), sourceMode: 'synthetic_fixture' as const, mrn: patient.mrn, patientKey: patient.mrn }
  const fetchMock = vi.fn(async () => respond(patient))
  vi.stubGlobal('fetch', fetchMock)
  // When: reading the selected patient.
  const result = await getPatientRecordDetail('token', selection)
  // Then: the source is preserved and the exact selector is sent.
  expect(result.sourceMode).toBe('synthetic_fixture')
  expect(fetchMock).toHaveBeenCalledWith('/api/v2/patients/SYNTHETIC-ROW?patient_record_id=31&source_mode=synthetic_fixture', expect.anything())
})

test('All shows stored synthetic rows while controls remain All Manual and Alleva', async () => {
  // Given: an authorized synthetic row returned by the existing All-source roster.
  vi.stubGlobal('fetch', vi.fn(async () => respond({ items: [patient] })))
  // When: the shipped roster renders.
  render(<TreatmentPlansRosterPage token='token' user={manager} onNavigate={vi.fn()} onSelectPatient={vi.fn()} onSelectTreatmentPlan={vi.fn()} />)
  // Then: source labeling is accurate without adding an intake/filter mode.
  expect(await screen.findByText(/Synthetic fixture · record 31/)).toBeInTheDocument()
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['All sources', 'Manual', 'Alleva'])
  expect(screen.getByLabelText('Source filter')).toHaveValue('all')
})

test.each([undefined, 'not-a-supported-source', 'manual_treatment_plan_file'])('rejects unsupported or missing source %s', (sourceMode) => {
  // Given: a non-contract source despite valid numeric identity.
  const payload = { items: [{ ...patient, source_mode: sourceMode }] }
  // When/Then: the reader fails closed rather than creating a source label.
  expect(() => mapTreatmentPlanList(payload)).toThrow('unsupported record source')
})

test.each(['patient_record_id', 'plan_version_id'])('rejects a synthetic row with nonpositive %s', (field) => {
  // Given: a supported source but an invalid exact numeric identity.
  const payload = { items: [{ ...patient, [field]: 0 }] }
  // When/Then: stored-source compatibility never fabricates IDs.
  expect(() => mapTreatmentPlanList(payload)).toThrow()
})
