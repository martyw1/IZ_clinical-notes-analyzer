import { test as guarded, expect } from '../failurePrivacy.mjs'
import { test as base } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import path from 'node:path'
import { createServer } from 'node:http'
import { once } from 'node:events'

const sentinel = process.env.IZ_OM_PRIVACY_SENTINEL
const kind = process.env.IZ_OM_PRIVACY_CASE
const selected = process.env.IZ_OM_PRIVACY_MODE === 'guarded' ? guarded : base.extend({
  failurePrivacy: [async ({}, use) => { await use() }, { auto: true, timeout: 5_000 }],
})
const test = selected.extend({
  dependent: async ({ failurePrivacy }, use) => {
    if (kind === 'dependent-setup') throw new Error(sentinel)
    await use(failurePrivacy)
    if (kind === 'dependent-teardown') throw new Error(sentinel)
  },
})

if (kind === 'beforeAll') test.beforeAll(() => { throw new Error(sentinel) })
if (kind === 'afterAll') test.afterAll(() => { throw new Error(sentinel) })
test.beforeEach(() => { if (kind === 'beforeEach') throw new Error(sentinel) })
test.afterEach(({}, testInfo) => {
  if (kind === 'afterEach') throw new Error(sentinel)
  if (kind === 'public-context') testInfo.errors[0].errorContext = sentinel
})

if (['locator', 'snapshot'].includes(kind)) {
  test('standalone browser privacy probe', async ({ page, browser }) => {
    const cdp = await browser.newBrowserCDPSession()
    const info = await cdp.send('SystemInfo.getProcessInfo')
    const record = {
      executable: process.env.IZ_OM_PRIVACY_BROWSER_EXECUTABLE,
      channel: process.env.IZ_OM_PRIVACY_BROWSER, version: browser.version(),
      pids: info.processInfo.map(item => item.id), headless: true, clinicalRuntime: false,
      ownedProfileDirectory: null,
    }
    const recordPath = path.join(process.env.IZ_OM_PRIVACY_ROOT, 'browser.json')
    writeFileSync(recordPath, JSON.stringify(record))
    const commandLine = await cdp.send('Browser.getBrowserCommandLine')
    const profileArgument = commandLine.arguments.find(value => value.startsWith('--user-data-dir='))
    expect(profileArgument).toBeTruthy()
    record.ownedProfileDirectory = profileArgument.slice('--user-data-dir='.length)
    writeFileSync(recordPath, JSON.stringify(record))
    await cdp.detach()
    await page.goto('about:blank')
    if (kind === 'locator') {
      await page.setContent('<input type="password" aria-label="Synthetic input">')
      await page.locator('#missing-input').fill(sentinel, { timeout: 150 })
    } else {
      await page.setContent(`<p>${sentinel}</p>`)
      throw new Error('DELIBERATE_SNAPSHOT_PROBE_FAILURE')
    }
  })
} else if (kind === 'api') {
  test('standalone API failure privacy probe', async ({ request }) => {
    const server = createServer((_request, response) => {
      response.writeHead(500, { 'content-type': 'text/plain' })
      response.end('DELIBERATE_LOCAL_API_FAILURE')
    })
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const port = server.address().port
    try {
      await request.get(`http://127.0.0.1:${port}/${sentinel}`, { timeout: 1_000, failOnStatusCode: true })
    } finally {
      await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
      writeFileSync(path.join(process.env.IZ_OM_PRIVACY_ROOT, 'api-server.json'), JSON.stringify({
        port, loopbackOnly: true, clinicalRuntime: false, serverClosed: !server.listening,
      }))
    }
  })
} else {
  test('standalone lifecycle privacy probe', async ({ dependent }) => {
    if (kind === 'body') throw new Error(sentinel, { cause: new Error(sentinel) })
    if (kind === 'public-context') throw new Error('DELIBERATE_CONTEXT_PROBE_FAILURE')
    if (kind === 'thrown-value') throw sentinel
    if (kind === 'timeout' || kind === 'pure-timeout') {
      test.setTimeout(250)
      if (kind === 'timeout') expect.soft(sentinel).toBe('not-the-sentinel')
      await new Promise(() => {})
    }
    expect(dependent).toBeUndefined()
  })
}
