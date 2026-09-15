import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { cpSync, mkdtempSync, mkdirSync, readFileSync, renameSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterEach, test } from 'node:test'
import { loadMaintenanceAttachment } from './maintenanceAttachment.mjs'

const sandboxes = []
afterEach(() => {
  for (const sandbox of sandboxes.splice(0)) rmSync(sandbox, { recursive: true, force: true })
})

function sha256(target) {
  return createHash('sha256').update(readFileSync(target)).digest('hex')
}

function json(target, value) {
  writeFileSync(target, JSON.stringify(value), 'utf8')
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), 'iz-maintenance-attachment-'))
  sandboxes.push(root)
  const localAppData = path.join(root, 'LocalAppData')
  const stateRoot = path.join(localAppData, 'IZ Clinical Notes Analyzer Maintenance', 'state')
  const installRoot = path.join(localAppData, 'Programs', 'IZ Clinical Notes Analyzer')
  const executable = path.join(installRoot, 'runtime', 'IZClinicalNotesAnalyzer.exe')
  const buildRoot = path.join(root, 'build')
  const packageRoot = path.join(buildRoot, 'candidate-package')
  const publicRoot = path.join(root, 'public', 'cmd-123456789abc')
  const packageExecutable = path.join(packageRoot, 'app', 'runtime', 'IZClinicalNotesAnalyzer.exe')
  for (const directory of [stateRoot, path.dirname(executable), path.dirname(packageExecutable), publicRoot]) mkdirSync(directory, { recursive: true })
  cpSync(process.execPath, executable)
  cpSync(process.execPath, packageExecutable)
  const packageMarker = path.join(packageRoot, 'app', 'backend', 'app', '__init__.py')
  mkdirSync(path.dirname(packageMarker), { recursive: true })
  writeFileSync(packageMarker, '')
  const executableHash = sha256(executable)
  const candidate = path.join(buildRoot, 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.zip')
  writeFileSync(candidate, 'synthetic-candidate-bytes', 'utf8')
  const candidateHash = sha256(candidate)
  const manifest = path.join(packageRoot, 'release-manifest.json')
  const sourceRevision = 'a'.repeat(40)
  const packageRecords = [{
    path: 'app/backend/app/__init__.py',
    length: readFileSync(packageMarker).length,
    sha256: sha256(packageMarker),
  }, {
    path: 'app/runtime/IZClinicalNotesAnalyzer.exe',
    length: readFileSync(packageExecutable).length,
    sha256: sha256(packageExecutable),
  }]
  const payloadIdentity = createHash('sha256')
    .update(packageRecords.map((record) => `${record.path}\t${record.length}\t${record.sha256}\n`).join(''), 'utf8').digest('hex')
  json(manifest, {
    schema: 'iz-cna-release-manifest-v1', product_id: 'r3.iz-clinical-notes-analyzer.desktop',
    version: '2.0.0-beta.4', build: '2026.09.14.1', installer_revision: 1,
    release_channel: 'beta-local-desktop-v2',
    compatibility: {
      source_version_minimum: '2.0.0-beta.3', source_version_maximum: '2.0.0-beta.4',
      source_build_minimum: '2026.09.03.1', source_build_maximum: '2026.09.14.1',
      source_schema_minimum: 12, source_schema_maximum: 12, target_schema: 12,
    },
    payload_identity: payloadIdentity, files: packageRecords,
  })
  const gateNames = [
    'backend_tests', 'frontend_tests', 'frontend_build', 'repository_safety',
    'directory_safety', 'zip_safety', 'frozen_bundle_inspection',
  ]
  const gates = gateNames.map((name) => {
    const evidence = `gate-${name}.json`
    json(path.join(buildRoot, evidence), { status: 'passed' })
    return { name, status: 'passed', command: `synthetic ${name}`, exit_code: 0, evidence }
  })
  const buildReceipt = {
    schema: 'iz-cna-build-receipt-v1', product_id: 'r3.iz-clinical-notes-analyzer.desktop',
    version: '2.0.0-beta.4', build: '2026.09.14.1', installer_revision: 1,
    source_revision: sourceRevision, package_directory: packageRoot, zip_path: candidate,
    zip_length: Buffer.byteLength('synthetic-candidate-bytes'), zip_sha256: candidateHash,
    manifest_sha256: sha256(manifest), payload_identity: payloadIdentity, gates,
    created_utc: new Date().toISOString(),
  }
  const buildReceiptPath = candidate.replace(/\.zip$/i, '.build-receipt.json')
  json(buildReceiptPath, buildReceipt)
  const runtimeIdentityPath = path.join(stateRoot, 'runtime-identity.json')
  const installReceiptPath = path.join(stateRoot, 'install-receipt.json')
  const committedTransaction = 'abcdef1234567890abcdef1234567890'
  const identity = {
    schema: 'iz-cna-runtime-identity-v1', product_id: 'r3.iz-clinical-notes-analyzer.desktop',
    owner_sid: 'S-1-5-21-1000', scope_id: 'c'.repeat(64), data_identity: 'd'.repeat(64),
    instance_id: '1234567890abcdef1234567890abcdef', transaction_id: committedTransaction, process_id: 4242,
    process_started_utc: new Date().toISOString(), executable_path: executable,
    executable_sha256: executableHash, version: '2.0.0-beta.4', build: '2026.09.14.1',
    installer_revision: 1, port: 18765, pipe_name: `iz-cna-runtime-v1-${'c'.repeat(32)}`,
    gate: 'open', draining: false, created_utc: new Date().toISOString(),
  }
  const installReceipt = {
    schema: 'iz-cna-install-receipt-v1', product_id: identity.product_id, owner_sid: identity.owner_sid,
    scope_id: identity.scope_id, install_identity: 'e'.repeat(64), data_identity: identity.data_identity,
    version: identity.version, build: identity.build, installer_revision: identity.installer_revision,
    payload_identity: payloadIdentity,
    owned_files: [{ path: 'runtime/IZClinicalNotesAnalyzer.exe', length: readFileSync(executable).length, sha256: executableHash }],
    owned_shortcuts: [], last_committed_transaction: committedTransaction,
    recovery_format: 'IZCNABK2', written_utc: new Date().toISOString(),
  }
  json(runtimeIdentityPath, identity)
  json(installReceiptPath, installReceipt)
  const attachmentPath = path.join(root, 'attachment.json')
  const attachment = {
    schema: 'iz-cna-maintenance-browser-attachment-v1', qualification_mode: 'release',
    run_id: 'cmd-123456789abc', case_id: 'A01', tier: 'Package',
    base_url: 'http://127.0.0.1:18765', runtime_identity_path: runtimeIdentityPath,
    install_receipt_path: installReceiptPath, candidate_zip_path: candidate,
    candidate_zip_sha256: candidateHash, candidate_package_path: packageRoot,
    candidate_manifest_sha256: sha256(manifest), candidate_payload_identity: payloadIdentity,
    candidate_authority_path: buildReceiptPath, expected_source_revision: sourceRevision,
    public_evidence_root: publicRoot, evidence_path: path.join(publicRoot, 'browser', 'maintenance-browser.json'),
  }
  json(attachmentPath, attachment)
  return {
    root, attachmentPath, localAppData, attachment, identity, installReceipt, buildReceipt,
    runtimeIdentityPath, installReceiptPath, buildReceiptPath, candidate,
    environment: { IZ_CNA_MAINTENANCE_ATTACHMENT: attachmentPath, LOCALAPPDATA: localAppData },
  }
}

test('accepts an exact candidate, runtime identity, install receipt and evidence boundary', () => {
  const input = fixture()
  const result = loadMaintenanceAttachment(input.environment)
  assert.equal(result.runtime.executable_sha256, input.identity.executable_sha256)
  assert.equal(result.attachment.candidate_zip_sha256, sha256(input.candidate))
  assert.equal(result.evidencePath, input.attachment.evidence_path)
})

test('accepts a marked validation-only artifact without treating it as a release build', () => {
  const input = fixture()
  const packageName = 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4-build-2026.09.14.1-installer-r1.NOT-RELEASE-READY'
  const validationPackage = path.join(path.dirname(input.buildReceipt.package_directory), packageName)
  const validationCandidate = path.join(path.dirname(input.candidate), `${packageName}.zip`)
  renameSync(input.buildReceipt.package_directory, validationPackage)
  renameSync(input.candidate, validationCandidate)
  unlinkSync(input.buildReceiptPath)
  const candidateHash = sha256(validationCandidate)
  const summaryPath = path.join(path.dirname(validationPackage), 'validation-summary.NOT-RELEASE-READY.json')
  json(summaryPath, {
    schema: 'iz-cna-build-gate-evidence-v1', product_id: input.buildReceipt.product_id,
    version: input.buildReceipt.version, build: input.buildReceipt.build,
    installer_revision: input.buildReceipt.installer_revision, source_revision: input.buildReceipt.source_revision,
    release_ready: false, preflight: {}, backend_tests: {}, frontend_tests: {}, frontend_build: {},
    repository_safety: {}, directory_safety: { payload_identity: input.buildReceipt.payload_identity },
    zip_safety: { length: readFileSync(validationCandidate).length, sha256: candidateHash },
    frozen_bundle_inspection: {}, preserved_archives: {},
  })
  Object.assign(input.attachment, {
    qualification_mode: 'validation_only', candidate_zip_path: validationCandidate,
    candidate_zip_sha256: candidateHash, candidate_package_path: validationPackage,
    candidate_manifest_sha256: sha256(path.join(validationPackage, 'release-manifest.json')),
    candidate_authority_path: summaryPath,
  })
  json(input.attachmentPath, input.attachment)
  const result = loadMaintenanceAttachment(input.environment)
  assert.equal(result.attachment.qualification_mode, 'validation_only')
  assert.equal(result.build.payload_identity, input.buildReceipt.payload_identity)
})

test('rejects an arbitrary loopback service before creating browser evidence', () => {
  const input = fixture()
  input.attachment.base_url = 'http://127.0.0.1:18766'
  json(input.attachmentPath, input.attachment)
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'BASE_URL_IDENTITY_MISMATCH' })
})

test('rejects runtime executable hash drift', () => {
  const input = fixture()
  input.identity.executable_sha256 = 'f'.repeat(64)
  json(input.runtimeIdentityPath, input.identity)
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'RUNTIME_EXECUTABLE_HASH_MISMATCH' })
})

test('rejects mismatched data identity between runtime and install receipt', () => {
  const input = fixture()
  input.installReceipt.data_identity = 'f'.repeat(64)
  json(input.installReceiptPath, input.installReceipt)
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'INSTALL_RECEIPT_IDENTITY_MISMATCH' })
})

test('rejects a runtime transaction not bound to the committed install receipt', () => {
  const input = fixture()
  input.identity.transaction_id = 'f'.repeat(32)
  json(input.runtimeIdentityPath, input.identity)
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'INSTALL_RECEIPT_IDENTITY_MISMATCH' })
})

test('rejects candidate mutation after its frozen build receipt', () => {
  const input = fixture()
  writeFileSync(input.candidate, 'mutated-candidate', 'utf8')
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'CANDIDATE_HASH_MISMATCH' })
})

test('rejects runtime identity outside the configured local app-data state path', () => {
  const input = fixture()
  const outside = path.join(input.root, 'outside-runtime.json')
  json(outside, input.identity)
  input.attachment.runtime_identity_path = outside
  json(input.attachmentPath, input.attachment)
  assert.throws(() => loadMaintenanceAttachment(input.environment), { code: 'RUNTIME_IDENTITY_LOCATION_INVALID' })
})
