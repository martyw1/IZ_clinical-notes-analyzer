const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const references = { pn: JSON.parse(fs.readFileSync(path.join(root, 'data/references/pn-source-fixtures.json'))), waveform: JSON.parse(fs.readFileSync(path.join(root, 'data/references/taylorf2-independent.json'))) };
fs.writeFileSync(path.join(root, 'data/science-references.js'), `window.HORIZON_REFERENCE=${JSON.stringify(references)};\n`);
let html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const staticOutput = path.join(root, 'dist');
fs.mkdirSync(staticOutput, { recursive: true });
const staticFiles = ['index.html', 'styles.css', 'physics.js', 'scientific.js', 'app.js', 'workbench.js', 'data/gwosc.js', 'data/research.js', 'data/observed-gw150914.js', 'data/publications.js', 'data/science-references.js', 'assets/wolfe-subsolar-figure-2.png'];
for (const file of staticFiles) { const destination = path.join(staticOutput, file); fs.mkdirSync(path.dirname(destination), { recursive: true }); fs.copyFileSync(path.join(root, file), destination); }
html = html.replace('<link rel="stylesheet" href="styles.css">', () => `<style>${fs.readFileSync(path.join(root, 'styles.css'), 'utf8')}</style>`);
fs.writeFileSync(path.join(staticOutput, 'index.html'), html);
html = html.replace('src="assets/wolfe-subsolar-figure-2.png"', () => `src="data:image/png;base64,${fs.readFileSync(path.join(root, 'assets/wolfe-subsolar-figure-2.png')).toString('base64')}"`);
html = html.replace(/<script src="([^"]+)" defer><\/script>/g, (_, file) => {
  const source = fs.readFileSync(path.join(root, file), 'utf8').replace(/<\/script/gi, '<\\/script');
  return `<script>${source}</script>`;
});
const start = html.indexOf('  <script>');
const end = html.lastIndexOf('</script>') + '</script>'.length;
const scripts = html.slice(start, end);
html = html.slice(0, start) + html.slice(end);
html = html.replace('</body>', `${scripts}\n</body>`);
fs.writeFileSync(path.join(root, 'Horizon.html'), html);
console.log(`Built Horizon.html: ${Buffer.byteLength(html).toLocaleString()} bytes; all runtime assets embedded.`);
console.log(`Sites static output: ${staticFiles.length} explicitly selected files.`);
