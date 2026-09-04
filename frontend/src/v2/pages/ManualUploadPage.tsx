import { useEffect, useRef, useState, type FormEvent } from 'react'
import { importTreatmentPlanAggregate, importTreatmentPlanFile } from '../api/client'
import { ApiRequestError, isRecord } from '../api/json'
import { messageForUploadError, readFileText } from './manualUploadFile'

type ManualUploadPageProps = {
  readonly token: string
  readonly onNavigate: (view: string) => void
}

export function ManualUploadPage(props: ManualUploadPageProps) {
  return <ManualUploadForm key={props.token} {...props} />
}

function ManualUploadForm({ token, onNavigate }: ManualUploadPageProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [jsonInputVersion, setJsonInputVersion] = useState(0)
  const [binderFiles, setBinderFiles] = useState<readonly File[]>([])
  const [binderInputVersion, setBinderInputVersion] = useState(0)
  const [rawPatientId, setRawPatientId] = useState('')
  const [confirmPatientIdCorrection, setConfirmPatientIdCorrection] = useState(false)
  const [correctionRequired, setCorrectionRequired] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [isParsing, setIsParsing] = useState(false)
  const [jsonMessage, setJsonMessage] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [binderMessage, setBinderMessage] = useState('')
  const [binderError, setBinderError] = useState('')
  const [binderWarnings, setBinderWarnings] = useState<readonly string[]>([])
  const [binderCounts, setBinderCounts] = useState({ parsed: 0, opaque: 0 })
  const [binderImported, setBinderImported] = useState(false)
  const binderInput = useRef<HTMLInputElement>(null)
  const jsonOperation = useRef<object | null>(null)
  const binderOperation = useRef<object | null>(null)

  useEffect(() => () => {
    jsonOperation.current = null
    binderOperation.current = null
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (jsonOperation.current) return
    setJsonMessage('')
    setJsonError('')
    if (!selectedFile) {
      setJsonError('Choose a normalized V2 aggregate JSON file before importing.')
      return
    }
    const operation = {}
    jsonOperation.current = operation
    setIsImporting(true)
    try {
      const payload: unknown = JSON.parse(await readFileText(selectedFile))
      if (jsonOperation.current !== operation) return
      if (!isRecord(payload)) {
        setJsonError('The selected JSON file must contain one treatment-plan aggregate object.')
        return
      }
      const result = await importTreatmentPlanAggregate(token, payload)
      if (jsonOperation.current !== operation) return
      setJsonMessage(`Imported ${result.patientDisplayLabel} from ${result.sourceMode}.`)
      clearJsonSelection()
    } catch (importError) {
      if (jsonOperation.current === operation) setJsonError(messageForUploadError(importError))
    } finally {
      if (jsonOperation.current === operation) {
        jsonOperation.current = null
        setIsImporting(false)
      }
    }
  }

  async function handleRawFileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (binderOperation.current) return
    setBinderMessage('')
    setBinderError('')
    setBinderWarnings([])
    setBinderImported(false)
    if (!binderFiles.length) {
      setBinderError('Choose one or more treatment-plan binder files before importing.')
      return
    }
    const operation = {}
    binderOperation.current = operation
    setIsParsing(true)
    try {
      const result = await importTreatmentPlanFile(token, binderFiles, rawPatientId, confirmPatientIdCorrection)
      if (binderOperation.current !== operation) return
      const warningSummary = result.status === 'imported_with_warnings' ? ' Imported with warnings.' : ''
      const correctionSummary = result.patientIdCorrectionApplied ? ' Confirmed MRN correction applied.' : ''
      setBinderMessage(`Secure processing complete. Imported ${result.patientDisplayLabel} from ${result.fileCount} source ${result.fileCount === 1 ? 'file' : 'files'}.${warningSummary}${correctionSummary}`)
      setBinderWarnings(result.warnings)
      setBinderCounts({ parsed: result.parsedFileCount, opaque: result.opaqueFileCount })
      setBinderImported(true)
      setBinderFiles([])
      setBinderInputVersion((current) => current + 1)
      setRawPatientId('')
      setConfirmPatientIdCorrection(false)
      setCorrectionRequired(false)
    } catch (importError) {
      if (binderOperation.current === operation) {
        setBinderError(messageForUploadError(importError))
        setCorrectionRequired(importError instanceof ApiRequestError && importError.status === 409)
      }
    } finally {
      if (binderOperation.current === operation) {
        binderOperation.current = null
        setIsParsing(false)
      }
    }
  }

  function clearJsonSelection() {
    setSelectedFile(null)
    setJsonInputVersion((current) => current + 1)
    setJsonError('')
  }

  function selectBinderFiles(files: FileList | null) {
    setBinderFiles(files ? Array.from(files) : [])
    setBinderMessage('')
    setBinderError('')
    setBinderWarnings([])
    setBinderImported(false)
    setCorrectionRequired(false)
  }

  function removeBinderFile(index: number) {
    const remaining = binderFiles.filter((_file, candidateIndex) => candidateIndex !== index)
    const selection = new DataTransfer()
    remaining.forEach((file) => selection.items.add(file))
    if (binderInput.current) binderInput.current.files = selection.files
    setBinderFiles(remaining)
    setBinderError('')
  }

  function clearBinderSelection() {
    setBinderFiles([])
    setBinderInputVersion((current) => current + 1)
    setBinderError('')
    setCorrectionRequired(false)
  }

  return (
    <div className='page-grid'>
      <section className='panel settings-form'>
        <p className='eyebrow'>Manual Upload</p>
        <h2>Point-in-time treatment-plan evidence</h2>
        <p>Import normalized V2 aggregate JSON, or parse supported treatment-plan evidence files into the same encrypted aggregate store.</p>
        <form onSubmit={handleSubmit} aria-label='Normalized aggregate import'>
          <label>
            Normalized V2 aggregate JSON
            <input
              key={jsonInputVersion}
              type='file'
              accept='.json,application/json'
              onChange={(event) => { setSelectedFile(event.currentTarget.files?.[0] ?? null); setJsonError(''); setJsonMessage('') }}
              disabled={isImporting}
            />
          </label>
          {selectedFile && <button type='button' className='secondary-button' onClick={clearJsonSelection} disabled={isImporting}>Clear JSON selection</button>}
          {jsonError && <p role='alert' className='error-banner'>{jsonError}</p>}
          {jsonMessage && <p role='status'>{jsonMessage}</p>}
          <button type='submit' disabled={isImporting}>
            {isImporting ? 'Importing...' : 'Import treatment-plan aggregate'}
          </button>
        </form>
        <form onSubmit={handleRawFileSubmit} aria-label='Treatment-plan binder import'>
          <label>
            Treatment-plan binder files
            <input
              ref={binderInput}
              key={binderInputVersion}
              type='file'
              multiple
              accept='.txt,.md,.csv,.tsv,.pdf,.xlsx,.docx,.rtf,.doc,.zip,.png,.jpg,.jpeg,text/plain,text/markdown,text/csv,text/tab-separated-values,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/rtf,application/msword,application/zip,image/png,image/jpeg'
              onChange={(event) => selectBinderFiles(event.currentTarget.files)}
              disabled={isParsing}
            />
          </label>
          <div className='binder-selection' aria-live='polite'>
            <div className='binder-selection-header'>
              <strong>{binderFiles.length ? `${binderFiles.length} ${binderFiles.length === 1 ? 'file' : 'files'} selected` : 'No binder files selected'}</strong>
              {binderFiles.length > 0 && <button type='button' className='secondary-button' onClick={clearBinderSelection} disabled={isParsing}>Clear selection</button>}
            </div>
            {binderFiles.length > 0 && <ul className='binder-file-list'>
              {binderFiles.map((file, index) => <li key={`${file.name}:${file.size}:${file.lastModified}`}>
                <span>{file.name}</span>
                <button type='button' className='secondary-button' aria-label={`Remove ${file.name}`} onClick={() => removeBinderFile(index)} disabled={isParsing}>Remove</button>
              </li>)}
            </ul>}
          </div>
          <label>
            MRN override
            <input
              value={rawPatientId}
              onChange={(event) => setRawPatientId(event.currentTarget.value)}
              placeholder='Required when the file omits MRN'
              disabled={isParsing}
            />
          </label>
          <label className='checkbox-row'>
            <input
              type='checkbox'
              checked={confirmPatientIdCorrection}
              onChange={(event) => setConfirmPatientIdCorrection(event.currentTarget.checked)}
              disabled={isParsing}
            />
            I confirm this MRN correction when the override differs from evidence detected in the binder.
          </label>
          {binderError && <p role='alert' className='error-banner'>{binderError}</p>}
          {binderMessage && <p role='status' className={binderWarnings.length ? 'binder-status warning' : 'binder-status'}>{binderMessage}</p>}
          {binderImported && <div className='binder-result-summary' aria-label='Binder processing counts'>
            <span>{binderCounts.parsed} parsed</span>
            <span>{binderCounts.opaque} stored without parsing</span>
          </div>}
          {binderWarnings.length > 0 && <ul className='binder-warning-list'>
            {binderWarnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>}
          <div className='binder-actions'>
            <button type='submit' disabled={isParsing || (correctionRequired && !confirmPatientIdCorrection)}>
              {isParsing ? 'Securely processing binder...' : correctionRequired ? 'Retry with confirmed MRN' : 'Upload and securely process binder'}
            </button>
            {binderImported && <button type='button' className='secondary-button' onClick={() => onNavigate('Patient Roster')}>Review in Patient Roster</button>}
          </div>
        </form>
      </section>
      <section className='panel'>
        <p className='eyebrow'>Current boundary</p>
        <h2>Manual evidence import</h2>
        <div className='source-card-grid'>
          <article className='source-card'><h3>Parsed deterministically</h3><p>Text, Markdown, CSV, TSV, text-extractable PDF, XLSX, DOCX, and RTF sources are merged into one treatment-plan result. Conflicting evidence is reported instead of guessed.</p></article>
          <article className='source-card'><h3>Stored safely</h3><p>Every selected source is encrypted under a generated identifier. Original filenames are cleared from the page after a successful import and are not persisted.</p></article>
          <article className='source-card'><h3>Opaque sources</h3><p>Legacy DOC, ZIP, PNG, and JPEG files can be archived encrypted, but are counted as stored without parsing and produce explicit warnings.</p></article>
        </div>
      </section>
    </div>
  )
}
