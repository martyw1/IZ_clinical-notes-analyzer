import { expect, test } from 'vitest'
import type { JsonRecord } from './json'
import { mapTreatmentPlanAggregate, mapTreatmentPlanList } from './treatmentPlanMapper'

test('maps a missing source mode to unavailable instead of synthetic fixture data', () => {
  const payload: JsonRecord = {}

  const aggregate = mapTreatmentPlanAggregate(payload)

  expect(aggregate.sourceMode).toBe('unavailable')
})

test('preserves every backend queue status without collapsing distinct status segments', () => {
  const payload: JsonRecord = {
    items: [],
    status_order: ['Missing Data', 'Conflicting Evidence', 'Unable to Evaluate', 'Needs Review', 'Overdue', 'Urgent', 'Due Soon', 'Current/Compliant', 'Incomplete'],
  }

  const queue = mapTreatmentPlanList(payload)

  expect(queue.statusOrder).toEqual(payload.status_order)
})

test('preserves selected-plan lineage and clinical review history for document composition', () => {
  const aggregate = mapTreatmentPlanAggregate({
    source_last_updated: '2026-02-04T17:30:00Z',
    treatment_plans: [
      { plan_id: 'plan-1', plan_date: '2026-01-03T09:00:00Z', last_modified: '2026-02-04T17:30:00Z' },
      { plan_id: 'plan-1', plan_date: '2026-01-03T09:00:00Z', last_modified: '2026-02-04T17:30:00Z' },
    ],
    treatment_reviews: [
      { id: 'review-1', createdDated: '2026-02-01T09:00:00Z', creatorSignatureDate: '2026-02-02T10:00:00Z' },
      { id: 'review-1', createdDated: '2026-02-01T09:00:00Z', creatorSignatureDate: '2026-02-02T10:00:00Z' },
    ],
    content_snapshot: { plan_id: 'plan-1' },
  })

  expect(aggregate).toMatchObject({
    lastUpdated: '2026-02-04T17:30:00Z',
    planHistory: [
      { treatmentPlanId: 'plan-1', planDate: '2026-01-03T09:00:00Z', lastModified: '2026-02-04T17:30:00Z' },
    ],
    treatmentReviews: [
      { reviewId: 'review-1', reviewDate: '2026-02-01T09:00:00Z', signatureDate: '2026-02-02T10:00:00Z' },
    ],
  })
})
