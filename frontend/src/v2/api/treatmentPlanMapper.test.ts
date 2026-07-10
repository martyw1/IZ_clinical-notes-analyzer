import { expect, test } from 'vitest'
import type { JsonRecord } from './json'
import { mapTreatmentPlanAggregate } from './treatmentPlanMapper'

test('maps a missing source mode to unavailable instead of synthetic fixture data', () => {
  const payload: JsonRecord = {}

  const aggregate = mapTreatmentPlanAggregate(payload)

  expect(aggregate.sourceMode).toBe('unavailable')
})
