// Proxy (:3000 -> next start on :3001) that delivers the app's responses on the recorder's virtual clock.
// While recording, runner.mjs steps time one frame at a time and reports it here (GET /__vt?t=<ms>). Every response
// chunk is released when virtual time reaches (virtual time the request arrived + the server's real delay for that
// chunk), so generation streams and page loads play at their real pace inside the stepped recording; a `speed: fast`
// step advances virtual time faster per frame, so they play faster too. Before recording (login) it is a plain proxy.
const httpProxy = require('http-proxy'); const http = require('http'); const url = require('url');
const TARGET = process.env.TARGET || 'http://127.0.0.1:3001';
let virtual = false, G = 0, GA = 0, RA = 0;      // G: the recorder's virtual clock, ms; (GA, RA): last anchor, virtual/real
const live = new Set();                           // responses still being delivered in virtual mode
const proxy = httpProxy.createProxyServer({ target: TARGET, ws: true, selfHandleResponse: true });
const flush = r => { while (r.q.length && r.q[0].due <= G) r.res.write(r.q.shift().c);
  if (r.ended && !r.q.length && !r.done) { r.done = true; r.res.end(); live.delete(r); } };
proxy.on('proxyRes', (pres, req, res) => {
  res.writeHead(pres.statusCode, pres.headers);
  if (!req._virtual) { pres.pipe(res); return; }
  const r = { q: [], ended: false, done: false, res, v0: req._v0, r0: req._r0, seen: 0 }; live.add(r);
  pres.on('data', c => { r.seen = Date.now(); r.q.push({ due: req._v0 + (Date.now() - req._r0), c }); flush(r); });
  pres.on('end', () => { r.ended = true; flush(r); });
  pres.on('error', () => { r.ended = true; r.q = []; flush(r); });
});
proxy.on('error', (e, req, res) => { try { res.end(); } catch {} });
http.createServer((req, res) => {
  if (req.url.startsWith('/__vt')) {            // runner: move the virtual clock to t (switches virtual mode on)
    const t = +url.parse(req.url, true).query.t;
    // The clock may not run ahead of the server: while a response is still arriving, virtual time is capped at
    // (its virtual start + the server's real elapsed time). If the runner asks for more, answer only once the server
    // has caught up — so a stream plays at exactly its real pace (or x× with speed: fast), however fast the runner is.
    // A response holds the clock only while it's live: still waiting for its first byte (up to 30 s — a slow generation
    // call), or having sent data in the last 1.5 s. An open-but-idle connection (a finished stream the server keeps
    // open) doesn't hold it.
    // And overall: since the last anchor (recording start, every speed change) the clock never runs ahead of real time —
    // the app also does real-time work the proxy can't see (server jobs, Supabase queries made straight from the browser),
    // and that must play at its true pace too. (speed: fast still compresses the clip: more virtual time per frame.)
    const lag = () => { const now = Date.now(); let need = virtual ? t - (GA + (now - RA)) : 0;
      for (const r of live) if (!r.ended && (r.seen ? now - r.seen < 1500 : now - r.r0 < 30000)) need = Math.max(need, t - (r.v0 + (now - r.r0)));
      return need; };
    const go = () => { const w = Number.isFinite(t) ? lag() : 0; if (w > 1) return setTimeout(go, Math.min(w, 50));
      if (Number.isFinite(t)) { if (!virtual) { GA = t; RA = Date.now(); } virtual = true; G = Math.max(G, t); }
      for (const r of [...live]) flush(r);
      res.end(JSON.stringify({ G, pending: live.size })); };
    go(); return; }
  if (req.url.startsWith('/__anchor')) { GA = G; RA = Date.now(); res.end('anchored'); return; }   // runner: speed changed
  if (req.url.startsWith('/__real')) {          // runner finished: back to a plain proxy, release anything held
    virtual = false; G = Infinity; for (const r of [...live]) flush(r); G = 0; res.end('real'); return; }
  req._virtual = virtual; req._r0 = Date.now(); req._v0 = G;
  proxy.web(req, res);
}).on('upgrade', (req, sock, head) => proxy.ws(req, sock, head)).listen(3000, () => console.log('vproxy up'));
