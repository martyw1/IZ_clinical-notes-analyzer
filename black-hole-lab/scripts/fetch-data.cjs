const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const root = path.resolve(__dirname, '..');
const endpoints = {
  events: 'https://gwosc.org/api/v2/event-versions?include-default-parameters=true&format=json&page_size=100',
  catalogs: 'https://gwosc.org/api/v2/catalogs?format=json&page_size=100',
  runs: 'https://gwosc.org/api/v2/runs?format=json&page_size=100',
};
async function collect(url) {
  const rows = [], visited = new Set();
  let expected;
  while (url) {
    const target = new URL(url);
    if (target.origin !== 'https://gwosc.org' || visited.has(url)) throw Error('Unexpected pagination URL');
    visited.add(url);
    const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
    if (!response.ok) throw Error(`GWOSC HTTP ${response.status}`);
    const page = await response.json();
    if (!Array.isArray(page.results)) throw Error('GWOSC results are missing');
    expected ??= page.results_count;
    rows.push(...page.results);
    url = page.next;
    console.log(`${target.pathname}: ${rows.length}/${expected}`);
  }
  if (rows.length !== expected) throw Error(`Incomplete catalog: ${rows.length}/${expected}`);
  return { rows, pages: visited.size, expected };
}
async function main() {
  const events = await collect(endpoints.events);
  const catalogs = await collect(endpoints.catalogs);
  const runs = await collect(endpoints.runs);
  const dataset = { retrievedAt: new Date().toISOString(), endpoints, counts: {
    versions: events.rows.length, events: new Set(events.rows.map(e => e.name)).size,
    catalogs: catalogs.rows.length, runs: runs.rows.length, pages: events.pages,
  }, events: events.rows, catalogs: catalogs.rows, runs: runs.rows };
  const json = JSON.stringify(dataset);
  fs.writeFileSync(path.join(root, 'data', 'gwosc-snapshot.json'), json);
  fs.writeFileSync(path.join(root, 'data', 'gwosc.js'), `window.GWOSC_DATA=${json.replaceAll('<', '\\u003c')};\n`);
  fs.writeFileSync(path.join(root, 'data', 'manifest.json'), JSON.stringify({ retrievedAt: dataset.retrievedAt,
    endpoints, counts: dataset.counts, sha256: createHash('sha256').update(json).digest('hex'),
    scope: 'All event-version default parameters exposed by the GWOSC API at retrieval; catalog and observing-run indexes. Not raw strain, posterior samples, or every LIGO data product.',
    license: 'CC BY 4.0', credit: 'LIGO Scientific Collaboration, Virgo Collaboration, KAGRA Collaboration; Gravitational Wave Open Science Center',
  }, null, 2));
  console.log(JSON.stringify(dataset.counts));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
