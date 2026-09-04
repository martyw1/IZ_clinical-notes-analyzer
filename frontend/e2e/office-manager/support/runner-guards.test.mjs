import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, existsSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, test } from 'node:test'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const sandbox = mkdtempSync(path.join(tmpdir(), 'iz-office-cli-guard-'))
const ownedRoot = path.join(process.env.LOCALAPPDATA, 'IZ-CNA-OfficeManager-Smoke')
after(() => rmSync(sandbox, { recursive: true }))
const runs = () => existsSync(ownedRoot) ? readdirSync(ownedRoot).sort() : []

for (const [name, extra, code] of [
  ['external-url', ['-BaseUrl', 'https://example.org'], 'UNSAFE_URL'],
  ['unowned-data-path', ['-LocalAppDataDir', sandbox], 'UNOWNED_DATA_PATH'],
  ['missing-prepared-executable', ['-RuntimeMode', 'prepared', '-PreparedExecutable', path.join(sandbox, 'missing.exe')], 'MISSING_PREPARED_EXECUTABLE'],
]) {
  test('actual PowerShell CLI rejects ' + name + ' before mutation', () => {
    // Given: a known existing sentinel directory and no evidence output directory.
    const before = runs()
    const evidence = path.join(sandbox, name)
    // When: the actual wrapper receives an unsafe target.
    const result = spawnSync('powershell.exe', ['-NoProfile', '-File', path.join(repo, 'scripts/test-office-manager-smoke.ps1'),
      '-Scenario', 'harness', '-Case', 'edge', '-BrowserChannel', 'chrome', '-EvidenceDir', evidence, ...extra],
    { cwd: repo, encoding: 'utf8', windowsHide: true, timeout: 20_000 })
    // Then: the precise refusal occurs without a process/data run or evidence write.
    assert.equal(result.status, 1)
    assert.match(result.stderr + result.stdout, new RegExp(code))
    assert.equal(existsSync(evidence), false)
    assert.deepEqual(runs(), before)
    assert.equal(existsSync(sandbox), true)
  })
}
