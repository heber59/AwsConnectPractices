const http = require('node:http');
const { seed, execute, ApiError } = require('./core.cjs');
const key = process.env.API_KEY;
if (!key) throw new Error('Set API_KEY before starting the mock server');
let state = seed();
http.createServer((req, res) => {
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  if (req.headers['x-api-key'] !== key) { res.writeHead(403); return res.end(JSON.stringify({ error: { message: 'Forbidden' } })); }
  try {
    const url = new URL(req.url, 'http://localhost');
    const next = structuredClone(state);
    const result = execute(next, req.method, url.pathname, Object.fromEntries(url.searchParams));
    if (req.method === 'POST') state = next;
    res.writeHead(200); res.end(JSON.stringify(result));
  } catch (error) {
    res.writeHead(error instanceof ApiError ? error.status : 500);
    res.end(JSON.stringify({ error: { message: error instanceof ApiError ? error.message : 'Internal error' } }));
  }
}).listen(Number(process.env.PORT || 3000), '127.0.0.1', () => console.log('AnyBank mock listening on localhost; data resets on restart.'));
