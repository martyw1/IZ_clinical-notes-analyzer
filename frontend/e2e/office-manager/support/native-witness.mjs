import { createHash } from 'node:crypto'
import { closeSync, mkdtempSync, openSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { HarnessError, assertPlainPath } from './guards.mjs'

const routes = [
  ['GET', /^\/api\/v2\/patient-roster$/, 'patient-roster'],
  ['GET', /^\/api\/v2\/treatment-plan-roster$/, 'plan-roster'],
  ['GET', /^\/api\/v2\/treatment-plans$/, 'plan-list'],
  ['GET', /^\/api\/v2\/patients\/[^/]+$/, 'patient-detail'],
  ['GET', /^\/api\/v2\/treatment-plans\/[^/]+\/[^/]+$/, 'plan-detail'],
  ['GET', /^\/api\/v2\/exports\/[^/]+\/checklist-evidence\.csv$/, 'checklist-export'],
  ['GET', /^\/api\/v2\/treatment-plans\/[^/]+\/source-documents\/[^/]+\/download$/, 'source-download'],
  ['POST', /^\/api\/v2\/exports\/treatment-plans\.csv$/, 'list-export'],
  ['POST', /^\/api\/v2\/treatment-plans\/[^/]+\/manager-actions$/, 'manager-action'],
  ['POST', /^\/api\/v2\/manual-uploads\/treatment-plan-aggregate$/, 'aggregate-upload'],
  ['POST', /^\/api\/v2\/manual-uploads\/treatment-plan-file$/, 'binder-upload'],
]
const anonymousName = /^(?:redacted-checklist-evidence\.csv|treatment-plans\.csv|manual-treatment-plan-source(?:-[0-9a-f-]{12})?\.(?:txt|json|rtf|pdf|docx|png|jpg|jpeg|tif|tiff|bmp|gif|bin))$/
const maxBytes = 2 * 1024 * 1024
const maxDownloads = 8
const downloadTimeoutMs = 5_000

function singleValue(params, field) {
  const values = params.getAll(field)
  return values.length === 1 ? values[0] : null
}
function positiveId(params, field) {
  const value = singleValue(params, field)
  if (value === null || !/^[1-9]\d*$/.test(value)) return null
  const number = Number(value)
  return Number.isSafeInteger(number) ? number : null
}

export function classifyNativeRequest(request, origin) {
  let url
  try { url = new URL(request.url()) } catch { return null }
  if (url.origin !== origin || url.username || url.password) return null
  const method = request.method()
  const matched = routes.find(([verb, pattern]) => verb === method && pattern.test(url.pathname))
  if (!matched) return null
  const source = singleValue(url.searchParams, 'source_mode')
  return { route: matched[2], method, patient_record_id: positiveId(url.searchParams, 'patient_record_id'),
    plan_version_id: positiveId(url.searchParams, 'plan_version_id'),
    source_mode: ['manual_upload', 'alleva_rest_api', 'synthetic_fixture'].includes(source) ? source : null }
}

function persistBytes(directory, sequence, bytes) {
  const name = `download-${String(sequence).padStart(2, '0')}.bin`
  const file = path.join(directory, name)
  assertPlainPath(file)
  const descriptor = openSync(file, 'wx', 0o600)
  let complete = false
  try { writeFileSync(descriptor, bytes); complete = true } finally {
    closeSync(descriptor)
    if (!complete) unlinkSync(file)
  }
  return `${path.basename(directory)}/${name}`
}

async function captureDownload(download, directory, sequence) {
  const record = { sequence, anonymousSuggestedName: false, outcome: 'capture-failed', file: null, bytes: null, sha256: null }
  try { record.anonymousSuggestedName = anonymousName.test(download.suggestedFilename()) } catch { return record }
  if (!record.anonymousSuggestedName) return { ...record, outcome: 'refused-name' }
  let active = true
  let stream
  let timer
  const deadline = new Promise(resolve => {
    timer = setTimeout(() => {
      active = false
      stream?.destroy()
      resolve({ ...record, outcome: 'timeout' })
    }, downloadTimeoutMs)
  })
  const work = (async () => {
    try {
      stream = await download.createReadStream()
      if (!active) { stream.destroy(); return { ...record, outcome: 'timeout' } }
      const chunks = []
      let size = 0
      for await (const chunk of stream) {
        if (!Buffer.isBuffer(chunk)) throw new HarnessError('NATIVE_DOWNLOAD_CHUNK')
        size += chunk.length
        if (size > maxBytes) throw new HarnessError('NATIVE_DOWNLOAD_SIZE_LIMIT')
        chunks.push(chunk)
      }
      if (!active) return { ...record, outcome: 'timeout' }
      const bytes = Buffer.concat(chunks, size)
      const text = bytes.toString('utf8')
      if (/Qa1![0-9a-f]{48}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b|\bBearer\s+[A-Za-z0-9._~-]{12,}/i.test(text)) {
        return { ...record, outcome: 'refused-content' }
      }
      // The bounded synchronous write is complete before this tracked task settles.
      const file = persistBytes(directory, sequence, bytes)
      return { ...record, outcome: 'saved', file, bytes: size, sha256: createHash('sha256').update(bytes).digest('hex') }
    } catch (error) {
      const outcome = !active ? 'timeout'
        : error instanceof HarnessError && error.code === 'NATIVE_DOWNLOAD_SIZE_LIMIT' ? 'size-limit' : 'capture-failed'
      return { ...record, outcome }
    } finally { stream?.destroy() }
  })()
  try { return await Promise.race([work, deadline]) } finally { active = false; clearTimeout(timer) }
}

/** Attach only after the caller's successful-login and masked-capture gates. */
export async function startNativeWitness(page, target, writeEvidence) {
  let origin
  try {
    const url = new URL(target.baseUrl)
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
      || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw new HarnessError('NATIVE_TARGET')
    origin = url.origin
    if (new URL(page.url()).origin !== origin) throw new HarnessError('NATIVE_PAGE_ORIGIN')
  } catch (error) { throw error instanceof HarnessError ? error : new HarnessError('NATIVE_TARGET') }
  if (await page.locator('input[type="password"]').count() !== 0) throw new HarnessError('NATIVE_PASSWORD_INPUT_PRESENT')
  assertPlainPath(target.evidenceDir)
  if (!statSync(target.evidenceDir).isDirectory()) throw new HarnessError('NATIVE_EVIDENCE_DIRECTORY')
  const report = { schemaVersion: 1, phase: 'post-login-native', rawBodiesOmitted: true, observerInitiatedActions: 0,
    pageErrorCount: 0, consoleErrorCount: 0, requestFailureCount: 0, droppedRequestCount: 0, droppedDownloadCount: 0,
    requests: [], downloads: [], limits: { requestRecords: 256, downloads: maxDownloads, downloadBytes: maxBytes, downloadTimeoutMs } }
  let directory
  const pending = []
  const appendRequest = (request, status) => {
    const projected = classifyNativeRequest(request, origin)
    if (!projected) return
    if (report.requests.length === 256) { report.droppedRequestCount += 1; return }
    report.requests.push({ sequence: report.requests.length + 1, ...projected, status })
  }
  const onPageError = () => { report.pageErrorCount += 1 }
  const onConsole = message => { if (message.type() === 'error') report.consoleErrorCount += 1 }
  const onResponse = response => {
    const status = response.status()
    if (Number.isInteger(status) && status >= 100 && status <= 599) appendRequest(response.request(), status)
  }
  const onRequestFailed = request => { report.requestFailureCount += 1; appendRequest(request, null) }
  const onDownload = download => {
    if (pending.length === maxDownloads) { report.droppedDownloadCount += 1; return }
    try {
      directory ??= mkdtempSync(path.join(path.resolve(target.evidenceDir), 'native-downloads-'))
      pending.push(captureDownload(download, directory, pending.length + 1))
    } catch {
      pending.push(Promise.resolve({ sequence: pending.length + 1, anonymousSuggestedName: false,
        outcome: 'capture-failed', file: null, bytes: null, sha256: null }))
    }
  }
  const listeners = [['pageerror', onPageError], ['console', onConsole], ['response', onResponse],
    ['requestfailed', onRequestFailed], ['download', onDownload]]
  for (const [event, handler] of listeners) page.on(event, handler)
  let finishing
  return {
    finish() {
      finishing ??= (async () => {
        for (const [event, handler] of listeners) page.removeListener(event, handler)
        report.downloads = await Promise.all(pending)
        await writeEvidence('native-witness.json', report)
        return report
      })()
      return finishing
    },
  }
}
