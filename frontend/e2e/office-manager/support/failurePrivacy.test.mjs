import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { randomUUID, createHash } from 'node:crypto'
import { existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, writeFileSync, cpSync, rmSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { after, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { startOwned, stopOwned, waitOwned } from './processes.mjs'
import { assertPlainPath } from './guards.mjs'

const support = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(support, '../../../..')
const id = randomUUID()
const tempParent = realpathSync(tmpdir())
const sandbox = realpathSync(mkdtempSync(path.join(tempParent, 'iz-om-failure-privacy-')))
const evidence = path.join(repo, '.omo/evidence/office-manager-production-fixes', `failure-privacy-${id}`)
assertPlainPath(evidence)
mkdirSync(path.dirname(evidence), { recursive: true })
mkdirSync(evidence)
writeFileSync(path.join(sandbox, 'owner.json'), JSON.stringify({ id }))
const records = []
const sentinel = `OM_NONCREDENTIAL_${randomUUID()}`
const inherited = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
  /^(PATH|SystemRoot|WINDIR|TEMP|TMP|USERPROFILE|LOCALAPPDATA|APPDATA|ProgramFiles|ProgramFiles\(x86\)|ProgramW6432|COMSPEC|PATHEXT)$/i.test(key)))
const alive = pid => { try { process.kill(pid, 0); return true } catch (error) { return error.code !== 'ESRCH' } }
const readJson = filename => JSON.parse(readFileSync(filename, 'utf8'))
const environmentPath = name => Object.entries(inherited).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1]

function fileScan(directory, base = directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const filename = path.join(directory, entry.name)
    if (entry.isDirectory()) return fileScan(filename, base)
    const bytes = readFileSync(filename)
    return [{ path: path.relative(base, filename), bytes: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex'), sentinelPresent: bytes.includes(sentinel) }]
  })
}

after(() => {
  const allOwnedProcessesStopped = records.every(record => record.child.stopped && record.browserPidsStopped)
  const allOwnedBrowserProfilesRemoved = records.every(record => record.ownedBrowserProfileRemoved)
  const validOwner = path.dirname(sandbox) === tempParent && path.basename(sandbox).startsWith('iz-om-failure-privacy-')
    && readJson(path.join(sandbox, 'owner.json')).id === id
  if (allOwnedProcessesStopped && validOwner) rmSync(sandbox, { recursive: true })
  const receipt = { id, evidence, sandbox, allOwnedProcessesStopped, allOwnedBrowserProfilesRemoved, validOwner,
    ownedTemporaryDirectoryRemoved: !existsSync(sandbox), clinicalRuntimeStarted: false,
    actualCredentialsUsed: false, retainedOutput: true, records }
  writeFileSync(path.join(evidence, 'manifest.json'), JSON.stringify(receipt, null, 2))
  console.log(JSON.stringify({ evidence, runs: records.length, allOwnedProcessesStopped,
    ownedTemporaryDirectoryRemoved: receipt.ownedTemporaryDirectoryRemoved }))
  assert.equal(allOwnedProcessesStopped, true)
  assert.equal(allOwnedBrowserProfilesRemoved, true)
  assert.equal(receipt.ownedTemporaryDirectoryRemoved, true)
})

async function runProbe(kind, mode, browser = '') {
  const name = `${mode}-${kind}${browser ? `-${browser}` : ''}`
  const root = path.join(sandbox, name)
  mkdirSync(root)
  let browserExecutable = ''
  if (browser) {
    const relative = browser === 'msedge' ? 'Microsoft/Edge/Application/msedge.exe' : 'Google/Chrome/Application/chrome.exe'
    browserExecutable = [environmentPath('ProgramFiles(x86)'), environmentPath('ProgramFiles'), environmentPath('LOCALAPPDATA')]
      .filter(Boolean).map(parent => path.join(parent, relative)).find(filename => existsSync(filename)) ?? ''
    assert.ok(browserExecutable, 'The actual installed browser executable is required')
  }
  const env = { ...inherited, IZ_OM_PRIVACY_ROOT: root, IZ_OM_PRIVACY_CASE: kind, IZ_OM_PRIVACY_MODE: mode,
    IZ_OM_PRIVACY_SENTINEL: sentinel, IZ_OM_PRIVACY_BROWSER: browser, IZ_OM_PRIVACY_BROWSER_EXECUTABLE: browserExecutable }
  if (mode === 'guarded') env.PLAYWRIGHT_NO_COPY_PROMPT = '1'
  const owned = startOwned(process.execPath, [path.join(repo, 'frontend/node_modules/@playwright/test/cli.js'),
    'test', '--config', path.join(support, 'failure-privacy-probes/config.mjs')], { cwd: repo, env })
  let stdout = '', stderr = ''
  owned.child.stdout.on('data', value => { stdout += value })
  owned.child.stderr.on('data', value => { stderr += value })
  let exitCode
  try { exitCode = await waitOwned(owned, 45_000) } finally { await stopOwned(owned) }
  const reportPath = path.join(root, 'probe-result.json')
  const report = existsSync(reportPath) ? readJson(reportPath) : null
  const browserRecord = existsSync(path.join(root, 'browser.json')) ? readJson(path.join(root, 'browser.json')) : null
  const record = { name, mode, kind, browser, exitCode, child: owned.record,
    stdoutSentinelPresent: stdout.includes(sentinel), stderrSentinelPresent: stderr.includes(sentinel),
    report, browserRecord, browserPidsStopped: browserRecord ? browserRecord.pids.every(pid => !alive(pid)) : !browser,
    ownedBrowserProfileRemoved: browser ? typeof browserRecord?.ownedProfileDirectory === 'string'
      && !existsSync(browserRecord.ownedProfileDirectory) : true,
    files: fileScan(root) }
  records.push(record)
  cpSync(root, path.join(evidence, name), { recursive: true, errorOnExist: true, force: false })
  writeFileSync(path.join(evidence, `${name}.json`), JSON.stringify(record, null, 2))
  assert.ok(report, 'The real Playwright child must produce a scalar failure report')
  assert.equal(report.discovered, 1)
  assert.equal(report.tests.length, 1)
  assert.equal(report.unhandledErrors, 0)
  assert.deepEqual(report.capturePolicy, { preserveOutput: 'always', trace: 'off', video: 'off', screenshot: 'off' })
  assert.equal(record.browserPidsStopped, true)
  assert.equal(record.ownedBrowserProfileRemoved, true)
  assert.equal(record.stdoutSentinelPresent, false)
  assert.equal(record.stderrSentinelPresent, false)
  assert.ok(record.files.every(file => !/\.(zip|png|webm)$/.test(file.path)), 'Automatic captures must remain disabled')
  if (kind === 'api') assert.equal(readJson(path.join(root, 'api-server.json')).serverClosed, true)
  return record
}

test('current application specs do not claim unsupported all-hook guard coverage', () => {
  const directories = [path.join(repo, 'frontend/e2e'), path.join(repo, 'frontend/e2e/office-manager')]
  const specs = directories.flatMap(directory => readdirSync(directory).filter(name => name.endsWith('.spec.mjs'))
    .map(name => path.join(directory, name)))
  const inventory = specs.map(filename => {
    const content = readFileSync(filename)
    return { path: path.relative(repo, filename), sha256: createHash('sha256').update(content).digest('hex'),
      unsupportedAllHooks: /\btest\.(beforeAll|afterAll)\s*\(/.test(content.toString()) }
  })
  writeFileSync(path.join(evidence, 'scenario-lifecycle-inventory.json'), JSON.stringify(inventory, null, 2))
  assert.ok(specs.length >= 8)
  assert.ok(inventory.every(item => !item.unsupportedAllHooks))
})

test('privacy sanitizer keeps public error identity, count and cyclic cause topology', async () => {
  const { sanitizeFailureErrors } = await import('./failurePrivacy.mjs')
  const cause = { message: sentinel, stack: sentinel, value: sentinel, errorContext: sentinel }
  cause.cause = cause
  const error = { message: sentinel, stack: sentinel, cause }
  const errors = [error, { value: sentinel }]
  sanitizeFailureErrors(errors)
  assert.equal(errors.length, 2)
  assert.equal(errors[0], error)
  assert.equal(error.cause, cause)
  assert.equal(cause.cause, cause)
  for (const entry of [error, cause, errors[1]]) {
    assert.equal(entry.message, 'FAILURE_DETAILS_REDACTED')
    assert.equal(entry.stack, undefined)
    assert.equal(entry.errorContext, 'FAILURE_DETAILS_REDACTED')
    assert.ok(entry.value === undefined || entry.value === 'FAILURE_DETAILS_REDACTED')
  }
})

test('privacy child environment strips capture overrides without weakening the native credential bridge', () => {
  const source = `
    const overrides = { DEBUG: 'pw:api', DEBUG_FILE: 'not-an-output', PWDEBUG: '1', PW_TEST_TRACE: '1',
      PLAYWRIGHT_JSON_OUTPUT_FILE: 'not-an-output', PLAYWRIGHT_NO_COPY_PROMPT: '',
      NODE_OPTIONS: '--inspect=0', NODE_DEBUG: 'http', NODE_V8_COVERAGE: 'not-an-output', NODE_REDIRECT_WARNINGS: 'not-an-output',
      CHROME_LOG_FILE: 'not-an-output', EDGE_LOG_FILE: 'not-an-output',
      IZ_OM_INTERACTIVE_PASSWORD: 'NONCREDENTIAL_INPUT' };
    Object.assign(process.env, overrides);
    const { childEnvironment, failureArtifactPrivacyPolicy } = await import('./frontend/e2e/office-manager/support/runner.mjs');
    const env = childEnvironment({ id: 'privacy-environment-probe', password: 'NONCREDENTIAL_SELECTED',
      baseUrl: 'http://127.0.0.1:1', port: 1, evidence: 'not-created', target: { dataDir: 'not-created', browserExecutable: '' } });
    console.log(JSON.stringify({ overridesRemoved: Object.keys(overrides).filter(key => key !== 'PLAYWRIGHT_NO_COPY_PROMPT').every(key => !(key in env)),
      snapshotDisabled: env.PLAYWRIGHT_NO_COPY_PROMPT === '1',
      selectedValuePreserved: env.IZ_OM_PASSWORD === 'NONCREDENTIAL_SELECTED' && env.IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD === 'NONCREDENTIAL_SELECTED',
      pathPreserved: env.PATH === process.env.PATH, policy: failureArtifactPrivacyPolicy }));
  `
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', source], {
    cwd: repo, env: inherited, encoding: 'utf8', windowsHide: true, timeout: 15_000,
  })
  assert.equal(result.status, 0)
  const report = JSON.parse(result.stdout)
  assert.equal(report.overridesRemoved, true)
  assert.equal(report.snapshotDisabled, true)
  assert.equal(report.selectedValuePreserved, true)
  assert.equal(report.pathPreserved, true)
  assert.equal(report.policy.universalCredentialPersistenceClaim, false)
  assert.equal(report.policy.artifactScanPerformed, false)
  assert.ok(report.policy.excludedLifecycle.includes('beforeAll'))
  assert.ok(report.policy.excludedLifecycle.includes('afterAll'))
  writeFileSync(path.join(evidence, 'environment-policy.json'), JSON.stringify(report, null, 2))
})

for (const kind of ['body', 'public-context', 'thrown-value', 'beforeEach', 'afterEach', 'api', 'dependent-setup', 'dependent-teardown', 'timeout', 'pure-timeout']) {
  test(`privacy matrix preserves failed ${kind} semantics while sanitizing retained artifacts`, async () => {
    const red = await runProbe(kind, 'baseline')
    const green = await runProbe(kind, 'guarded')
    assert.equal(red.exitCode, 1)
    assert.equal(green.exitCode, 1)
    if (!['public-context', 'pure-timeout'].includes(kind)) assert.equal(red.report.tests[0].errorsContainSentinel, true)
    assert.equal(green.report.tests[0].errorsContainSentinel, false)
    assert.equal(green.report.tests[0].errorCount, red.report.tests[0].errorCount)
    assert.equal(green.report.tests[0].status, red.report.tests[0].status)
    assert.equal(green.report.tests[0].expectedStatus, 'passed')
    assert.ok(red.report.tests[0].errorCount > 0)
    assert.equal(red.report.tests[0].publicErrorDetailsSanitized, false)
    assert.equal(green.report.tests[0].publicErrorDetailsSanitized, true)
    if (kind === 'pure-timeout') assert.equal(green.report.tests[0].status, 'timedOut')
    assert.equal(green.files.some(file => file.sentinelPresent), false)
    assert.equal(green.report.observations.some(file => file.sentinelPresent), false)
    if (!['thrown-value', 'pure-timeout'].includes(kind)) assert.ok(red.report.observations.some(file => file.sentinelPresent))
  })
}

test('privacy passing control retains a real zero-error pass', async () => {
  for (const mode of ['baseline', 'guarded']) {
    const result = await runProbe('pass', mode)
    assert.equal(result.exitCode, 0)
    assert.equal(result.report.tests[0].status, 'passed')
    assert.equal(result.report.tests[0].errorCount, 0)
    assert.equal(result.files.some(file => file.sentinelPresent), false)
  }
})

for (const kind of ['beforeAll', 'afterAll']) {
  test(`privacy boundary explicitly retains unsupported ${kind} failure`, async () => {
    const result = await runProbe(kind, 'guarded')
    assert.equal(result.exitCode, 1)
    assert.equal(result.report.tests[0].status, 'failed')
    assert.ok(result.report.tests[0].errorCount > 0)
    assert.equal(result.report.tests[0].errorsContainSentinel, true)
    assert.equal(result.report.tests[0].publicErrorDetailsSanitized, false)
    assert.ok(result.report.observations.some(file => file.sentinelPresent))
  })
}

for (const browser of ['msedge', 'chrome']) {
  for (const kind of ['locator', 'snapshot']) {
    test(`privacy installed ${browser} ${kind} probe preserves failure without capture leakage`, async () => {
      const red = await runProbe(kind, 'baseline', browser)
      const green = await runProbe(kind, 'guarded', browser)
      assert.equal(red.exitCode, 1)
      assert.equal(green.exitCode, 1)
      assert.equal(green.report.tests[0].status, 'failed')
      assert.equal(green.report.tests[0].errorCount, red.report.tests[0].errorCount)
      assert.equal(green.report.tests[0].errorsContainSentinel, false)
      assert.equal(red.report.tests[0].publicErrorDetailsSanitized, false)
      assert.equal(green.report.tests[0].publicErrorDetailsSanitized, true)
      assert.equal(green.files.some(file => file.sentinelPresent), false)
      assert.equal(green.report.observations.some(file => file.sentinelPresent), false)
      if (kind === 'snapshot') assert.ok(red.report.observations.some(file => file.sentinelPresent))
      assert.ok(green.browserRecord?.version)
    })
  }
}
