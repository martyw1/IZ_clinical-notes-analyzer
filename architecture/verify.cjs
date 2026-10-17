const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const dir = __dirname;
async function main() {
  let links = 0;
  const pages = fs.readdirSync(dir).filter(p=>p.endsWith('.html'));
  for(const p of pages) {
    const html = fs.readFileSync(path.join(dir,p),'utf8');
    for(const m of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
      if(m[1].startsWith('#')) continue;
      if(/^[a-z]+:/i.test(m[1])) throw Error('Unexpected external dependency: '+m[1]);
      const target=path.resolve(dir,decodeURI(m[1]));
      if(!fs.existsSync(target)) throw Error(`${p}: missing ${m[1]}`);
      links++;
    }
  }
  const {chromium}=require(path.join(dir,'../frontend/node_modules/@playwright/test'));
  console.log(`Static link gate passed: ${pages.length} pages, ${links} local references.`);
  const browser=await chromium.launch({headless:true, channel:'msedge'});
  try {
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    for(const p of pages) {
      await page.goto(pathToFileURL(path.join(dir,p)).href);
      if(await page.locator('h1').count()!==1) throw Error('Missing heading: '+p);
      if(await page.locator('nav a').count()!==9) throw Error('Missing navigation: '+p);
    }
    await page.goto(pathToFileURL(path.join(dir,'screens.html')).href);
    await page.locator('#filter').fill('Manual Upload');
    if(await page.locator('.filter-item:visible').count()!==1) throw Error('Screen search failed');
    await page.locator('#filter').fill('no-such-screen-xyz');
    if(await page.locator('.filter-item:visible').count()!==0) throw Error('Empty results failed');
    await page.goto(pathToFileURL(path.join(dir,'backend.html')).href);
    await page.locator('#filter').fill('/api/auth/login');
    if(await page.locator('.filter-item:visible').count()!==1) throw Error('API search failed');
    await page.setViewportSize({width:390,height:844});
    for(const p of ['index.html','screens.html','backend.html','flows.html']){
      await page.goto(pathToFileURL(path.join(dir,p)).href);
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
      if(overflow) throw Error('Mobile overflow: '+p);
    }
    if(errors.length) throw Error(errors.join('\n'));
    console.log(`PASS: ${pages.length} HTML pages, ${links} local links/assets, browser rendering, screen/API filters, empty results, 390px mobile layout, no page errors.`);
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
