import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync, copyFileSync, rmSync, realpathSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'
import { randomBytes, randomUUID, createHash } from 'node:crypto'
import { HarnessError, assertPlainPath, validateTarget } from './guards.mjs'
import { allocatePort, startOwned, waitOwned, stopOwned, waitForRuntime, runtimeStopped } from './processes.mjs'

const supportDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(supportDir, '../../../..')
const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
const { values } = parseArgs({ args: isMain ? process.argv.slice(2) : [], options: {
  scenario: { type: 'string', default: 'harness' }, case: { type: 'string', default: 'all' },
  'browser-channel': { type: 'string', default: 'msedge' }, 'runtime-mode': { type: 'string', default: 'checkout' },
  'evidence-dir': { type: 'string', default: '.omo/evidence/office-manager-production-fixes' },
  'prepared-executable': { type: 'string', default: '' }, 'base-url': { type: 'string', default: '' },
  'local-app-data-dir': { type: 'string', default: '' }, 'interactive-seconds': { type: 'string', default: '0' },
  'interactive-role': { type: 'string', default: 'office_manager' },
  'interactive-credentials-from-environment': { type: 'boolean', default: false },
  headed: { type: 'boolean', default: false },
} })

export function selectRunPassword(options) {
  if (!options['interactive-credentials-from-environment']) return `Qa1!${randomBytes(24).toString('hex')}`
  const seconds = Number(options['interactive-seconds'])
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 900) throw new HarnessError('INTERACTIVE_CREDENTIALS_REQUIRE_BOUND')
  const suppliedPassword = process.env.IZ_OM_INTERACTIVE_PASSWORD
  if (!suppliedPassword) throw new HarnessError('INTERACTIVE_CREDENTIALS_MISSING')
  if (!/^Qa1![0-9a-f]{48}$/.test(suppliedPassword)) throw new HarnessError('INTERACTIVE_CREDENTIALS_INVALID')
  return suppliedPassword
}

function installedBrowser(channel) {
  const relative = channel === 'msedge' ? 'Microsoft/Edge/Application/msedge.exe' : 'Google/Chrome/Application/chrome.exe'
  return [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA]
    .filter(Boolean).map(root => path.join(root, relative)).find(candidate => existsSync(candidate)) ?? ''
}

export function childEnvironment(run) {
  const env = { ...process.env }
  for (const key of Object.keys(env)) {
    if (/^(IZ_CNA_|IZ_OM_)/i.test(key) || ['SECRET_KEY', 'DATA_ENCRYPTION_KEY', 'LOCAL_SQLITE_DB_PATH', 'BOOTSTRAP_ADMIN_USERNAME', 'BOOTSTRAP_ADMIN_PASSWORD'].includes(key)) delete env[key]
  }
  return {
    ...env, PYTHONPATH: path.join(repoRoot, 'backend'), PYTHONUNBUFFERED: '1', ENVIRONMENT: 'local-client',
    IZ_CNA_LOCAL_APP_DATA_DIR: run.target.dataDir, IZ_CNA_LOCAL_SQLITE_DB_PATH: 'clinical-notes-analyzer-v2.sqlite3',
    IZ_CNA_SECRET_KEY: randomBytes(32).toString('hex'), IZ_CNA_DATA_ENCRYPTION_KEY: randomBytes(32).toString('hex'),
    IZ_CNA_BOOTSTRAP_ADMIN_USERNAME: 'smoke_admin', IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD: run.password,
    ALLOWED_HOSTS: '127.0.0.1,localhost', FRONTEND_ORIGINS: run.baseUrl, IZ_CNA_PORT: String(run.port),
    IZ_OM_PASSWORD: run.password, IZ_OM_RUN_ID: run.id, IZ_OM_BASE_URL: run.baseUrl,
    IZ_OM_EVIDENCE_DIR: run.evidence, IZ_OM_OUTPUT_DIR: path.join(run.target.dataDir, 'playwright-output'),
    IZ_OM_FIXTURE_CONTRACT: path.join(run.evidence, 'fixture-contract.json'),
    IZ_OM_SCENARIO: values.scenario, IZ_OM_CASE: values.case, IZ_OM_BROWSER_CHANNEL: values['browser-channel'],
    IZ_OM_BROWSER_EXECUTABLE: run.target.browserExecutable, IZ_OM_HEADED: values.headed ? '1' : '0',
    IZ_OM_INTERACTIVE_SECONDS: values['interactive-seconds'], IZ_OM_REPO_ROOT: repoRoot,
    IZ_OM_INTERACTIVE_ROLE: values['interactive-role'],
  }
}

async function runSmoke() {
  const id = randomUUID()
  const password = selectRunPassword(values)
  if (!process.env.LOCALAPPDATA) throw new HarnessError('OS_LOCAL_APP_DATA_UNAVAILABLE')
  const ownedRoot = path.join(process.env.LOCALAPPDATA, 'IZ-CNA-OfficeManager-Smoke')
  const target = validateTarget({
    ownedRoot, dataDir: values['local-app-data-dir'] || path.join(ownedRoot, `run-${id}`),
    baseUrl: values['base-url'], runtimeMode: values['runtime-mode'], preparedExecutable: values['prepared-executable'],
    pythonExecutable: path.join(repoRoot, 'backend/.venv/Scripts/python.exe'),
    browserExecutable: installedBrowser(values['browser-channel']),
  })
  if (!['msedge', 'chrome'].includes(values['browser-channel']) || !['happy', 'edge', 'all'].includes(values.case)
    || !['checkout', 'prepared'].includes(values['runtime-mode']) || !/^[a-z0-9-]+$/.test(values.scenario)) throw new HarnessError('INVALID_SELECTION')
  const interactiveSeconds = Number(values['interactive-seconds'])
  if (!Number.isInteger(interactiveSeconds) || interactiveSeconds < 0 || interactiveSeconds > 900) throw new HarnessError('INVALID_INTERACTIVE_BOUND')
  if (!['admin', 'office_manager', 'counselor', 'viewer'].includes(values['interactive-role'])) throw new HarnessError('INVALID_INTERACTIVE_ROLE')
  const specs = readdirSync(path.dirname(supportDir)).filter(name => name.endsWith('.spec.mjs'))
  if (values.scenario !== 'all' && !specs.includes(`${values.scenario}.spec.mjs`)) throw new HarnessError('SCENARIO_NOT_FOUND')
  const playwrightCli = path.join(repoRoot, 'frontend/node_modules/@playwright/test/cli.js')
  if (!existsSync(playwrightCli)) throw new HarnessError('MISSING_INSTALLED_PLAYWRIGHT')
  const frontendIndex = path.join(repoRoot, 'frontend/dist/index.html')
  if (values['runtime-mode'] === 'checkout' && !existsSync(frontendIndex)) throw new HarnessError('FRONTEND_BUILD_MISSING')
  const evidenceRoot = path.resolve(values['evidence-dir'])
  assertPlainPath(evidenceRoot)
  const evidence = path.join(evidenceRoot, `${values.scenario}-${values.case}-${values['browser-channel']}-${id}`)
  const port = await allocatePort()
  const run = { id, port, baseUrl: `http://127.0.0.1:${port}`, evidence, target, password }
  const env = childEnvironment(run)
  const processes = []
  const receipt = { runId: id, scenario: values.scenario, case: values.case, browserChannel: values['browser-channel'],
    runtimeMode: values['runtime-mode'], baseUrl: run.baseUrl, dataDir: target.dataDir,
    browserExecutable: target.browserExecutable, preparedExecutable: target.preparedExecutable,
    frontendIndexSha256: existsSync(frontendIndex) ? createHash('sha256').update(readFileSync(frontendIndex)).digest('hex') : null,
    startedAt: new Date().toISOString(), status: 'running', processes: [], safety: { traces: false, credentialsPersisted: false, syntheticOnly: true } }
  mkdirSync(evidence, { recursive: true })
  mkdirSync(ownedRoot, { recursive: true })
  mkdirSync(target.dataDir)
  receipt.physicalDataDir = realpathSync(target.dataDir)
  receipt.physicalEvidenceDir = realpathSync(evidence)
  writeFileSync(path.join(target.dataDir, 'owner.json'), JSON.stringify({ runId: id, dataDir: target.dataDir }))
  const persist = (name, payload) => writeFileSync(path.join(evidence, name), JSON.stringify(payload, null, 2))
  const start = (executable, args, childEnv = env) => {
    const owned = startOwned(executable, args, { cwd: repoRoot, env: childEnv })
    processes.push(owned)
    receipt.processes.push(owned.record)
    return owned
  }
  let runtime
  try {
    const seed = start(target.pythonExecutable, [path.join(supportDir, 'seed.py')])
    if (await waitOwned(seed, 60_000) !== 0) throw new HarnessError('SYNTHETIC_SEED_FAILED')
    copyFileSync(path.join(target.dataDir, 'fixture-contract.json'), path.join(evidence, 'fixture-contract.json'))
    receipt.pythonResolvedDataDir = JSON.parse(readFileSync(path.join(evidence, 'fixture-contract.json'), 'utf8')).physical_data_dir
    const discovery = start(process.execPath, [playwrightCli, 'test', '--config', 'frontend/playwright.office-manager.config.mjs', '--list'], { ...env, IZ_OM_DISCOVERY: '1' })
    if (await waitOwned(discovery, 60_000) !== 0) throw new HarnessError('SCENARIO_DISCOVERY_FAILED')
    const discoveryResult = JSON.parse(readFileSync(path.join(evidence, 'discovery.json'), 'utf8'))
    receipt.discoveredCount = discoveryResult.discoveredCount
    if (receipt.discoveredCount < 1) throw new HarnessError('ZERO_TESTS_DISCOVERED')
    const executable = values['runtime-mode'] === 'checkout' ? target.pythonExecutable : target.preparedExecutable
    const args = values['runtime-mode'] === 'checkout'
      ? ['-m', 'uvicorn', 'app.desktop_main:app', '--host', '127.0.0.1', '--port', String(port), '--no-access-log', '--log-level', 'error'] : []
    receipt.runtimeInvocation = { executable, args }
    runtime = start(executable, args)
    receipt.runtimeVersion = await waitForRuntime(run.baseUrl, runtime)
    persist('runtime-ready.json', receipt)
    console.log(`ISOLATED_RUNTIME_READY ${run.baseUrl} EVIDENCE ${evidence}`)
    const testRun = start(process.execPath, [playwrightCli, 'test', '--config', 'frontend/playwright.office-manager.config.mjs'])
    receipt.playwrightExitCode = await waitOwned(testRun, 20 * 60_000)
    const result = JSON.parse(readFileSync(path.join(evidence, 'playwright-results.json'), 'utf8'))
    receipt.executedCount = result.executedCount
    receipt.passedCount = result.passedCount
    if (receipt.playwrightExitCode !== 0 || result.status !== 'passed' || result.passedCount !== receipt.discoveredCount) throw new HarnessError('SCENARIO_FAILED')
    if (interactiveSeconds > 0) {
      const interactive = start(process.execPath, [path.join(supportDir, 'interactive.mjs')])
      console.log(`BOUNDED_HANDS_ON_READY ${run.baseUrl} WINDOW IZ Clinical Notes Analyzer LIMIT_SECONDS ${interactiveSeconds}`)
      if (await waitOwned(interactive, (interactiveSeconds + 30) * 1_000) !== 0) throw new HarnessError('INTERACTIVE_SESSION_FAILED')
    }
    receipt.status = 'passed'
  } catch (error) {
    receipt.status = 'failed'
    receipt.failureCode = error instanceof HarnessError ? error.code : 'UNEXPECTED_HARNESS_FAILURE'
    process.exitCode = 1
  } finally {
    for (const owned of [...processes].reverse()) {
      try { await stopOwned(owned) } catch { receipt.status = 'failed'; process.exitCode = 1 }
    }
    const stopped = runtime ? await runtimeStopped(run.baseUrl) : true
    const marker = JSON.parse(readFileSync(path.join(target.dataDir, 'owner.json'), 'utf8'))
    const ownPath = marker.runId === id && path.resolve(marker.dataDir) === target.dataDir && path.dirname(target.dataDir) === target.ownedRoot
    assertPlainPath(target.dataDir)
    if (ownPath && stopped && processes.every(owned => owned.record.stopped)) rmSync(target.dataDir, { recursive: true })
    else { receipt.status = 'failed'; process.exitCode = 1 }
    receipt.completedAt = new Date().toISOString()
    persist('teardown.json', { runId: id, runtimeStopped: stopped, allOwnedProcessesStopped: processes.every(owned => owned.record.stopped),
      ownedDataRemoved: ownPath && stopped && processes.every(owned => owned.record.stopped),
      dataDir: target.dataDir, processes: receipt.processes, personalProcessesTargeted: false })
    persist('task-1-harness.json', receipt)
    console.log(`SMOKE_${receipt.status.toUpperCase()} ${evidence}`)
  }
}

if (isMain) {
  try { await runSmoke() } catch (error) {
    console.error(error instanceof HarnessError ? error.message : 'Office-manager smoke refused: INVALID_RUNNER_INPUT')
    process.exitCode = 1
  }
}
