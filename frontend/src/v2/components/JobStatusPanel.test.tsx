import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import type { ApiHarnessJob } from '../api/jobTypes'
import { JobStatusPanel } from './JobStatusPanel'

const completed: ApiHarnessJob = {
  jobId: 'synthetic-job', jobType: 'approved_treatment_plan_sync',
  createdAt: '', startedAt: '', updatedAt: '', completedAt: '2026-09-10T21:20:58.082903',
  status: 'completed', phase: '', message: '', progressPercent: 100,
  currentEndpoint: '', currentPage: 0, recordsSeen: 581, recordsWritten: 13,
  recordsFailed: 0, warningsCount: 0, errorsCount: 0, cancelRequested: false,
  lastHeartbeatAt: '', artifacts: [],
}

test('keeps a persisted UTC completion time unchanged in a non-UTC browser environment', () => {
  render(<JobStatusPanel job={completed} isActive={false} message='' error='' />)
  expect(screen.getByText(/Last run completed/)).toHaveTextContent('2026-09-10 21:20 UTC')
})

test('shows a reloaded job failure reason even without a local request error', () => {
  const job: ApiHarnessJob = { ...completed, status: 'failed', completedAt: '', errorsCount: 1, message: 'Alleva did not respond before the request timeout. Resume the sync safely.' }
  render(<JobStatusPanel job={job} isActive={false} message='' error='' />)
  expect(screen.getByRole('alert')).toHaveTextContent(job.message)
  const count = screen.getByText('Errors').closest('div')
  expect(count).not.toBeNull()
  if (count) expect(within(count).getByText('1')).toBeVisible()
})

test('explains historical failures without a saved reason', () => {
  render(<JobStatusPanel job={{ ...completed, status: 'failed', completedAt: '' }} isActive={false} message='' error='' />)
  expect(screen.getByRole('alert')).toHaveTextContent(/Forensic Logs/)
})

test('prefers a current request error over the previous job failure', () => {
  render(<JobStatusPanel job={{ ...completed, status: 'failed', message: 'Previous failure' }} isActive={false} message='' error='Current request failed' />)
  expect(screen.getAllByRole('alert')).toHaveLength(1)
  expect(screen.getByRole('alert')).toHaveTextContent('Current request failed')
})
