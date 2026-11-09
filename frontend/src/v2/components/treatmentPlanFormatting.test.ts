import { expect, test } from 'vitest'
import { formatDateTime24Hour, formatUtcEventDateTime } from './treatmentPlanFormatting'

test.each([
  ['2026-08-01T12:34:00-04:00', '2026-08-01 12:34 EDT'],
  ['2026-01-01T02:30:00Z', '2025-12-31 21:30 EST'],
  ['2026-09-04 04:30:00', '2026-09-04 00:30 EDT'],
  ['2026-09-04T04:30:00.123456', '2026-09-04 00:30 EDT'],
  ['2026-09-04T04:30', '2026-09-04 00:30 EDT'],
  ['2026-09-04T04:30:00+05:30', '2026-09-03 19:00 EDT'],
  ['2026-03-08T06:59:00Z', '2026-03-08 01:59 EST'],
  ['2026-03-08T07:00:00Z', '2026-03-08 03:00 EDT'],
  ['2026-11-01T05:30:00Z', '2026-11-01 01:30 EDT'],
  ['2026-11-01T06:30:00Z', '2026-11-01 01:30 EST'],
  ['2026-11-06', '2026-11-06'],
  ['', 'Unknown'],
  ['not-a-timestamp', 'not-a-timestamp'],
  ['2026-99-99 99:30:00', '2026-99-99 99:30:00'],
])('displays %s in Eastern time while preserving calendar dates and wire input', (input, expected) => {
  const original = input
  expect(formatDateTime24Hour(input)).toBe(expected)
  expect(formatUtcEventDateTime(input)).toBe(expected)
  expect(input).toBe(original)
})
