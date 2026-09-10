const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const { default: AxeBuilder } = require('@axe-core/playwright');
const root = path.resolve(__dirname, '..');
const evidence = path.join(root, 'evidence');
async function main() {
  const browser = await chromium.launch({ channel: 'chromium', headless: true, args: ['--remote-debugging-port=9227'] });
  try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  const url = process.env.HORIZON_URL || 'http://127.0.0.1:8766/dist/index.html';
  await page.goto(url);
  assert.match(await page.locator('#event-title').innerText(), /GW150914/);
  assert.ok(await page.locator('script[src]').count() <= 10);
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export').click();
  const download = await downloadPromise;
  assert.equal(download.suggestedFilename(), 'horizon-model.json');
  const output = path.join(evidence, 'model-export.json');
  await download.saveAs(output);
  const exported = JSON.parse(fs.readFileSync(output, 'utf8'));
  assert.ok(exported.samples.length >= 4096);
  assert.equal(exported.samples[0].observerSeconds, 0);
  assert.ok(exported.samples.every(sample => Number.isFinite(sample.hPlus) && Number.isFinite(sample.frequencyHz)));
  assert.equal(exported.samples.at(-1).stage, 'Fitted ringdown');
  const accessibility = [];
  for (const view of ['simulation', 'scientist', 'catalog', 'library', 'research']) {
    await page.locator(`[data-view="${view}"]`).click();
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    accessibility.push({ view, violations: result.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, nodes: v.nodes.map(n => n.target) })) });
  }
  await page.locator('[data-view="scientist"]').click();
  await page.locator('#science-check').click();
  await page.waitForFunction(() => document.querySelector('#science-check-result').textContent.startsWith('PASS'));
  const scientificCheck = await page.locator('#science-check-result').innerText();
  const initialSNR = Number((await page.locator('#science-snr').innerText()).replaceAll(',', ''));
  await page.locator('#science-distance').fill('940');
  assert.equal(await page.locator('#science-export').isDisabled(), true);
  await page.getByRole('button', { name: 'Calculate waveform', exact: true }).click();
  assert.ok(Math.abs(Number(await page.locator('#science-snr').innerText()) - initialSNR / 2) < .001);
  await page.locator('#science-fref').fill('500'); await page.getByRole('button', { name: 'Calculate waveform', exact: true }).click();
  assert.match(await page.locator('#science-error').innerText(), /ISCO/); assert.equal(await page.locator('#science-export').isDisabled(), true);
  await page.locator('#science-reset').click();
  const csvPromise = page.waitForEvent('download'); await page.locator('#science-export').click();
  const csvDownload = await csvPromise; const csvPath = path.join(evidence, 'scientific-export.csv'); await csvDownload.saveAs(csvPath);
  const csv = fs.readFileSync(csvPath, 'utf8').trim().split('\n');
  assert.match(csv[0], /hplus_real_s/); assert.equal(csv.length - 1, Number(await page.locator('#science-count').innerText()));
  assert.ok(csv.slice(1).every(row => row.split(',').map(Number).every(Number.isFinite)));
  const configPromise = page.waitForEvent('download'); await page.locator('#science-config').click(); const configDownload = await configPromise;
  const configPath = path.join(evidence, 'reproducibility-export.json'); await configDownload.saveAs(configPath); const config = JSON.parse(fs.readFileSync(configPath));
  assert.equal(config.verification.pass, true); assert.equal(config.inputs.order, 7); assert.ok(config.conventions.noise.includes('not measured'));
  await page.locator('[data-view="library"]').click(); assert.match(await page.locator('#library-count').innerText(), /310 of 310/);
  await page.locator('#library-search').fill('zz-no-result-928173'); assert.match(await page.locator('#library-count').innerText(), /0 of 310/);
  await page.locator('#library-search').fill(''); await page.locator('#library-topic').selectOption('Stochastic'); assert.match(await page.locator('#library-count').innerText(), /27 of 310/);
  await page.locator('#library-topic').selectOption('');
  while (await page.locator('#library-more').isVisible()) await page.locator('#library-more').click(); assert.equal(await page.locator('.library-row').count(), 310);
  await page.locator('[data-view="research"]').click(); const figure = page.locator('.research-figure img'); await figure.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => document.querySelector('.research-figure img').naturalWidth === 1849);
  const receipt = { url, browserVersion: browser.version(), errors, requests, downloadedSamples: exported.samples.length, scientificCheck, scientificExportRows: csv.length - 1, libraryRows: 310, accessibility };
  fs.writeFileSync(path.join(evidence, 'automation-qa.json'), JSON.stringify(receipt, null, 2));
  console.log(JSON.stringify({ ...receipt, requests: requests.length }));
  assert.equal(errors.length, 0);
  await page.goto(url);
  const lighthousePath = path.join(root, 'node_modules', 'lighthouse', 'core', 'index.js');
  const { default: lighthouse } = await import(pathToFileURL(lighthousePath));
  const results = [];
  for (const preset of ['mobile', 'desktop']) for (let run = 1; run <= 3; run++) {
    const options = { port: 9227, logLevel: 'error', output: 'json', onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'] };
    const config = preset === 'desktop' ? { extends:'lighthouse:default',settings:{formFactor:'desktop',screenEmulation:{mobile:false,width:1350,height:940,deviceScaleFactor:1},throttling:{rttMs:40,throughputKbps:10240,cpuSlowdownMultiplier:1}} } : undefined;
    const result = await lighthouse(url, options, config);
    if (run === 1) fs.writeFileSync(path.join(evidence, `lighthouse-${preset}-full.json`), JSON.stringify(result.lhr));
    const scores = Object.fromEntries(Object.entries(result.lhr.categories).map(([id, category]) => [id, Math.round(category.score * 100)]));
    const failures = Object.entries(result.lhr.audits).filter(([,a]) => a.score !== null && a.score < 1).map(([id,a])=>({ id, score:a.score, title:a.title, displayValue:a.displayValue }));
    results.push({ preset, run, scores, failures });
    fs.writeFileSync(path.join(evidence, 'lighthouse.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify({ preset, run, scores }));
  }
  assert.ok(accessibility.every(entry => entry.violations.length === 0), 'Accessibility violations remain');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
