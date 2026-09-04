import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { DashboardPage } from './DashboardPage'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const metrics = { active_patient_ids: 5, overdue_plans: 1, urgent_plans: 2, due_soon_plans: 3,
  needs_review: 4, missing_data: 77, returned: 6, conflicting: 7, unable: 8 }

test('associates every value with an explicit population unit and refreshes', async () => {
  // Given
  const fetch = vi.fn(async () => new Response(JSON.stringify({ refreshed_at: '2026-01-02T12:00:00Z',
    metrics, source_cards: [], blockers: ['LOC-change update window is unvalidated and configurable.'] }),
  { headers: { 'content-type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  // When
  render(<DashboardPage token='synthetic-test-token' />)
  // Then
  const expected = [['Patient records with plans', 5], ['Overdue plans', 1], ['Urgent plans', 2],
    ['Due soon plans', 3], ['Plans needing review', 4], ['Missing Data criteria', 77],
    ['Open correction items', 6], ['Plans with conflicting evidence', 7], ['Plans unable to evaluate', 8]] as const
  for (const [label, value] of expected) {
    const term = await screen.findByText(label, { selector: 'dt' })
    expect(term.nextElementSibling).toHaveTextContent(String(value))
  }
  expect(screen.getByText(/latest version of each source plan/i)).toBeInTheDocument()
  expect(screen.getByText(/not a partition/i)).toBeInTheDocument()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Refresh dashboard' })) })
  expect(fetch).toHaveBeenCalledTimes(2)
})
