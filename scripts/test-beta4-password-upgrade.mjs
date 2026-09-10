import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import net from 'node:net'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const data = await mkdtemp(path.join(process.env.LOCALAPPDATA, 'IZ-beta4-upgrade-smoke-'))
const port = await new Promise(resolve => { const server = net.createServer(); server.listen(0, '127.0.0.1', () => { const address = server.address(); server.close(() => resolve(address.port)) }) })
const base = `http://127.0.0.1:${port}`
const chosen = `Synthetic!9${randomBytes(12).toString('hex')}`
const starter = 'r3mar123ABC'
const legacyStarter = `Legacy!9${randomBytes(12).toString('hex')}`
const env = { ...process.env, IZ_CNA_LOCAL_APP_DATA_DIR: data, IZ_CNA_LOCAL_SQLITE_DB_PATH: 'synthetic.sqlite3', IZ_CNA_PORT: String(port), ENVIRONMENT: 'local-client', IZ_CNA_SECRET_KEY: randomBytes(32).toString('hex'), IZ_CNA_DATA_ENCRYPTION_KEY: randomBytes(32).toString('base64url'), IZ_CNA_BOOTSTRAP_ADMIN_USERNAME: 'admin', IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD: starter }
delete env.IZ_CNA_ENV_FILE
let child
const checks = {}
let phase = 'beta3-start'
async function start(version) {
  child = spawn(path.join(root, `dist/windows-release/IZ-Clinical-Notes-Analyzer-v2.0.0-beta.${version}/app/runtime/IZClinicalNotesAnalyzer.exe`), [], { cwd: root, env: { ...env, IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD: version === 3 ? legacyStarter : starter }, windowsHide: true, stdio: 'ignore' })
  for (let index = 0; index < 120; index++) {
    if (child.exitCode !== null) throw new Error('Runtime exited')
    try { const response = await fetch(base + '/api/version'); if (response.ok && JSON.stringify(await response.json()).includes(`2.0.0-beta.${version}`)) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  throw new Error('Readiness timeout')
}
async function stop() {
  if (!child) return
  await new Promise(resolve => { const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' }); killer.once('exit', resolve) })
  await new Promise(resolve => { if (child.exitCode !== null) resolve(); else { child.once('exit', resolve); setTimeout(resolve, 5000).unref() } })
  assert(child.exitCode !== null || child.signalCode !== null)
}
async function post(route, body, token) {
  return fetch(base + route, { method: 'POST', headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body) })
}
try {
  await start(3)
  const initial = await post('/api/auth/login', { username: 'admin', password: legacyStarter })
  assert(initial.ok)
  const token = (await initial.json()).access_token
  assert((await post('/api/users/me/change-password', { current_password: legacyStarter, new_password: chosen }, token)).ok)
  checks.beta3ChosenPasswordEstablished = (await post('/api/auth/login', { username: 'admin', password: chosen })).ok
  assert(checks.beta3ChosenPasswordEstablished)
  await stop()
  phase = 'beta4-upgrade'
  await start(4)
  const login = await post('/api/auth/login', { username: 'admin', password: chosen })
  checks.beta4PreservesChosenPassword = login.ok
  assert(login.ok)
  const upgraded = await login.json()
  checks.noForcedResetOfChosenPassword = upgraded.must_reset_password === false
  checks.starterRejectedAfterUpgrade = !(await post('/api/auth/login', { username: 'admin', password: starter })).ok
  const recovery = await fetch(base + '/api/users/me/recovery-code', { headers: { authorization: `Bearer ${upgraded.access_token}` } })
  console.log(JSON.stringify({ recoveryStatus: recovery.status }))
  checks.upgradedAccountReadyForRecoverySetup = recovery.ok && (await recovery.json()).configured === false
  assert(Object.values(checks).every(Boolean))
  phase = 'complete'
} catch (error) {
  console.log(JSON.stringify({ failureType: error.name, safeReason: error.message.split(String.fromCharCode(10))[0] }))
  process.exitCode = 1
} finally {
  await stop()
  checks.ownedRuntimeStopped = true
  checks.runtimePortClosed = await new Promise(resolve => { const socket = net.createConnection({ host: '127.0.0.1', port }); socket.once('connect', () => { socket.destroy(); resolve(false) }); socket.once('error', () => resolve(true)) })
  const evidence = path.join(root, '.omo/evidence/beta4-password-upgrade')
  await mkdir(evidence, { recursive: true })
  const result = { passed: phase === 'complete', phase, checks, syntheticDataOutsideRepository: true, credentialsRecorded: false }
  await writeFile(path.join(evidence, 'result.json'), JSON.stringify(result, null, 2) + '\n')
  console.log(JSON.stringify(result))
}
