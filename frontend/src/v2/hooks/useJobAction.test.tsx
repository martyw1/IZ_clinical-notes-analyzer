import { StrictMode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { ApiHarnessJob } from '../api/jobTypes'
import { useJobAction } from './useJobAction'

const running: ApiHarnessJob = {
  jobId: 'synthetic-long-job', jobType: 'two_stage_roster_update', status: 'running',
  createdAt: '', startedAt: '', updatedAt: '', completedAt: '', phase: 'fetching_plan_details',
  message: 'Still receiving plans', progressPercent: 40, phaseCompleted: 4, phaseTotal: 10,
  progressDeterminate: true, currentEndpoint: '', currentPage: 0, recordsSeen: 10,
  recordsWritten: 0, recordsFailed: 0, warningsCount: 0, errorsCount: 0,
  cancelRequested: false, lastHeartbeatAt: '', artifacts: [],
}
afterEach(() => { cleanup(); vi.useRealTimers() })

test('keeps watching after a minute and preserves the status message in StrictMode', async () => {
  vi.useFakeTimers()
  let current = running
  const completed = vi.fn()
  const poll = vi.fn(async () => current)
  const { result, unmount } = renderHook(() => useJobAction({ start: async () => running, poll,
    onCompleted: completed, failureMessage: 'Failed' }), { wrapper: StrictMode })
  await act(async () => { await result.current.run() })
  await act(async () => { await vi.advanceTimersByTimeAsync(65_000) })
  expect(result.current.isActive).toBe(true)
  expect(result.current.message).toMatch(/still running/)
  current = { ...running, status: 'completed', progressPercent: 100 }
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
  expect(completed).toHaveBeenCalledTimes(1)
  expect(result.current.isActive).toBe(false)
  unmount()
  const count = poll.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
  expect(poll).toHaveBeenCalledTimes(count)
})

test('reattaches to a saved running job without starting another import', async () => {
  const start = vi.fn(async () => running)
  const poll = vi.fn(async () => ({ ...running, status: 'completed' as const }))
  const completed = vi.fn()
  const { result } = renderHook(() => useJobAction({ start, poll, onCompleted: completed, failureMessage: 'Failed' }))
  await act(async () => { result.current.setLastJob(running) })
  expect(start).not.toHaveBeenCalled()
  expect(poll).toHaveBeenCalledWith(running.jobId)
  expect(completed).toHaveBeenCalledTimes(1)
})
