import { test as base, expect } from '@playwright/test'

export { expect }

export function sanitizeFailureErrors(errors) {
  const seen = new Set()
  const sanitize = error => {
    if (!error || typeof error !== 'object' || seen.has(error)) return
    seen.add(error)
    error.message = 'FAILURE_DETAILS_REDACTED'
    error.stack = undefined
    error.errorContext = 'FAILURE_DETAILS_REDACTED'
    if (error.value !== undefined) error.value = 'FAILURE_DETAILS_REDACTED'
    if (error.cause) sanitize(error.cause)
  }
  for (const error of errors) sanitize(error)
}

export const test = base.extend({
  failurePrivacy: [async ({}, use, testInfo) => {
    try { await use() } finally { sanitizeFailureErrors(testInfo.errors) }
  }, { auto: true, timeout: 5_000, box: true }],
})
