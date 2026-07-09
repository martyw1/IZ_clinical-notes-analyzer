<<<<<<< HEAD
import { useState, type FormEvent } from 'react'
import { importTreatmentPlanAggregate, importTreatmentPlanFile } from '../api/client'
import { ApiRequestError, isRecord } from '../api/json'

type ManualUploadPageProps = {
  readonly token: string
}

class FileReadError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FileReadError'
  }
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof FileReadError) return error.message
  if (error instanceof SyntaxError) return 'The selected file is not valid JSON.'
  if (error instanceof Error) return error.message
  return 'Unable to import the selected treatment-plan aggregate.'
}

function readFileText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new FileReadError('Unable to read the selected file.'))
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result)
        return
      }
      reject(new FileReadError('The selected file did not contain readable text.'))
    }
    reader.readAsText(file)
  })
}

export function ManualUploadPage({ token }: ManualUploadPageProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [rawFile, setRawFile] = useState<File | null>(null)
  const [rawPatientId, setRawPatientId] = useState('')
  const [isImporting, setIsImporting] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setError('')
    if (!selectedFile) {
      setError('Choose a normalized V2 aggregate JSON file before importing.')
      return
    }
    setIsImporting(true)
    try {
      const payload: unknown = JSON.parse(await readFileText(selectedFile))
      if (!isRecord(payload)) {
        setError('The selected JSON file must contain one treatment-plan aggregate object.')
        return
      }
      const result = await importTreatmentPlanAggregate(token, payload)
      setMessage(`Imported ${result.patientDisplayLabel} from ${result.sourceMode}.`)
    } catch (importError) {
      setError(messageForError(importError))
    } finally {
      setIsImporting(false)
    }
  }

  async function handleRawFileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setError('')
    if (!rawFile) {
      setError('Choose a supported treatment-plan file before importing.')
      return
    }
    setIsParsing(true)
    try {
      const result = await importTreatmentPlanFile(token, rawFile, rawPatientId)
      const archived = result.sourceFileArchived ? ' and archived encrypted source file' : ''
      setMessage(`Imported ${result.patientDisplayLabel} from parsed ${result.sourceMode} file${archived}.`)
    } catch (importError) {
      setError(messageForError(importError))
    } finally {
      setIsParsing(false)
    }
  }

  return (
    <div className='page-grid'>
      <section className='panel settings-form'>
        <p className='eyebrow'>Manual Upload</p>
        <h2>Point-in-time treatment-plan evidence</h2>
        <p>Import normalized V2 aggregate JSON, or parse supported treatment-plan evidence files into the same encrypted aggregate store.</p>
        <form onSubmit={handleSubmit}>
          <label>
            Normalized V2 aggregate JSON
            <input
              type='file'
              accept='.json,application/json'
              onChange={(event) => setSelectedFile(event.currentTarget.files?.[0] ?? null)}
            />
          </label>
          {error && <p role='alert' className='error-banner'>{error}</p>}
          {message && <p role='status'>{message}</p>}
          <button type='submit' disabled={isImporting}>
            {isImporting ? 'Importing...' : 'Import treatment-plan aggregate'}
          </button>
        </form>
        <form onSubmit={handleRawFileSubmit}>
          <label>
            Patient ID override
            <input
              value={rawPatientId}
              onChange={(event) => setRawPatientId(event.currentTarget.value)}
              placeholder='Required when the file omits Patient ID'
            />
          </label>
          <label>
            Treatment-plan file (TXT, CSV, TSV, MD, PDF, XLSX)
            <input
              type='file'
              accept='.txt,.md,.csv,.tsv,.pdf,.xlsx,text/plain,text/markdown,text/csv,text/tab-separated-values,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
              onChange={(event) => setRawFile(event.currentTarget.files?.[0] ?? null)}
            />
          </label>
          <button type='submit' disabled={isParsing}>
            {isParsing ? 'Parsing...' : 'Upload and parse treatment-plan file'}
          </button>
        </form>
      </section>
      <section className='panel'>
        <p className='eyebrow'>Current boundary</p>
        <h2>Manual evidence import</h2>
        <div className='source-card-grid'>
          <article className='source-card'><h3>Accepted now</h3><p>V2 aggregate JSON plus text, Markdown, CSV, TSV, PDF, and XLSX files with labeled treatment-plan fields.</p></article>
          <article className='source-card'><h3>Stored safely</h3><p>Aggregate payloads and parsed source files are encrypted. Queue columns keep only patient ID and non-secret status metadata.</p></article>
          <article className='source-card'><h3>Still pending</h3><p>Multi-document binders and patient correction UI remain documented blockers for later stations.</p></article>
        </div>
      </section>
    </div>
=======
export function ManualUploadPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Manual Upload</p>
      <h2>Point-in-time treatment-plan evidence</h2>
      <p>Manual uploads normalize into the same V2 aggregate and content graph used by API evidence.</p>
      <div className='source-card-grid'>
        <article className='source-card'><h3>Supported files</h3><p>PDF, CSV, TSV, XLSX, TXT, and MD.</p></article>
        <article className='source-card'><h3>Metadata correction</h3><p>Office managers can supply patient ID, LOC, signature dates, and missing source dates.</p></article>
        <article className='source-card'><h3>Fingerprinting</h3><p>Unchanged batches are skipped unless explicitly reprocessed.</p></article>
      </div>
    </section>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
  )
}
