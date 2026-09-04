import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { after, test } from 'node:test'
import { validateTarget } from './guards.mjs'

const sandbox = mkdtempSync(path.join(tmpdir(), 'iz-office-guard-test-'))
const ownedRoot = path.join(sandbox, 'owned')
mkdirSync(ownedRoot)
const executable = process.execPath
const input = {
  ownedRoot,
  dataDir: path.join(ownedRoot, 'run-12345678-1234-1234-1234-123456789abc'),
  baseUrl: '',
  runtimeMode: 'checkout',
  preparedExecutable: '',
  pythonExecutable: executable,
  browserExecutable: executable,
}
after(() => rmSync(sandbox, { recursive: true }))

test('accepts a fresh direct child when the runtime executables exist', () => {
  // Given: a unique, not-yet-created synthetic runtime target.
  // When: the read-only target validation runs.
  const result = validateTarget(input)
  // Then: it returns the canonical target without mutation.
  assert.equal(result.dataDir, input.dataDir)
  assert.equal(existsSync(result.dataDir), false)
})

for (const baseUrl of ['https://example.org', 'http://127.0.0.1.evil.test:8765', 'file:///C:/data', 'http://user:pass@127.0.0.1:8765']) {
  test('rejects unsafe URL before any mutation: ' + baseUrl.replace('user:pass@', ''), () => {
    // Given: an external, credential-bearing, or unsupported URL.
    // When/Then: validation refuses the target and creates no data directory.
    assert.throws(() => validateTarget({ ...input, baseUrl }), { code: 'UNSAFE_URL' })
    assert.equal(existsSync(input.dataDir), false)
  })
}

test('rejects even loopback attachment to an existing runtime', () => {
  // Given: a loopback URL not allocated by this runner.
  // When/Then: the harness refuses to attach to another service.
  assert.throws(() => validateTarget({ ...input, baseUrl: 'http://127.0.0.1:8765' }), { code: 'EXISTING_RUNTIME_URL' })
})

for (const dataDir of [ownedRoot, sandbox, path.join(sandbox, 'outside'), path.join(ownedRoot, '..', 'escape')]) {
  test('rejects an unowned or broad runtime target: ' + path.basename(dataDir), () => {
    // Given: a target outside the unique-run naming and direct-parent boundary.
    // When/Then: it fails before filesystem mutation.
    assert.throws(() => validateTarget({ ...input, dataDir }), { code: 'UNOWNED_DATA_PATH' })
  })
}

test('rejects a pre-existing data directory even with a valid run name', () => {
  // Given: a previously created runtime directory.
  const dataDir = path.join(ownedRoot, 'run-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')
  mkdirSync(dataDir)
  // When/Then: validation refuses to reuse or remove it.
  assert.throws(() => validateTarget({ ...input, dataDir }), { code: 'EXISTING_DATA_PATH' })
  assert.equal(existsSync(dataDir), true)
})

test('rejects a missing prepared executable before any mutation', () => {
  // Given: prepared mode points to a missing binary.
  // When/Then: no seed directory or server can be created.
  assert.throws(() => validateTarget({ ...input, runtimeMode: 'prepared', preparedExecutable: path.join(sandbox, 'missing.exe') }), { code: 'MISSING_PREPARED_EXECUTABLE' })
  assert.equal(existsSync(input.dataDir), false)
})
