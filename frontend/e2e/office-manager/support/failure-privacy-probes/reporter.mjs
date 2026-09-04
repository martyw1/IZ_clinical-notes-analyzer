import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'node:path'

const root = process.env.IZ_OM_PRIVACY_ROOT
const sentinel = process.env.IZ_OM_PRIVACY_SENTINEL
const hasSentinel = value => typeof value === 'string' && value.includes(sentinel)
const errorsContainSentinel = errors => errors.some(error =>
  ['message', 'stack', 'value', 'errorContext'].some(key => hasSentinel(error[key]))
  || (error.cause && errorsContainSentinel([error.cause])))
const errorsAreSanitized = errors => errors.every(error => error.message === 'FAILURE_DETAILS_REDACTED'
  && error.stack === undefined && (error.value === undefined || error.value === 'FAILURE_DETAILS_REDACTED')
  && (!error.cause || errorsAreSanitized([error.cause])))

export default class ProbeReporter {
  observations = []
  observed = new Set()
  tests = []
  unhandledErrors = 0
  onBegin(config, suite) {
    this.discovered = suite.allTests().length
    this.capturePolicy = { preserveOutput: config.preserveOutput, trace: config.projects[0].use.trace,
      video: config.projects[0].use.video, screenshot: config.projects[0].use.screenshot }
  }
  scan(phase) {
    const walk = directory => {
      if (!existsSync(directory)) return
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const filename = path.join(directory, entry.name)
        if (entry.isDirectory()) walk(filename)
        else if (entry.isFile()) {
          const bytes = readFileSync(filename)
          const hash = createHash('sha256').update(bytes).digest('hex')
          const relative = path.relative(root, filename)
          const key = `${relative}:${hash}`
          if (this.observed.has(key)) continue
          this.observed.add(key)
          this.observations.push({ phase, path: relative, bytes: bytes.length, sha256: hash,
            sentinelPresent: bytes.includes(sentinel) })
        }
      }
    }
    walk(path.join(root, 'output'))
  }
  onStepEnd() { this.scan('step-end') }
  onTestEnd(test, result) {
    this.scan('test-end')
    this.tests.push({ status: result.status, expectedStatus: test.expectedStatus,
      errorCount: result.errors.length, errorsContainSentinel: errorsContainSentinel(result.errors),
      publicErrorDetailsSanitized: errorsAreSanitized(result.errors) })
  }
  onError() { this.unhandledErrors += 1 }
  onEnd(result) {
    this.scan('run-end')
    writeFileSync(path.join(root, 'probe-result.json'), JSON.stringify({ status: result.status,
      discovered: this.discovered, tests: this.tests, unhandledErrors: this.unhandledErrors,
      capturePolicy: this.capturePolicy, observations: this.observations }, null, 2))
  }
}
