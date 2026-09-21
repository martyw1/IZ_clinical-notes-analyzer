import { createHash } from 'node:crypto'
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'

const PRODUCT_ID = 'r3.iz-clinical-notes-analyzer.desktop'
const SUPPORTED_RELEASE_VERSIONS = new Set(['2.0.0-beta.4', '1.0.0'])
const SHA256 = /^[a-f0-9]{64}$/
const SOURCE_REVISION = /^[a-f0-9]{40}$/
const BUILD_ID = /^20[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]+$/
const RUN_ID = /^cmd-[a-f0-9]{12}$/
const GUID_N = /^[a-f0-9]{32}$/
const BUILD_GATE_NAMES = [
  'backend_tests', 'frontend_tests', 'frontend_build', 'repository_safety',
  'directory_safety', 'zip_safety', 'frozen_bundle_inspection',
]
const BUILD_RECEIPT_KEYS = [
  'schema', 'product_id', 'version', 'build', 'installer_revision', 'source_revision',
  'package_directory', 'zip_path', 'zip_length', 'zip_sha256', 'manifest_sha256',
  'payload_identity', 'gates', 'created_utc',
]
const MANIFEST_KEYS = [
  'schema', 'product_id', 'version', 'build', 'installer_revision', 'release_channel',
  'compatibility', 'payload_identity', 'files',
]
const COMPATIBILITY_KEYS = [
  'source_version_minimum', 'source_version_maximum', 'source_build_minimum',
  'source_build_maximum', 'source_schema_minimum', 'source_schema_maximum', 'target_schema',
]
const VALIDATION_SUMMARY_KEYS = [
  'schema', 'product_id', 'version', 'build', 'installer_revision', 'source_revision',
  'release_ready', 'preflight', 'backend_tests', 'frontend_tests', 'frontend_build',
  'repository_safety', 'directory_safety', 'zip_safety', 'frozen_bundle_inspection',
  'preserved_archives',
]
const RUNTIME_KEYS = [
  'schema', 'product_id', 'owner_sid', 'scope_id', 'data_identity', 'instance_id',
  'transaction_id', 'process_id', 'process_started_utc', 'executable_path',
  'executable_sha256', 'version', 'build', 'installer_revision', 'port', 'pipe_name',
  'gate', 'draining', 'created_utc',
]
const INSTALL_RECEIPT_KEYS = [
  'schema', 'product_id', 'owner_sid', 'scope_id', 'install_identity', 'data_identity',
  'version', 'build', 'installer_revision', 'payload_identity', 'owned_files',
  'owned_shortcuts', 'last_committed_transaction', 'recovery_format', 'written_utc',
]
const ATTACHMENT_KEYS = [
  'schema', 'qualification_mode', 'run_id', 'case_id', 'tier', 'base_url', 'runtime_identity_path',
  'install_receipt_path', 'candidate_zip_path', 'candidate_zip_sha256',
  'candidate_package_path', 'candidate_manifest_sha256', 'candidate_payload_identity',
  'candidate_authority_path',
  'expected_source_revision', 'public_evidence_root', 'evidence_path',
]

export class MaintenanceAttachmentError extends Error {
  constructor(code) {
    super(`Maintenance browser attachment refused: ${code}`)
    this.name = 'MaintenanceAttachmentError'
    this.code = code
  }
}

function refuse(code) { throw new MaintenanceAttachmentError(code) }

function exactKeys(value, expected, code) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) refuse(code)
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) refuse(code)
}

function plainPath(target, { file = false, allowEmptyFile = false, directory = false, missingLeaf = false } = {}) {
  if (typeof target !== 'string' || !path.isAbsolute(target) || target.startsWith('\\\\')) refuse('ABSOLUTE_LOCAL_PATH_REQUIRED')
  let cursor = path.resolve(target)
  const targetExists = existsSync(cursor)
  if (!targetExists && !missingLeaf) refuse('ATTACHMENT_PATH_MISSING')
  while (!existsSync(cursor)) {
    const parent = path.dirname(cursor)
    if (parent === cursor) refuse('ATTACHMENT_PATH_MISSING')
    cursor = parent
  }
  while (true) {
    if (lstatSync(cursor).isSymbolicLink()) refuse('LINKED_ATTACHMENT_PATH')
    const parent = path.dirname(cursor)
    if (parent === cursor) break
    cursor = parent
  }
  if (file && (!targetExists || !statSync(target).isFile() || (!allowEmptyFile && statSync(target).size === 0))) refuse('ATTACHMENT_FILE_INVALID')
  if (directory && (!targetExists || !statSync(target).isDirectory())) refuse('ATTACHMENT_DIRECTORY_INVALID')
  return targetExists ? realpathSync(target) : path.resolve(target)
}

function readJsonFile(target, expectedKeys, code) {
  const file = plainPath(target, { file: true })
  let value
  try { value = JSON.parse(readFileSync(file, 'utf8').replace(/^\uFEFF/, '')) } catch { refuse(code) }
  exactKeys(value, expectedKeys, code)
  return Object.freeze({ file, value })
}

function sha256(target) {
  return createHash('sha256').update(readFileSync(target)).digest('hex')
}

function sha256Text(value) {
  return createHash('sha256').update(value, 'utf8').digest('hex')
}

function samePath(left, right) {
  return path.resolve(left).toLowerCase() === path.resolve(right).toLowerCase()
}

function requireHash(value, code) {
  if (typeof value !== 'string' || !SHA256.test(value)) refuse(code)
  return value
}

function validateBuildReceipt(candidatePath, expectedHash, expectedSource) {
  const stem = candidatePath.slice(0, -path.extname(candidatePath).length)
  const receiptPath = `${stem}.build-receipt.json`
  const { value } = readJsonFile(receiptPath, BUILD_RECEIPT_KEYS, 'BUILD_RECEIPT_INVALID')
  const packageRoot = plainPath(value.package_directory, { directory: true })
  const manifest = plainPath(path.join(packageRoot, 'release-manifest.json'), { file: true })
  const expectedLeaf = `IZ-Clinical-Notes-Analyzer-v${value.version}-build-${value.build}-installer-r1.zip`
  const gateNames = Array.isArray(value.gates) ? value.gates.map((gate) => gate?.name) : []
  if (value.schema !== 'iz-cna-build-receipt-v1' || value.product_id !== PRODUCT_ID ||
      !SUPPORTED_RELEASE_VERSIONS.has(value.version) || !BUILD_ID.test(value.build) || value.installer_revision !== 1 ||
      !SOURCE_REVISION.test(value.source_revision) || value.source_revision !== expectedSource ||
      !samePath(value.zip_path, candidatePath) || value.zip_length !== statSync(candidatePath).size ||
      value.zip_sha256 !== expectedHash || value.zip_sha256 !== sha256(candidatePath) ||
      path.basename(candidatePath) !== expectedLeaf ||
      !requireHash(value.manifest_sha256, 'BUILD_RECEIPT_INVALID') || sha256(manifest) !== value.manifest_sha256 ||
      !requireHash(value.payload_identity, 'BUILD_RECEIPT_INVALID') ||
      gateNames.length !== BUILD_GATE_NAMES.length || gateNames.some((name, index) => name !== BUILD_GATE_NAMES[index])) {
    refuse('BUILD_RECEIPT_INVALID')
  }
  for (const gate of value.gates) {
    exactKeys(gate, ['name', 'status', 'command', 'exit_code', 'evidence'], 'BUILD_GATE_INVALID')
    if (gate.status !== 'passed' || gate.exit_code !== 0 || typeof gate.command !== 'string' || !gate.command ||
        typeof gate.evidence !== 'string' || !gate.evidence || path.isAbsolute(gate.evidence) || gate.evidence.split(/[\\/]/).some((part) => part === '..')) {
      refuse('BUILD_GATE_INVALID')
    }
    plainPath(path.join(path.dirname(receiptPath), gate.evidence), { file: true })
  }
  return Object.freeze({ ...value, package_directory: packageRoot })
}

function validateManifest(packagePath, expectedHash, expectedPayload) {
  const manifestPath = plainPath(path.join(packagePath, 'release-manifest.json'), { file: true })
  if (sha256(manifestPath) !== requireHash(expectedHash, 'MANIFEST_HASH_INVALID')) refuse('MANIFEST_HASH_MISMATCH')
  const { value } = readJsonFile(manifestPath, MANIFEST_KEYS, 'MANIFEST_INVALID')
  exactKeys(value.compatibility, COMPATIBILITY_KEYS, 'MANIFEST_COMPATIBILITY_INVALID')
  if (value.schema !== 'iz-cna-release-manifest-v1' || value.product_id !== PRODUCT_ID ||
      !SUPPORTED_RELEASE_VERSIONS.has(value.version) || !BUILD_ID.test(value.build) || value.installer_revision !== 1 ||
      value.payload_identity !== requireHash(expectedPayload, 'PAYLOAD_IDENTITY_INVALID') ||
      !Array.isArray(value.files) || value.files.length === 0) refuse('MANIFEST_INVALID')
  const listed = new Set()
  let previous = ''
  let payloadRows = ''
  for (const record of value.files) {
    exactKeys(record, ['path', 'length', 'sha256'], 'MANIFEST_FILE_INVALID')
    if (typeof record.path !== 'string' || path.isAbsolute(record.path) || record.path.includes('\\') ||
        record.path.split('/').some((part) => !part || part === '.' || part === '..') ||
        record.path <= previous || listed.has(record.path) || !Number.isInteger(record.length) || record.length < 0 ||
        !requireHash(record.sha256, 'MANIFEST_FILE_INVALID')) refuse('MANIFEST_FILE_INVALID')
    const file = plainPath(path.join(packagePath, ...record.path.split('/')), { file: true, allowEmptyFile: true })
    if (statSync(file).size !== record.length || sha256(file) !== record.sha256) refuse('MANIFEST_FILE_MISMATCH')
    listed.add(record.path)
    previous = record.path
    payloadRows += `${record.path}\t${record.length}\t${record.sha256}\n`
  }
  if (sha256Text(payloadRows) !== value.payload_identity) refuse('PAYLOAD_IDENTITY_MISMATCH')
  const actual = []
  const visit = (directory, prefix = '') => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name
      const target = path.join(directory, entry.name)
      if (entry.isSymbolicLink()) refuse('LINKED_PACKAGE_PATH')
      if (entry.isDirectory()) visit(target, relative)
      else if (entry.isFile() && relative !== 'release-manifest.json') actual.push(relative)
      else if (!entry.isFile()) refuse('PACKAGE_ENTRY_INVALID')
    }
  }
  visit(packagePath)
  if (actual.length !== listed.size || actual.some((item) => !listed.has(item))) refuse('MANIFEST_FILE_SET_MISMATCH')
  return Object.freeze(value)
}

function validateCandidateAuthority(attachment, candidate, candidateHash) {
  const packagePath = plainPath(attachment.candidate_package_path, { directory: true })
  const authorityPath = plainPath(attachment.candidate_authority_path, { file: true })
  const mode = attachment.qualification_mode
  let build
  if (mode === 'release') {
    const expectedAuthority = candidate.slice(0, -path.extname(candidate).length) + '.build-receipt.json'
    if (!samePath(authorityPath, expectedAuthority)) refuse('CANDIDATE_AUTHORITY_INVALID')
    build = validateBuildReceipt(candidate, candidateHash, attachment.expected_source_revision)
    if (!samePath(packagePath, build.package_directory)) refuse('CANDIDATE_PACKAGE_MISMATCH')
  } else if (mode === 'validation_only') {
    const expectedAuthority = path.join(path.dirname(packagePath), 'validation-summary.NOT-RELEASE-READY.json')
    const expectedZip = `${path.basename(packagePath)}.zip`
    if (!path.basename(packagePath).endsWith('.NOT-RELEASE-READY') || path.basename(candidate) !== expectedZip ||
        !samePath(authorityPath, expectedAuthority) || existsSync(candidate.slice(0, -path.extname(candidate).length) + '.build-receipt.json')) {
      refuse('VALIDATION_ONLY_MARKER_INVALID')
    }
    const { value: summary } = readJsonFile(authorityPath, VALIDATION_SUMMARY_KEYS, 'VALIDATION_SUMMARY_INVALID')
    if (summary.schema !== 'iz-cna-build-gate-evidence-v1' || summary.product_id !== PRODUCT_ID ||
        summary.release_ready !== false || summary.source_revision !== attachment.expected_source_revision ||
        summary.zip_safety?.length !== statSync(candidate).size || summary.zip_safety?.sha256 !== candidateHash ||
        summary.directory_safety?.payload_identity !== attachment.candidate_payload_identity) {
      refuse('VALIDATION_SUMMARY_INVALID')
    }
    build = Object.freeze({
      version: summary.version, build: summary.build, installer_revision: summary.installer_revision,
      payload_identity: summary.directory_safety.payload_identity, source_revision: summary.source_revision,
      package_directory: packagePath,
    })
  } else refuse('QUALIFICATION_MODE_INVALID')
  const manifest = validateManifest(packagePath, attachment.candidate_manifest_sha256, attachment.candidate_payload_identity)
  if (manifest.version !== build.version || manifest.build !== build.build ||
      manifest.installer_revision !== build.installer_revision || manifest.payload_identity !== build.payload_identity) {
    refuse('CANDIDATE_MANIFEST_IDENTITY_MISMATCH')
  }
  return Object.freeze({ build, manifest, packagePath })
}

function validateRuntimeIdentity(target, localAppData) {
  const expected = path.join(localAppData, 'IZ Clinical Notes Analyzer Maintenance', 'state', 'runtime-identity.json')
  if (!samePath(target, expected)) refuse('RUNTIME_IDENTITY_LOCATION_INVALID')
  const { value } = readJsonFile(target, RUNTIME_KEYS, 'RUNTIME_IDENTITY_INVALID')
  if (value.schema !== 'iz-cna-runtime-identity-v1' || value.product_id !== PRODUCT_ID ||
      !requireHash(value.scope_id, 'RUNTIME_IDENTITY_INVALID') ||
      !requireHash(value.data_identity, 'RUNTIME_IDENTITY_INVALID') ||
      !GUID_N.test(value.instance_id) || !GUID_N.test(value.transaction_id) ||
      !Number.isInteger(value.process_id) || value.process_id < 1 ||
      !Number.isInteger(value.port) || value.port < 1024 || value.port > 65535 ||
      value.gate !== 'open' || value.draining !== false ||
      typeof value.owner_sid !== 'string' || !value.owner_sid.startsWith('S-1-') ||
      typeof value.pipe_name !== 'string' || !value.pipe_name.startsWith('iz-cna-runtime-v1-')) refuse('RUNTIME_IDENTITY_INVALID')
  const executable = plainPath(value.executable_path, { file: true })
  if (!requireHash(value.executable_sha256, 'RUNTIME_IDENTITY_INVALID') || sha256(executable) !== value.executable_sha256) {
    refuse('RUNTIME_EXECUTABLE_HASH_MISMATCH')
  }
  return Object.freeze({ ...value, executable_path: executable })
}

function validateInstallReceipt(target, localAppData, runtime, build) {
  const expected = path.join(localAppData, 'IZ Clinical Notes Analyzer Maintenance', 'state', 'install-receipt.json')
  if (!samePath(target, expected)) refuse('INSTALL_RECEIPT_LOCATION_INVALID')
  const { value } = readJsonFile(target, INSTALL_RECEIPT_KEYS, 'INSTALL_RECEIPT_INVALID')
  if (value.schema !== 'iz-cna-install-receipt-v1' || value.product_id !== PRODUCT_ID ||
      value.owner_sid !== runtime.owner_sid || value.scope_id !== runtime.scope_id ||
      value.data_identity !== runtime.data_identity || value.version !== runtime.version || value.version !== build.version ||
      value.build !== runtime.build || value.build !== build.build ||
      value.installer_revision !== runtime.installer_revision || value.installer_revision !== build.installer_revision ||
      value.payload_identity !== build.payload_identity || !GUID_N.test(value.last_committed_transaction) ||
      value.last_committed_transaction !== runtime.transaction_id ||
      !Array.isArray(value.owned_files) || !Array.isArray(value.owned_shortcuts)) refuse('INSTALL_RECEIPT_IDENTITY_MISMATCH')
  for (const record of value.owned_files) {
    if (!record || typeof record !== 'object') refuse('OWNED_FILE_INVALID')
    exactKeys(record, ['path', 'length', 'sha256'], 'OWNED_FILE_INVALID')
    if (typeof record.path !== 'string' || !Number.isInteger(record.length) || record.length < 0 ||
        !requireHash(record.sha256, 'OWNED_FILE_INVALID')) refuse('OWNED_FILE_INVALID')
  }
  const executableRecord = value.owned_files.find((record) =>
    record.path.replaceAll('\\', '/').toLowerCase() === 'runtime/izclinicalnotesanalyzer.exe')
  if (!executableRecord || executableRecord.sha256 !== runtime.executable_sha256 ||
      executableRecord.length !== statSync(runtime.executable_path).size) refuse('OWNED_EXECUTABLE_MISMATCH')
  const installRoot = path.dirname(path.dirname(runtime.executable_path))
  if (!samePath(runtime.executable_path, path.join(installRoot, executableRecord.path))) {
    refuse('OWNED_EXECUTABLE_LOCATION_MISMATCH')
  }
  return Object.freeze(value)
}

export function loadMaintenanceAttachment(environment = process.env) {
  const attachmentPath = environment.IZ_CNA_MAINTENANCE_ATTACHMENT
  const localAppData = environment.LOCALAPPDATA
  if (!attachmentPath || !localAppData) refuse('ATTACHMENT_ENVIRONMENT_REQUIRED')
  const { value: attachment } = readJsonFile(attachmentPath, ATTACHMENT_KEYS, 'ATTACHMENT_INVALID')
  if (attachment.schema !== 'iz-cna-maintenance-browser-attachment-v1' || !RUN_ID.test(attachment.run_id) ||
      !/^[A-Z][0-9]{2}$/.test(attachment.case_id) || !['Component', 'Package', 'Home'].includes(attachment.tier) ||
      !SOURCE_REVISION.test(attachment.expected_source_revision)) refuse('ATTACHMENT_IDENTITY_INVALID')
  const candidate = plainPath(attachment.candidate_zip_path, { file: true })
  const candidateHash = requireHash(attachment.candidate_zip_sha256, 'CANDIDATE_HASH_INVALID')
  if (sha256(candidate) !== candidateHash) refuse('CANDIDATE_HASH_MISMATCH')
  const authority = validateCandidateAuthority(attachment, candidate, candidateHash)
  const build = authority.build
  const runtime = validateRuntimeIdentity(attachment.runtime_identity_path, localAppData)
  const installReceipt = validateInstallReceipt(attachment.install_receipt_path, localAppData, runtime, build)
  const expectedBaseUrl = `http://127.0.0.1:${runtime.port}`
  if (attachment.base_url !== expectedBaseUrl) refuse('BASE_URL_IDENTITY_MISMATCH')
  const evidenceRoot = plainPath(attachment.public_evidence_root, { directory: true })
  const evidencePath = plainPath(attachment.evidence_path, { missingLeaf: true })
  if (!samePath(path.dirname(evidencePath), path.join(evidenceRoot, 'browser')) || existsSync(evidencePath) ||
      path.basename(evidencePath) !== 'maintenance-browser.json') refuse('EVIDENCE_PATH_INVALID')
  return Object.freeze({ attachment: Object.freeze(attachment), build, manifest: authority.manifest,
    runtime, installReceipt, evidencePath, evidenceRoot })
}
