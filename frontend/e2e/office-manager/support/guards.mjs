import { existsSync, lstatSync, realpathSync, statSync } from 'node:fs'
import path from 'node:path'

export class HarnessError extends Error {
  constructor(code) {
    super(`Office-manager smoke refused: ${code}`)
    this.name = 'HarnessError'
    this.code = code
  }
}

export function assertPlainPath(target) {
  let current = path.resolve(target)
  while (true) {
    if (existsSync(current) && lstatSync(current).isSymbolicLink()) throw new HarnessError('LINKED_TARGET_PATH')
    const parent = path.dirname(current)
    if (parent === current) return
    current = parent
  }
}

function requireExecutable(executable, code) {
  if (!executable || !existsSync(executable) || !statSync(executable).isFile()) throw new HarnessError(code)
  return realpathSync(executable)
}

export function validateTarget(input) {
  if (input.baseUrl) {
    let url
    try { url = new URL(input.baseUrl) } catch { throw new HarnessError('UNSAFE_URL') }
    if (url.protocol !== 'http:' || !['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname) || url.username || url.password) {
      throw new HarnessError('UNSAFE_URL')
    }
    throw new HarnessError('EXISTING_RUNTIME_URL')
  }
  const ownedRoot = path.resolve(input.ownedRoot)
  const dataDir = path.resolve(input.dataDir)
  if (path.dirname(dataDir).toLowerCase() !== ownedRoot.toLowerCase() || !/^run-[0-9a-f-]{36}$/i.test(path.basename(dataDir))) {
    throw new HarnessError('UNOWNED_DATA_PATH')
  }
  assertPlainPath(dataDir)
  if (existsSync(dataDir)) throw new HarnessError('EXISTING_DATA_PATH')
  const preparedExecutable = input.runtimeMode === 'prepared'
    ? requireExecutable(input.preparedExecutable, 'MISSING_PREPARED_EXECUTABLE') : ''
  return Object.freeze({
    ownedRoot, dataDir, preparedExecutable,
    pythonExecutable: requireExecutable(input.pythonExecutable, 'MISSING_CHECKOUT_INTERPRETER'),
    browserExecutable: requireExecutable(input.browserExecutable, 'MISSING_INSTALLED_BROWSER'),
  })
}
