import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UsersPage } from './UsersPage'

beforeEach(() => {
  const users = [{ id: 31, username: 'synthetic_operator', full_name: 'Synthetic operator',
    role: 'office_manager', auth_state: 'active', must_reset_password: false, is_active: true }]
  vi.stubGlobal('fetch', vi.fn(async (path: string) => new Response(JSON.stringify(path === '/api/users' ? users : []), {
    status: 200, headers: { 'content-type': 'application/json' },
  })))
})

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Users table presentation', () => {
  it('preserves the populated user values and assignment controls', async () => {
    // Given: a synthetic user returned from the existing client boundary.
    render(<UsersPage token='synthetic-nonworking-token' />)
    // When: the user table finishes loading.
    await screen.findByText('Synthetic operator')
    // Then: existing values and assignment controls are still available.
    expect(screen.getByRole('cell', { name: 'office_manager' })).toBeVisible()
    expect(screen.getByRole('cell', { name: 'active' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Assign facility' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Assign patient' })).toBeVisible()
  })

  it('labels every stacked user cell with its actual column heading', async () => {
    // Given: the responsive table uses data-label as visible cell headings.
    render(<UsersPage token='synthetic-nonworking-token' />)
    // When: the populated row is displayed.
    const row = (await screen.findByText('Synthetic operator')).closest('tr')
    if (!row) throw new Error('Expected the synthetic user row')
    // Then: all five values retain their column meaning when the header is clipped.
    expect(within(row).getAllByRole('cell').map(cell => cell.getAttribute('data-label')))
      .toEqual(['User', 'Role', 'Status', 'Password reset', 'Action'])
  })
})
