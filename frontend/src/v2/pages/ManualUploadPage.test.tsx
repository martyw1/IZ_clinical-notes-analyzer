import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ManualUploadPage } from './ManualUploadPage'

describe('Manual Upload binder workflow', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('uploads the selected binder files, shows warnings, and links to Treatment Plans', async () => {
    // Given: three synthetic binder sources are selected and one is removed.
    const onNavigate = vi.fn()
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body
      expect(body).toBeInstanceOf(FormData)
      if (!(body instanceof FormData)) return response({ detail: 'Expected multipart form data.' }, 500)
      expect(body.getAll('file')).toHaveLength(2)
      expect(body.get('patient_id')).toBe('944')
      expect(body.get('confirm_patient_id_correction')).toBe('true')
      return response(binderResult(), 201)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ManualUploadPage token='token' onNavigate={onNavigate} />)

    const input = screen.getByLabelText(/treatment-plan binder files/i)
    fireEvent.change(input, {
      target: {
        files: [
          new File(['Patient ID: 944'], 'demographics.txt', { type: 'text/plain' }),
          new File(['{\\rtf1 Admission Date: 2026-06-04}'], 'dates.rtf', { type: 'application/rtf' }),
          new File(['opaque'], 'scan.png', { type: 'image/png' }),
        ],
      },
    })
    expect(screen.getByText('3 files selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove dates.rtf' }))
    expect(screen.getByText('2 files selected')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Patient ID override'), { target: { value: '944' } })
    fireEvent.click(screen.getByLabelText(/confirm this patient id correction/i))

    // When: the binder is uploaded once.
    fireEvent.click(screen.getByRole('button', { name: 'Upload and securely process binder' }))

    // Then: warning-aware success is visible, selected names are cleared, and navigation is explicit.
    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('Secure processing complete')
    expect(status).toHaveTextContent('Imported with warnings')
    expect(screen.getByText(/one source was archived but could not be parsed deterministically/i)).toBeInTheDocument()
    expect(screen.queryByText('demographics.txt')).not.toBeInTheDocument()
    expect(screen.queryByText('scan.png')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Review in Treatment Plans' }))
    expect(onNavigate).toHaveBeenCalledWith('Treatment Plans')
  })

  it('keeps binder correction errors inside the binder form without masking JSON import feedback', async () => {
    // Given: the server requires explicit confirmation for a detected Patient ID mismatch.
    vi.stubGlobal('fetch', vi.fn(async () => response({ detail: 'Confirm the Patient ID correction and submit again.' }, 409)))
    render(<ManualUploadPage token='token' onNavigate={vi.fn()} />)
    const binderForm = screen.getByRole('button', { name: 'Upload and securely process binder' }).closest('form')
    expect(binderForm).not.toBeNull()
    if (!binderForm) return
    fireEvent.change(within(binderForm).getByLabelText(/treatment-plan binder files/i), {
      target: { files: [new File(['Patient ID: 812'], 'source.txt', { type: 'text/plain' })] },
    })

    // When: the binder is submitted without correction confirmation.
    fireEvent.submit(binderForm)

    // Then: the binder form owns the actionable failure and the JSON form stays clear.
    expect(await within(binderForm).findByRole('alert')).toHaveTextContent('Confirm the Patient ID correction and submit again.')
    const jsonForm = screen.getByRole('button', { name: 'Import treatment-plan aggregate' }).closest('form')
    expect(jsonForm).not.toBeNull()
    if (jsonForm) expect(within(jsonForm).queryByRole('alert')).not.toBeInTheDocument()
  })

  it('prevents duplicate binder submissions while parsing', async () => {
    // Given: a binder request remains in flight.
    let finishRequest: ((value: Response) => void) | undefined
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finishRequest = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    render(<ManualUploadPage token='token' onNavigate={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/treatment-plan binder files/i), {
      target: { files: [new File(['Patient ID: 944'], 'source.txt', { type: 'text/plain' })] },
    })

    // When: upload starts and the user tries the control again.
    const submit = screen.getByRole('button', { name: 'Upload and securely process binder' })
    fireEvent.click(submit)
    expect(await screen.findByRole('button', { name: 'Securely processing binder...' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Securely processing binder...' }))

    // Then: only one request is made and the form returns to ready after completion.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    finishRequest?.(response(binderResult(), 201))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload and securely process binder' })).toBeEnabled())
  })
})

function binderResult() {
  return {
    status: 'imported_with_warnings', patient_id: '944', patient_display_label: 'Patient ID 944',
    source_mode: 'manual_upload', criteria_total: 42, encrypted_at_rest: true,
    source_file_archived: true, source_file_id: 'source-1', source_file_ids: ['source-1', 'source-2'],
    patient_id_correction_applied: true, file_count: 2, parsed_file_count: 1, opaque_file_count: 1,
    overall_status: 'Unable to Evaluate', warnings: ['One source was archived but could not be parsed deterministically.'],
  }
}

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } })
}
