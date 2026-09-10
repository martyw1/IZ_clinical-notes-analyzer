const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { gzipSync } = require('node:zlib');
const root = path.resolve(__dirname, '..');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json' };
const server = http.createServer((request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    const file = path.resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!file.startsWith(root + path.sep) || !fs.statSync(file).isFile()) throw Error('Missing file');
    const raw = fs.readFileSync(file);
    const compress = /\bgzip\b/.test(request.headers['accept-encoding'] || '') && Boolean(types[path.extname(file)]);
    const body = compress ? gzipSync(raw) : raw;
    response.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store', 'Content-Length': body.length, Vary: 'Accept-Encoding', ...(compress ? { 'Content-Encoding': 'gzip' } : {}) });
    response.end(body);
  } catch { response.writeHead(404, { 'Content-Type': 'text/plain' }); response.end('Not found'); }
});
server.listen(8766, '127.0.0.1', () => console.log('Horizon: http://127.0.0.1:8766'));
