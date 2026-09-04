import { chromium } from '@playwright/test'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import { login, capture, writeEvidence } from './fixtures.mjs'
import { startNativeWitness } from './native-witness.mjs'

const failures = []
const sourceLocations = ['interactive.mjs', 'fixtures.mjs'].flatMap(file => {
  const url = new URL(file, import.meta.url)
  const nativePath = fileURLToPath(url)
  return [...new Set([url.href, nativePath, nativePath.replaceAll('\\', '/')])].map(location => ({ file, location }))
})

async function observePhase(phase, action) {
  const started = performance.now()
  try { return await action() } catch (error) {
    try {
      const errorName = ['Error', 'TimeoutError', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError', 'AbortError'].includes(error?.name) ? error.name : 'UnknownError'
      let sourceLocation = null
      for (const line of typeof error?.stack === 'string' ? error.stack.split('\n') : []) {
        for (const entry of sourceLocations) {
          const offset = line.indexOf(entry.location)
          if (offset < 0 || !/^\s+at (?:.+ \()?$/u.test(line.slice(0, offset))) continue
          const match = line.slice(offset + entry.location.length).match(/^:([1-9]\d*):([1-9]\d*)\)?$/u)
          if (match) { sourceLocation = `support/${entry.file}:${match[1]}:${match[2]}`; break }
        }
        if (sourceLocation) break
      }
      failures.push({ phase, errorName, sourceLocation, elapsedMs: Math.max(0, Math.round(performance.now() - started)) })
      writeEvidence('interactive-failure.json', { failures })
    } catch { process.stderr.write('INTERACTIVE_DIAGNOSTIC_WRITE_FAILED\n') }
    throw error
  }
}

const browser = await observePhase('browser-launch', () => chromium.launch({ channel: process.env.IZ_OM_BROWSER_CHANNEL,
  executablePath: process.env.IZ_OM_BROWSER_EXECUTABLE, headless: false }))
const context = await observePhase('context-create', () => browser.newContext({ baseURL: process.env.IZ_OM_BASE_URL, viewport: null, serviceWorkers: 'block' }))
const cdp = await observePhase('cdp-session', () => browser.newBrowserCDPSession())
const info = await observePhase('process-info', () => cdp.send('SystemInfo.getProcessInfo'))
const receipt = { channel: process.env.IZ_OM_BROWSER_CHANNEL, executable: process.env.IZ_OM_BROWSER_EXECUTABLE,
  version: browser.version(), pids: info.processInfo.map(item => ({ pid: item.id, type: item.type })),
  baseUrl: process.env.IZ_OM_BASE_URL, role: process.env.IZ_OM_INTERACTIVE_ROLE,
  boundedSeconds: Number(process.env.IZ_OM_INTERACTIVE_SECONDS), ownedContext: true,
  browserClosed: false, handsOnActionsClaimed: false }
let witness
try {
  await observePhase('request-routing', () => context.route('**/*', route => new URL(route.request().url()).origin === process.env.IZ_OM_BASE_URL
    ? route.continue() : route.abort('blockedbyclient')))
  const page = await observePhase('page-create', () => context.newPage())
  await observePhase('login', () => login(page, process.env.IZ_OM_INTERACTIVE_ROLE))
  receipt.windowTitle = await observePhase('page-title', () => page.title())
  await observePhase('ready-capture', () => capture(page, 'interactive-ready.png'))
  witness = await observePhase('witness-start', () => startNativeWitness(page, {
    baseUrl: process.env.IZ_OM_BASE_URL, evidenceDir: process.env.IZ_OM_EVIDENCE_DIR,
  }, writeEvidence))
  receipt.startedAt = new Date().toISOString()
  await observePhase('ready-evidence', () => writeEvidence('interactive-ready.json', receipt))
  await observePhase('interactive-wait', () => delay(receipt.boundedSeconds * 1_000))
  await observePhase('finished-capture', () => capture(page, 'interactive-finished.png'))
} finally {
  try { await observePhase('witness-finish', () => witness?.finish()) } finally {
    await observePhase('cdp-detach', () => cdp.detach())
    await observePhase('context-close', () => context.close())
    await observePhase('browser-close', () => browser.close())
    receipt.browserClosed = !browser.isConnected()
    receipt.completedAt = new Date().toISOString()
    await observePhase('teardown-evidence', () => writeEvidence('interactive-teardown.json', receipt))
  }
}
