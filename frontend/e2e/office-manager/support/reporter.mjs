import { writeFileSync } from 'node:fs'
import path from 'node:path'

export default class SafeReporter {
  tests = []
  discovered = []
  errors = 0
  onBegin(_config, suite) {
    this.discovered = suite.allTests().map(test => ({
      title: test.title,
      file: path.basename(test.location.file),
      line: test.location.line,
    }))
  }
  onTestEnd(test, result) {
    this.tests.push({
      title: test.title,
      file: path.basename(test.location.file),
      line: test.location.line,
      status: result.status,
      durationMs: result.duration,
      errorCount: result.errors.length,
    })
  }
  onError() { this.errors += 1 }
  onEnd(result) {
    const report = {
      status: result.status,
      discoveredCount: this.discovered.length,
      discovered: this.discovered,
      executedCount: this.tests.length,
      passedCount: this.tests.filter(test => test.status === 'passed').length,
      tests: this.tests,
      errorCount: this.errors,
      errorBodiesOmitted: true,
    }
    const filename = process.env.IZ_OM_DISCOVERY === '1' ? 'discovery.json' : 'playwright-results.json'
    writeFileSync(path.join(process.env.IZ_OM_EVIDENCE_DIR, filename), JSON.stringify(report, null, 2))
  }
}
