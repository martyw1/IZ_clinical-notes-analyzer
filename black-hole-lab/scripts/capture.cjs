const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
async function main() {
  const browser = await chromium.launch({ headless: true });
  const captures = [];
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(process.env.HORIZON_URL || 'http://127.0.0.1:8766/dist/index.html');
    for (const width of [375,768,1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const view of ['simulation','scientist','catalog','library','research']) {
        await page.locator(`[data-view="${view}"]`).click();
        if (view === 'research') { await page.locator('.research-figure img').scrollIntoViewIfNeeded(); await page.waitForFunction(() => document.querySelector('.research-figure img').naturalWidth === 1849); }
        const geometry = await page.evaluate(() => ({ viewport: innerWidth, client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
        const file = `qa-${width}-${view}.png`;
        const bytes = await page.screenshot({ path: path.join(root,'evidence',file), fullPage:true, type:'png' });
        if (bytes.readUInt32BE(0) !== 0x89504e47) throw Error('Invalid PNG signature');
        const imageWidth = bytes.readUInt32BE(16), imageHeight = bytes.readUInt32BE(20);
        if (imageWidth !== width || geometry.scroll > width) throw Error('Capture dimensions or overflow failure');
        captures.push({ file, ...geometry, imageWidth, imageHeight });
      }
    }
    await page.locator('[data-view="simulation"]').click();
    await page.locator('#timeline').press('End');
    await page.locator('#wave-window').selectOption('end');
    await page.screenshot({ path:path.join(root,'evidence','qa-1280-ringdown.png'), fullPage:true,type:'png' });
    await page.locator('#reset').click();
    await page.locator('#timeline').press('Home');
    for (let i=0;i<8;i++) await page.locator('#timeline').press('PageUp');
    await page.screenshot({ path:path.join(root,'evidence','qa-1280-merger.png'), fullPage:true,type:'png' });
    await page.locator('[data-view="scientist"]').click(); await page.locator('#science-check').click(); await page.waitForFunction(() => document.querySelector('#science-check-result').textContent.startsWith('PASS'));
    await page.screenshot({path:path.join(root,'evidence','qa-1280-scientist-verified.png'),fullPage:true,type:'png'});
    await page.locator('#science-fref').fill('500'); await page.getByRole('button',{name:'Calculate waveform',exact:true}).click();
    await page.screenshot({path:path.join(root,'evidence','qa-1280-scientist-invalid.png'),fullPage:true,type:'png'});
    await page.locator('[data-view="simulation"]').click(); await page.locator('#reset').click();
    await page.locator('.space-panel').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(root,'evidence','qa-motion-rest.png'),type:'png'});
    await page.locator('#play').click(); await page.waitForTimeout(100); await page.screenshot({path:path.join(root,'evidence','qa-motion-mid.png'),type:'png'});
    await page.waitForTimeout(1500); await page.locator('#play').click(); await page.screenshot({path:path.join(root,'evidence','qa-motion-paused.png'),type:'png'});
    const files = ['index.html','styles.css','physics.js','scientific.js','app.js','workbench.js','data/publications.js','data/science-references.js'];
    const sources = Object.fromEntries(files.map(file => [file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'dist',file))).digest('hex')]));
    fs.writeFileSync(path.join(root,'evidence','capture-manifest.json'),JSON.stringify({capturedAt:new Date().toISOString(),artifact:'Horizon.html',sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'Horizon.html'))).digest('hex'),sources,captures},null,2));
    console.log(JSON.stringify(captures));
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
