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
