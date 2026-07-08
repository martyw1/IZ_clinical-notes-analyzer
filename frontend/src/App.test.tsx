import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

function signIn() {
  render(<App />)
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'local-only' } })
  fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
}

describe('V2 active app shell', () => {
  it('shows V2 login and required navigation after admin sign-in', () => {
    signIn()

    expect(screen.getByText('Version 2.0 Beta')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: /primary navigation/i })
    const labels = within(nav).getAllByRole('button').map((button) => button.textContent)

    expect(labels).toEqual([
      'Status Dashboard',
      'Treatment Plans',
      'Manual Upload',
      'API Testing Harness',
      'Users',
      'Forensic Logs',
      'Settings',
      'Help',
    ])
  })

  it('renders Treatment Plans status strip in risk order and excludes patient names', () => {
    signIn()
    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))

    const strip = screen.getByLabelText('Treatment Plans status strip')
    const labels = within(strip).getAllByText(/Missing Data|Needs Review|Incomplete|Within Window|Late|Conflicting Evidence|Unable to Evaluate/)
    expect(labels.map((label) => label.textContent)).toEqual([
      'Missing Data',
      'Needs Review',
      'Incomplete',
      'Within Window',
      'Late',
      'Conflicting Evidence',
      'Unable to Evaluate',
    ])
    expect(screen.getAllByText('Patient ID 307').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Marleigh|Johnson|client name/i)).not.toBeInTheDocument()
  })

  it('shows nested detail sections, blocks override without reason, and saves with reason', () => {
    signIn()
    fireEvent.click(screen.getByRole('button', { name: 'Treatment Plans' }))

    expect(screen.getByText('Diagnoses')).toBeInTheDocument()
    expect(screen.getByText('Behavioral Definitions')).toBeInTheDocument()
    expect(screen.getByText('Goals')).toBeInTheDocument()
    expect(screen.getByText(/Objective 1:/)).toBeInTheDocument()
    expect(screen.getByText('Interventions')).toBeInTheDocument()
    expect(screen.getByText(/Signature image\/base64 never renders/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /save override/i }))
    expect(screen.getByRole('status')).toHaveTextContent('Override reason is required.')

    fireEvent.change(screen.getByLabelText(/override reason/i), { target: { value: 'Reviewed source path and accepted manager override.' } })
    fireEvent.click(screen.getByRole('button', { name: /save override/i }))
    expect(screen.getByRole('status')).toHaveTextContent('Override saved with required reason and audit event.')
  })

  it('shows large API job progress and bounded artifact list', async () => {
    signIn()
    fireEvent.click(screen.getByRole('button', { name: 'API Testing Harness' }))
    fireEvent.click(screen.getByRole('button', { name: /start synthetic large job/i }))

    expect(screen.getByLabelText(/Pull ALL Treatment Plans job card/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Completed job artifacts')).toBeInTheDocument())
    expect(screen.getByText('all-treatment-plans.all-fields.redacted.jsonl')).toBeInTheDocument()
    expect(screen.queryByText(/signatureData.*base64/i)).not.toBeInTheDocument()
  })
})
