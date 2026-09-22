import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../apps/web-v32/', import.meta.url));
const port = Number(process.env.WEB_PORT || 8780);
const apiPort = Number(process.env.API_PORT || 8800);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.woff2': 'font/woff2' };

http.createServer(async (req, res) => {
  if (/^\/(api\/|health\/)/.test(req.url)) {
    const upstream = http.request({
      hostname: '127.0.0.1', port: apiPort, path: req.url, method: req.method,
      headers: { ...req.headers, host: `127.0.0.1:${apiPort}` },
    }, response => {
      res.writeHead(response.statusCode, response.headers);
      response.pipe(res);
    });
    upstream.on('error', () => {
      if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ detail: 'Local API is unavailable. Start the API server first.' }));
    });
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
    return;
  }
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    const file = path.resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
    const relative = path.relative(root, file);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      res.writeHead(403); res.end(); return;
    }
    const bytes = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(req.method === 'HEAD' ? undefined : bytes);
  } catch {
    res.writeHead(404); res.end('Not found');
  }
}).listen(port, '127.0.0.1', () => console.log(`Web: http://127.0.0.1:${port}/`));
