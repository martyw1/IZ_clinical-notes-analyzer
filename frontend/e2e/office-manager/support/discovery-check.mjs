import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
const cli = path.join(repo, 'frontend/node_modules/@playwright/test/cli.js')

function discovery(config, overrides = {}) {
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('IZ_OM_') && !key.startsWith('IZ_CNA_E2E_')))
  const result = spawnSync(process.execPath, [cli, 'test', '--config', config, '--list', '--reporter=json'], {
    cwd: repo, env: { ...env, ...overrides }, encoding: 'utf8', windowsHide: true, timeout: 60_000,
  })
  assert.equal(result.status, 0, 'Discovery must exit successfully without starting a runtime')
  assert.doesNotThrow(() => JSON.parse(result.stdout), 'Discovery must not execute Node self-tests or emit unrelated stdout')
  const report = JSON.parse(result.stdout)
  assert.deepEqual(report.errors, [])
  return report.suites.flatMap(suite => flatten(suite))
}

function flatten(suite) {
  return [...suite.specs.map(spec => ({ file: spec.file, title: spec.title })), ...(suite.suites ?? []).flatMap(child => flatten(child))]
}

test('ordinary config lists all seven original tests without importing the isolated suite', () => {
  // Given: the ordinary config with no office-manager or desktop runtime environment.
  // When: Playwright performs discovery only.
  const specs = discovery('frontend/playwright.config.mjs')
  // Then: both original files remain intact and no isolated spec/self-test is imported.
  assert.equal(specs.length, 7)
  assert.deepEqual([...new Set(specs.map(spec => spec.file))].sort(), ['treatment-plan-pull.spec.mjs', 'workflow-profiles.spec.mjs'])
  assert.equal(specs.filter(spec => spec.file === 'workflow-profiles.spec.mjs').length, 4)
  assert.equal(specs.filter(spec => spec.file === 'treatment-plan-pull.spec.mjs').length, 3)
})

test('dedicated config still discovers every office-manager scenario and no support self-test', () => {
  // Given: inert discovery-only settings, with no credentials, server, browser, or fixture data.
  const expectedFiles = readdirSync(path.join(repo, 'frontend/e2e/office-manager')).filter(name => name.endsWith('.spec.mjs')).sort()
  // When: the dedicated config lists all scenarios without executing their test bodies.
  const specs = discovery('frontend/playwright.office-manager.config.mjs', {
    IZ_OM_BASE_URL: 'http://127.0.0.1:1', IZ_OM_RUN_ID: 'discovery-only-no-runtime',
    IZ_OM_SCENARIO: 'all', IZ_OM_CASE: 'all',
  })
  // Then: each scenario remains available exclusively through its intended config.
  assert.deepEqual([...new Set(specs.map(spec => spec.file))].sort(), expectedFiles)
  assert.ok(specs.length >= expectedFiles.length)
  assert.ok(specs.every(spec => /@(happy|edge)\b/.test(spec.title)))
})
