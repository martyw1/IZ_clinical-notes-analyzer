import { afterEach, describe, expect, it, vi } from 'vitest'
import { getPatientRoster, getTreatmentPlanRoster, getTreatmentPlans } from './client'
import { getCorrectionQueue } from './correctionsClient'
import { mapTreatmentPlanAggregate, mapTreatmentPlanList } from './treatmentPlanMapper'

const identity = { patient_record_id: 31, plan_version_id: 91, source_mode: 'manual_upload', treatment_plan_id: 'external-shared' }
const plan = { ...identity, patient_id: 'MRN-SHARED', full_name: 'Synthetic Manual', version_ordinal: 2, is_current: false, original_plan_reference: 'REF-ONLY', service_date: '2026-09-01', last_updated: '2026-09-03T01:00:00Z' }
function respond(value: unknown) { return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } }) }

describe('exact source-aware response boundaries', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('retains row version source and optional metadata when mapping a current list', () => {
    // Given an authorized response with distinct display/reference and database identity.
    const payload = { items: [plan] }
    // When the response is parsed.
    const result = mapTreatmentPlanList(payload)
    // Then no identity or authorized metadata is dropped.
    expect(result.items[0]).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'manual_upload', treatmentPlanId: 'external-shared', fullName: 'Synthetic Manual', versionOrdinal: 2, isCurrent: false, originalPlanReference: 'REF-ONLY', serviceDate: '2026-09-01' })
  })

  it.each([undefined, 0, -1, 1.5, '91', Number.POSITIVE_INFINITY])('rejects invalid required plan version %s instead of creating a fallback', (invalid) => {
    // Given a malformed immutable identity.
    const payload = { items: [{ ...plan, plan_version_id: invalid }] }
    // When/Then boundary parsing fails closed.
    expect(() => mapTreatmentPlanList(payload)).toThrow()
  })

  it('rejects a missing patient row when detail otherwise has a valid version', () => {
    // Given an envelope without an exact patient row.
    const payload = { plan_version_id: 91, source_mode: 'manual_upload', content_snapshot: { plan_id: 'external-shared' } }
    // When/Then detail parsing does not substitute MRN or zero.
    expect(() => mapTreatmentPlanAggregate(payload)).toThrow()
  })

  it('preserves manual metadata and keeps unassigned history separate', () => {
    // Given metadata and one historical action with no provable plan link.
    const payload = { ...identity, content_snapshot: { plan_id: 'external-shared', service_date: '2026-09-01', original_plan_reference: 'REF-ONLY' }, unassigned_manager_reviews: [{ criterion_id: 'c1', action: 'comment', comment: 'Unassigned synthetic history' }] }
    // When parsing the selected plan.
    const result = mapTreatmentPlanAggregate(payload)
    // Then original identity and separate non-actionable history survive.
    expect(result).toMatchObject({ patientRecordId: 31, planVersionId: 91, treatmentPlanId: 'external-shared', serviceDate: '2026-09-01', originalPlanReference: 'REF-ONLY', managerReviews: [], unassignedManagerReviews: [{ comment: 'Unassigned synthetic history' }] })
  })

  it('retains exact nested plan identities in a patient roster', async () => {
    // Given one patient and a nested immutable saved plan.
    vi.stubGlobal('fetch', vi.fn(async () => respond({ items: [{ ...identity, mrn: 'MRN-SHARED', treatment_plans: [plan] }] })))
    // When loading the roster.
    const result = await getPatientRoster('token')
    // Then both levels carry the exact row and the nested version/source.
    expect(result.items[0]).toMatchObject({ patientRecordId: 31, treatmentPlans: [{ patientRecordId: 31, planVersionId: 91, sourceMode: 'manual_upload', versionOrdinal: 2 }] })
  })

  it('retains exact identity on treatment roster and correction work items', async () => {
    // Given identical external identity that cannot replace numeric database identity.
    vi.stubGlobal('fetch', vi.fn(async () => respond({ items: [{ ...plan, work_item_id: 15, patient_key: 'MRN-SHARED', mrn: 'MRN-SHARED' }] })))
    // When both response boundaries parse the selected record.
    const [roster, corrections] = await Promise.all([getTreatmentPlanRoster('token'), getCorrectionQueue('token')])
    // Then both retain exact row/version/source/external ID.
    expect(roster.items[0]).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'manual_upload', treatmentPlanId: 'external-shared' })
    expect(corrections[0]).toMatchObject({ patientRecordId: 31, planVersionId: 91, sourceMode: 'manual_upload', treatmentPlanId: 'external-shared' })
  })

  it('does not invent a source when a list response has an unknown source mode', () => {
    // Given a response outside the frozen source union.
    const payload = { items: [{ ...plan, source_mode: 'manual_treatment_plan_file' }] }
    // When/Then parsing rejects the source-kind/plan-source mismatch.
    expect(() => mapTreatmentPlanList(payload)).toThrow()
  })
})
