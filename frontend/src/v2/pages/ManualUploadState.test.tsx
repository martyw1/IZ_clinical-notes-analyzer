import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManualUploadPage } from './ManualUploadPage'

const jsonLabel = 'Normalized V2 aggregate JSON'
const binderLabel = 'Treatment-plan binder files'
const jsonSubmit = 'Import treatment-plan aggregate'
const binderSubmit = 'Upload and securely process binder'

function inputFor(label: string): HTMLInputElement {
  const input = screen.getByLabelText(label)
  if (!(input instanceof HTMLInputElement)) throw new Error('File input missing')
  return input
}

function selectFile(label: string) {
  const file = new File([label === jsonLabel ? '{}' : 'MRN: SYNTHETIC-006'], label === jsonLabel ? 'aggregate.json' : 'binder.txt')
  fireEvent.change(inputFor(label), { target: { files: [file] } })
  return file
}

function submitForm(label: string) {
  const form = inputFor(label).closest('form')
  if (!form) throw new Error('Upload form missing')
  fireEvent.submit(form)
}

function success() {
  return new Response(JSON.stringify({ patient_record_id: 6003, plan_version_id: 6004, treatment_plan_id: 'synthetic-state-plan', patient_display_label: 'MRN SYNTHETIC-006', source_mode: 'manual_upload', status: 'imported', file_count: 1, parsed_file_count: 1, warnings: [] }))
}

describe('native upload selection state', () => {
  beforeEach(() => {
    vi.stubGlobal('DataTransfer', class {
      readonly files: File[] = []
      readonly items = { add: (file: File) => { this.files.push(file) } }
    })
  })
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it.each([jsonLabel, binderLabel])('clears the native file and selected object when %s succeeds', async (label) => {
    // Given: one synthetic file is selected.
    const fetchMock = vi.fn(async () => success())
    vi.stubGlobal('fetch', fetchMock)
    render(<ManualUploadPage token='current' onNavigate={vi.fn()} />)
    selectFile(label)
    // When: its import succeeds.
    submitForm(label)
    await screen.findByRole('status')
    // Then: the native input is empty and another submit cannot reuse the object.
    expect(inputFor(label).files?.length).toBe(0)
    submitForm(label)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(fetchMock.mock.calls.length).toBe(1)
  })

  it.each([jsonLabel, binderLabel])('preserves retryable selection when %s fails', async (label) => {
    // Given: a selected file's first import fails and the second succeeds.
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 500 })).mockResolvedValueOnce(success())
    vi.stubGlobal('fetch', fetchMock)
    render(<ManualUploadPage token='current' onNavigate={vi.fn()} />)
    const file = selectFile(label)
    // When: the failed import is retried without choosing a file again.
    submitForm(label)
    await screen.findByRole('alert')
    expect(inputFor(label).files?.[0]).toBe(file)
    submitForm(label)
    // Then: retry succeeds exactly once and clears native selection.
    await screen.findByRole('status')
    expect(fetchMock.mock.calls.length).toBe(2)
    expect(inputFor(label).files?.length).toBe(0)
  })

  it('updates native files when a binder file is removed', () => {
    // Given: two binder files are selected.
    render(<ManualUploadPage token='current' onNavigate={vi.fn()} />)
    const files = [new File(['a'], 'one.txt'), new File(['b'], 'two.txt')]
    fireEvent.change(inputFor(binderLabel), { target: { files } })
    // When: one selected file is removed.
    fireEvent.click(screen.getByRole('button', { name: 'Remove one.txt' }))
    // Then: native selection and the visible list contain the same remaining file.
    expect(Array.from(inputFor(binderLabel).files ?? []).map((file) => file.name)).toEqual(['two.txt'])
    expect(screen.queryByText('one.txt')).not.toBeInTheDocument()
    expect(screen.getByText('two.txt')).toBeInTheDocument()
  })

  it.each([jsonLabel, binderLabel])('allows choosing the same file after %s is cleared', (label) => {
    // Given: a selected file in the corresponding form.
    render(<ManualUploadPage token='current' onNavigate={vi.fn()} />)
    const file = selectFile(label)
    // When: selection is cleared and that file is chosen again.
    fireEvent.click(screen.getByRole('button', { name: label === jsonLabel ? 'Clear JSON selection' : 'Clear selection' }))
    expect(inputFor(label).files?.length).toBe(0)
    fireEvent.change(inputFor(label), { target: { files: [file] } })
    // Then: the current native selection is the newly chosen object.
    expect(inputFor(label).files?.[0]).toBe(file)
  })

  it.each([jsonLabel, binderLabel])('emits one import when %s receives duplicate submit events', async (label) => {
    // Given: an import remains in flight.
    let finish: ((response: Response) => void) | undefined
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    render(<ManualUploadPage token='current' onNavigate={vi.fn()} />)
    selectFile(label)
    // When: the form submits twice during the same operation.
    submitForm(label)
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(1))
    submitForm(label)
    await act(async () => { finish?.(success()) })
    // Then: the second event cannot enqueue another import.
    await screen.findByRole('status')
    expect(fetchMock.mock.calls.length).toBe(1)
  })

  it.each([jsonLabel, binderLabel])('ignores stale success when the session changes during %s', async (label) => {
    // Given: an old session has a pending upload.
    let finish: ((response: Response) => void) | undefined
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const view = render(<ManualUploadPage token='old' onNavigate={vi.fn()} />)
    selectFile(label)
    submitForm(label)
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(1))
    view.rerender(<ManualUploadPage token='new' onNavigate={vi.fn()} />)
    // When: the old session's operation succeeds.
    await act(async () => { finish?.(success()) })
    // Then: its result cannot overwrite the new session's UI.
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: label === jsonLabel ? jsonSubmit : binderSubmit })).toBeEnabled()
  })
})
