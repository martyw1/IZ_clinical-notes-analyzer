import { spawn, spawnSync } from 'node:child_process'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { setTimeout as delay } from 'node:timers/promises'
import { HarnessError } from './guards.mjs'

export async function allocatePort() {
  const server = createServer()
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  if (!address || typeof address === 'string') throw new HarnessError('PORT_ALLOCATION_FAILED')
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  return address.port
}

export function startOwned(executable, args, options) {
  const child = spawn(executable, args, { ...options, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
  const record = { executable, pid: child.pid, startedAt: new Date().toISOString(), exitCode: null, stopped: false }
  // Drain, but never persist authentication-bearing process output or raw exceptions.
  child.stdout.resume()
  child.stderr.resume()
  const completion = new Promise(resolve => {
    child.once('error', () => { record.exitCode = -1; record.stopped = true; resolve(-1) })
    child.once('exit', code => { record.exitCode = code; record.stopped = true; resolve(code ?? -1) })
  })
  return { child, record, completion }
}

export async function waitOwned(owned, timeoutMs) {
  const controller = new AbortController()
  const timedOut = delay(timeoutMs, 'timeout', { signal: controller.signal }).catch(() => 'cancelled')
  const result = await Promise.race([owned.completion, timedOut])
  controller.abort()
  if (result === 'timeout') throw new HarnessError('OWNED_PROCESS_TIMEOUT')
  return result
}

export async function stopOwned(owned) {
  if (!owned || owned.record.stopped) return
  // The live ChildProcess handle proves this PID is still the process we started.
  if (process.platform === 'win32') {
    const result = spawnSync('taskkill.exe', ['/PID', String(owned.child.pid), '/T', '/F'], {
      windowsHide: true, stdio: 'ignore', timeout: 15_000,
    })
    owned.record.treeTerminationExitCode = result.status
  } else {
    owned.child.kill('SIGTERM')
  }
  await waitOwned(owned, 15_000)
}

export async function waitForRuntime(baseUrl, owned) {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    if (owned.record.stopped) throw new HarnessError('RUNTIME_EXITED_BEFORE_READY')
    try {
      const response = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(1_000), redirect: 'error' })
      if (response.ok && (await response.json()).status === 'ok') {
        const version = await fetch(`${baseUrl}/api/version`, { signal: AbortSignal.timeout(10_000), redirect: 'error' })
        if (version.ok) return version.json()
      }
    } catch (error) {
      if (!(error instanceof TypeError || error instanceof DOMException)) throw error
    }
    await delay(150)
  }
  throw new HarnessError('RUNTIME_HEALTH_TIMEOUT')
}

export async function runtimeStopped(baseUrl) {
  try {
    await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(1_000), redirect: 'error' })
    return false
  } catch (error) {
    if (error instanceof TypeError || error instanceof DOMException) return true
    throw error
  }
}
