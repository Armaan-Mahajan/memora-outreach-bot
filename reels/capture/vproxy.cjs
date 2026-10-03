// Proxy (:3000 -> next start on :3001) with a piecewise virtual clock.
// SSE chunks are released when virtual time reaches (request's virtual start + the server's real delay),
// so the demo's streaming plays at real speed inside a page whose clock runs K× slow.
// GET /__k?k=N changes the dilation factor (called in lockstep with the page).
const httpProxy = require('http-proxy'); const http = require('http'); const url = require('url');
const TARGET = process.env.TARGET || 'http://127.0.0.1:3001';
let K = 1, rb = Date.now(), vb = Date.now();
const vnow = () => vb + (Date.now() - rb) / K;
const setK = k => { vb = vnow(); rb = Date.now(); K = k; };
const proxy = httpProxy.createProxyServer({ target: TARGET, ws: true, selfHandleResponse: true });
proxy.on('proxyRes', (pres, req, res) => {
  const ct = String(pres.headers['content-type'] || ''); res.writeHead(pres.statusCode, pres.headers);
  if (!ct.includes('text/event-stream')) { pres.pipe(res); return; }
  const q = []; let ended = false, n = 0;
  pres.on('data', c => { q.push({ due: req._v0 + (Date.now() - req._r0), c }); n++; });
  pres.on('end', () => { ended = true; });
  const tick = setInterval(() => { const v = vnow();
    while (q.length && q[0].due <= v) res.write(q.shift().c);
    if (ended && !q.length) { clearInterval(tick); res.end(); console.log(`SSE ${req.url} chunks=${n}`); } }, 5);
});
proxy.on('error', (e, req, res) => { try { res.end(); } catch {} });
http.createServer((req, res) => {
  if (req.url.startsWith('/__k')) { setK(+url.parse(req.url, true).query.k || 1); res.end('K=' + K); return; }
  req._r0 = Date.now(); req._v0 = vnow(); proxy.web(req, res);
}).on('upgrade', (req, sock, head) => proxy.ws(req, sock, head)).listen(3000, () => console.log('vproxy up'));
