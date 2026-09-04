import { expect, test } from 'vitest'
import { formatDateTime24Hour, formatUtcEventDateTime } from './treatmentPlanFormatting'

test('formats history timestamps explicitly in UTC', () => {
  expect(formatDateTime24Hour('2026-08-01T12:34:00-04:00')).toBe('2026-08-01 16:34 UTC')
})

test('uses a readable fallback when a timestamp is absent or invalid', () => {
  expect(formatDateTime24Hour('')).toBe('Unknown')
  expect(formatDateTime24Hour('not-a-timestamp')).toBe('not-a-timestamp')
})

test.each([
  ['2026-09-04 04:30:00', '2026-09-04 04:30 UTC'],
  ['2026-09-04T04:30:00', '2026-09-04 04:30 UTC'],
  ['2026-09-04 04:30:00.5', '2026-09-04 04:30 UTC'],
  ['2026-09-04T04:30:00.123456', '2026-09-04 04:30 UTC'],
  ['2026-09-04T04:30:00Z', '2026-09-04 04:30 UTC'],
  ['2026-09-04T04:30:00-04:00', '2026-09-04 08:30 UTC'],
  ['2026-09-04T04:30:00+05:30', '2026-09-03 23:00 UTC'],
  ['', 'Unknown'],
  ['not-a-timestamp', 'not-a-timestamp'],
  ['2026-99-99 99:30:00', '2026-99-99 99:30:00'],
])('formats the known-UTC event contract without a browser-local shift: %s', (input, expected) => {
  expect(formatUtcEventDateTime(input)).toBe(expected)
})

test('does not reinterpret general clinical timestamps or widen naive UTC event shapes', () => {
  const clinical = '2026-09-04T04:30:00'
  expect(formatDateTime24Hour(clinical)).toBe(formatDateTime24Hour(new Date(clinical).toISOString()))
  for (const nonWire of ['2026-09-04T04:30', '2026-09-04', 'September 4, 2026 04:30:00']) {
    expect(formatUtcEventDateTime(nonWire)).toBe(formatDateTime24Hour(nonWire))
  }
})
