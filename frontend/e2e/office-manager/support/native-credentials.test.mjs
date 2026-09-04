import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, test } from 'node:test'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const sandbox = mkdtempSync(path.join(tmpdir(), 'iz-native-credential-guard-'))
const controllerPassword = `Qa1!${randomBytes(24).toString('hex')}`
const inherited = Object.fromEntries(Object.entries(process.env).filter(([key]) => !/^(IZ_OM_|IZ_CNA_)/i.test(key)))
const ownedRoot = path.join(process.env.LOCALAPPDATA, 'IZ-CNA-OfficeManager-Smoke')
const runs = () => existsSync(ownedRoot) ? readdirSync(ownedRoot).sort() : []
after(() => rmSync(sandbox, { recursive: true }))

const probeSource = `
  import { pathToFileURL } from 'node:url';
  const runner = await import(pathToFileURL(process.cwd() + '/frontend/e2e/office-manager/support/runner.mjs'));
  if (typeof runner.selectRunPassword !== 'function') {
    console.log(JSON.stringify({ selectorAvailable: false })); process.exit(0);
  }
  const options = { 'interactive-credentials-from-environment': process.env.PROBE_OPT_IN === '1',
    'interactive-seconds': process.env.PROBE_SECONDS };
  let report;
  try {
    const password = runner.selectRunPassword(options);
    report = { selectorAvailable: true, selectedInput: password === process.env.IZ_OM_INTERACTIVE_PASSWORD,
      syntheticShape: /^Qa1![0-9a-f]{48}$/.test(password),
      nextGeneratedDiffers: options['interactive-credentials-from-environment'] || runner.selectRunPassword(options) !== password };
    if (process.env.PROBE_CHILD === '1') {
      const env = runner.childEnvironment({ id: 'probe-only', port: 1, baseUrl: 'http://127.0.0.1:1',
        evidence: process.env.PROBE_EVIDENCE, target: { dataDir: process.env.PROBE_EVIDENCE, browserExecutable: '' }, password });
      report.reservedInputCleared = !Object.keys(env).some(key => key.toUpperCase() === 'IZ_OM_INTERACTIVE_PASSWORD');
      report.seedInputMatched = env.IZ_OM_PASSWORD === password && env.IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD === password;
      Object.assign(process.env, { IZ_OM_PASSWORD: env.IZ_OM_PASSWORD, IZ_OM_EVIDENCE_DIR: env.IZ_OM_EVIDENCE_DIR });
      delete process.env.IZ_OM_INTERACTIVE_PASSWORD;
      const { writeEvidence } = await import(pathToFileURL(process.cwd() + '/frontend/e2e/office-manager/support/fixtures.mjs'));
      try { writeEvidence('credential-must-not-exist.json', { value: password }); }
      catch (error) { report.existingRedactionRecognizedPassword = error.code === 'SECRET_IN_EVIDENCE_REFUSED'; }
    }
  } catch (error) { report = { selectorAvailable: true, failureCode: error.code, errorValueOmitted: true }; }
  console.log(JSON.stringify(report));
`

function probe(options = {}) {
  const env = { ...inherited, LOCALAPPDATA: '', PROBE_OPT_IN: options.optIn ? '1' : '0',
    PROBE_SECONDS: String(options.seconds ?? 0), PROBE_CHILD: options.child ? '1' : '0',
    PROBE_EVIDENCE: path.join(sandbox, 'never-created') };
  if (options.password !== undefined) env.IZ_OM_INTERACTIVE_PASSWORD = options.password
  // Empty LOCALAPPDATA also prevents runtime mutation if the pre-fix module runs on import.
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', probeSource], {
    cwd: repo, env, encoding: 'utf8', windowsHide: true, timeout: 15_000,
  })
  assert.ok(!(`${result.stdout}${result.stderr}`).includes(controllerPassword), 'Child output must omit the controller value')
  assert.equal(result.status, 0)
  const report = JSON.parse(result.stdout)
  assert.ok(report.selectorAvailable, 'The password selector must be available without starting the runner')
  return report
}

test('default generates fresh credentials and ignores inherited valid input', () => {
  // Given: a valid inherited controller value but no explicit opt-in.
  // When: the default password path is selected twice in a real child process.
  const report = probe({ password: controllerPassword })
  // Then: both generated values are fresh, synthetic, and independent of the input.
  assert.equal(report.selectedInput, false)
  assert.equal(report.syntheticShape, true)
  assert.equal(report.nextGeneratedDiffers, true)
})

test('default ignores malformed inherited input', () => {
  // Given: malformed inherited data and no opt-in.
  // When: the default path runs.
  const report = probe({ password: 'not-a-synthetic-value' })
  // Then: normal generation remains available.
  assert.equal(report.syntheticShape, true)
  assert.equal(report.selectedInput, false)
})

test('bounded opt-in hands the controller value to seed and existing secret guards in memory', t => {
  // Given: a fresh value owned by this test controller and a bounded opt-in.
  // When: a real Node child selects it and constructs the existing downstream environment.
  const report = probe({ password: controllerPassword, optIn: true, seconds: 1, child: true })
  // Then: only the required seed variables retain it, and evidence redaction refuses it.
  assert.equal(report.selectedInput, true)
  assert.equal(report.seedInputMatched, true)
  assert.equal(report.reservedInputCleared, true)
  assert.equal(report.existingRedactionRecognizedPassword, true)
  assert.equal(existsSync(path.join(sandbox, 'never-created')), false)
  t.diagnostic(JSON.stringify({ controllerValueMatched: true, requiredChildVariablesMatched: true,
    reservedInputCleared: true, redactionRefusedValue: true, credentialFileCreated: false }))
})

for (const seconds of [0, -1, 901, 1.5, 'not-seconds']) {
  test(`opt-in rejects unbounded duration ${seconds} without exposing input`, () => {
    // Given: a valid controller value with an invalid interactive duration.
    // When: the password boundary is evaluated.
    const report = probe({ password: controllerPassword, optIn: true, seconds })
    // Then: only the bounded-session refusal code is returned.
    assert.equal(report.failureCode, 'INTERACTIVE_CREDENTIALS_REQUIRE_BOUND')
  })
}

for (const [name, password, code] of [
  ['missing', undefined, 'INTERACTIVE_CREDENTIALS_MISSING'],
  ['empty', '', 'INTERACTIVE_CREDENTIALS_MISSING'],
  ['wrong-prefix', `Bad!${randomBytes(24).toString('hex')}`, 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['short', `Qa1!${randomBytes(23).toString('hex')}`, 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['long', `Qa1!${randomBytes(25).toString('hex')}`, 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['non-hex', `Qa1!${'x'.repeat(48)}`, 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['trailing-newline', `${controllerPassword}\n`, 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['trailing-crlf', `${controllerPassword}\r\n`, 'INTERACTIVE_CREDENTIALS_INVALID'],
]) {
  test(`bounded opt-in rejects ${name} input with a code-only error`, () => {
    // Given: a bounded opt-in with invalid environment input.
    // When: the boundary parses that input.
    const report = probe({ password, optIn: true, seconds: 900 })
    // Then: a fixed safe error code is emitted, never the supplied value.
    assert.equal(report.failureCode, code)
    assert.equal(report.errorValueOmitted, true)
  })
}

for (const [name, extra, password, code] of [
  ['no-bound', ['-InteractiveCredentialsFromEnvironment'], controllerPassword, 'INTERACTIVE_CREDENTIALS_REQUIRE_BOUND'],
  ['missing', ['-InteractiveCredentialsFromEnvironment', '-InteractiveSeconds', '1'], undefined, 'INTERACTIVE_CREDENTIALS_MISSING'],
  ['malformed', ['-InteractiveCredentialsFromEnvironment', '-InteractiveSeconds', '1'], 'not-a-synthetic-value', 'INTERACTIVE_CREDENTIALS_INVALID'],
  ['valid-bound', ['-InteractiveCredentialsFromEnvironment', '-InteractiveSeconds', '1'], controllerPassword, 'UNSAFE_URL'],
  ['default-ignores-input', [], 'not-a-synthetic-value', 'UNSAFE_URL'],
]) {
  test(`actual PowerShell credential ${name} path refuses before runtime or evidence mutation`, () => {
    // Given: an external target that always stops the runner, plus this credential selection.
    const before = runs()
    const evidence = path.join(sandbox, name)
    const env = { ...inherited }
    if (password !== undefined) env.IZ_OM_INTERACTIVE_PASSWORD = password
    // When: the real wrapper parses the nonsecret switch and inherited input.
    const result = spawnSync('powershell.exe', ['-NoProfile', '-File', path.join(repo, 'scripts/test-office-manager-smoke.ps1'),
      '-Scenario', 'harness', '-Case', 'edge', '-BrowserChannel', 'chrome', '-EvidenceDir', evidence,
      '-BaseUrl', 'https://example.org', ...extra], { cwd: repo, env, encoding: 'utf8', windowsHide: true, timeout: 20_000 })
    // Then: only the expected fixed error reaches output and neither target is mutated.
    const output = result.stdout + result.stderr
    assert.ok(!output.includes(controllerPassword), 'CLI output must omit the controller value')
    assert.equal(result.status, 1)
    assert.ok(output.trim() === `Office-manager smoke refused: ${code}`, 'The CLI must report only the expected safe refusal')
    assert.equal(existsSync(evidence), false)
    assert.deepEqual(runs(), before)
  })
}
