// reel.json runner: executes a declarative step list against the demo app in STEPPED TIME and writes events.json
// plus a 30 fps clip.mp4. No model in the loop.
// Usage: DEMO_PASSWORD=... node runner.mjs reel.json
//
// How time works while recording: the page's clock (performance.now, Date, timers, requestAnimationFrame) and every
// CSS/Web animation are frozen between frames. Each output frame advances them by exactly 1/30 s (× the speed factor
// during `speed: fast`), fires whatever came due, seeks the animations, then takes one screenshot. A slow screenshot
// therefore can't cause stutter — the page simply waits for it. vproxy.cjs releases the app's responses on the same
// clock (GET /__vt), so generation streams at its real pace (or x× faster when sped up).
import { chromium } from 'playwright'; import fs from 'fs'; import { spawn } from 'child_process';
const reel = JSON.parse(fs.readFileSync(process.argv[2] || 'reel.json', 'utf8'));
const BASE = reel.base || 'http://localhost:3000', OUT = `out/${reel.name}`, SPEED = { x: 5, ...(reel.speed || {}) };
const { w: W, h: H } = reel.viewport || { w: 1320, h: 860 };
const FPS = 30, DT = 1000 / FPS, DPR = reel.dpr || 1.5;          // 1.5× covers the edit's deepest zoom (~1.33× needed)
const T = Date.now(); fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
// Frames are lossless PNG, streamed straight into a near-lossless H.264 encode (nothing written per frame). JPEG frames
// made soft, slowly-animated surfaces (glass panels, glows, text over them) flicker and shift colour from frame to frame.
const enc = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
  '-c:v', 'libx264', '-crf', '10', '-preset', 'medium', '-g', '300', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', `${OUT}/clip.mp4`], { stdio: ['pipe', 'inherit', 'inherit'] });
const encDone = new Promise((res, rej) => enc.on('close', c => c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`))));
const put = buf => new Promise((res, rej) => enc.stdin.write(buf, e => e ? rej(e) : res()));

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DPR, colorScheme: 'dark' });
// optional "hide": [css selectors] — removed from every page (e.g. the floating navbar on quiz/flashcard reels)
if (reel.hide?.length) await ctx.addInitScript(css => {
  const add = () => { const s = document.createElement('style'); s.textContent = css; (document.head || document.documentElement).appendChild(s); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', add) : add();
}, reel.hide.map(sel => `${sel}{display:none!important}`).join('\n'));
await ctx.addInitScript(() => {             // page-side stepped clock; only active once the runner sets sessionStorage.__stepped
  let stepped = false; try { stepped = sessionStorage.getItem('__stepped') === '1'; } catch {}
  if (!stepped) return;
  const pn = performance.now.bind(performance), OD = Date, d0 = OD.now();
  const st = setTimeout, ct = clearTimeout;
  let V = 0;                                 // this document's virtual time, ms (frozen between steps)
  performance.now = () => V;
  function D(...a) { if (!new.target) return new OD(d0 + V).toString(); return a.length ? new OD(...a) : new OD(d0 + V); }
  D.prototype = OD.prototype; D.now = () => d0 + V; D.parse = OD.parse; D.UTC = OD.UTC; Object.setPrototypeOf(D, OD); window.Date = D;
  let seq = 1; const timers = new Map();
  window.setTimeout = (f, ms = 0, ...a) => { if (typeof f !== 'function') return st(f, ms); const id = seq++; timers.set(id, { f, ms: Math.max(0, +ms || 0), rep: false, a, due: V + Math.max(0, +ms || 0) }); return id; };
  window.setInterval = (f, ms = 0, ...a) => { const id = seq++, m = Math.max(1, +ms || 0); timers.set(id, { f, ms: m, rep: true, a, due: V + m }); return id; };
  window.clearTimeout = window.clearInterval = id => { timers.delete(id); };
  let rafQ = [], rafSeq = 1;
  window.requestAnimationFrame = cb => { const id = rafSeq++; rafQ.push({ id, cb }); return id; };
  window.cancelAnimationFrame = id => { rafQ = rafQ.filter(r => r.id !== id); };
  // Smooth scrolling runs on the browser's own clock, so it would never move in frozen time. Programmatic smooth scrolls
  // (scrollTo / scrollBy / scrollIntoView with behavior: 'smooth') are animated here on the virtual clock instead
  // (~0.45 s, eased); CSS scroll-behavior: smooth is switched off, so any other scroll lands instantly.
  const noSmooth = document.createElement('style'); noSmooth.textContent = '*,html{scroll-behavior:auto!important}';
  const addNS = () => (document.head || document.documentElement).appendChild(noSmooth);
  document.documentElement ? addNS() : document.addEventListener('DOMContentLoaded', addNS);
  document.addEventListener('DOMContentLoaded', () => { if (!noSmooth.isConnected) addNS(); });
  const scrollers = el => (el === window || el === document.documentElement || el === document.body) ? document.scrollingElement : el;
  const animScroll = (el, toX, toY) => { const x0 = el.scrollLeft, y0 = el.scrollTop, t0 = V, D = 450;
    const tick = () => { const u = Math.min(1, (V - t0) / D), k = u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
      el.scrollLeft = x0 + (toX - x0) * k; el.scrollTop = y0 + (toY - y0) * k; if (u < 1) window.requestAnimationFrame(tick); };
    window.requestAnimationFrame(tick); };
  const optsOf = (a, b) => typeof a === 'object' && a ? a : { left: a, top: b };
  for (const [obj, isWin] of [[Element.prototype, false], [window, true]]) {
    const oTo = obj.scrollTo, oBy = obj.scrollBy;
    const to = function (a, b) { const o = optsOf(a, b), el = scrollers(isWin ? window : this);
      if (o.behavior !== 'smooth') return oTo.call(this, typeof a === 'object' ? { ...o, behavior: 'instant' } : a, b);
      animScroll(el, o.left ?? el.scrollLeft, o.top ?? el.scrollTop); };
    obj.scrollTo = to; obj.scroll = to;
    obj.scrollBy = function (a, b) { const o = optsOf(a, b), el = scrollers(isWin ? window : this);
      if (o.behavior !== 'smooth') return oBy.call(this, typeof a === 'object' ? { ...o, behavior: 'instant' } : a, b);
      animScroll(el, el.scrollLeft + (o.left || 0), el.scrollTop + (o.top || 0)); };
  }
  const oSIV = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (arg) {
    const o = typeof arg === 'object' && arg ? arg : { block: arg === false ? 'end' : 'start' };
    if (o.behavior !== 'smooth') return oSIV.call(this, { ...o, behavior: 'instant' });
    const chain = []; for (let e = this.parentElement; e; e = e.parentElement) if (e.scrollHeight > e.clientHeight || e.scrollWidth > e.clientWidth) chain.push(e);
    chain.push(document.scrollingElement);
    const before = chain.map(e => [e.scrollLeft, e.scrollTop]);
    oSIV.call(this, { ...o, behavior: 'instant' });                 // find where it lands…
    const after = chain.map(e => [e.scrollLeft, e.scrollTop]);
    chain.forEach((e, i) => { e.scrollLeft = before[i][0]; e.scrollTop = before[i][1]; });   // …then glide there
    chain.forEach((e, i) => { if (after[i][0] !== before[i][0] || after[i][1] !== before[i][1]) animScroll(e, after[i][0], after[i][1]); });
  };
  const anims = new Set();
  // New animations are paused and from then on only move when stepped. One started by JS against our virtual
  // performance.now() (framer-motion does) gets a start time on that clock, but the browser measures it against the
  // real animation timeline, so it shows up with a large NEGATIVE current time — it would wait that long before
  // starting. A negative current time can only come from that mismatch (a real delay is part of the effect's timing,
  // not a negative current time), so such an animation starts from 0.
  const track = () => { for (const a of document.getAnimations()) if (!anims.has(a)) { anims.add(a);
    try { a.pause(); if (a.currentTime == null || a.currentTime < 0) a.currentTime = 0; } catch {} } };
  let dirty = true;
  const watch = () => { new MutationObserver(() => { dirty = true; }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true }); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', watch) : watch();
  addEventListener('scroll', () => { dirty = true; }, true);
  addEventListener('pointermove', () => { dirty = true; }, true);
  window.__step = dt => {                     // advance dt ms; returns whether anything on the page may have changed
    const target = V + dt; let ran = 0;
    for (;;) { let next = null; for (const [id, t] of timers) if (t.due <= target && (!next || t.due < next[1].due)) next = [id, t];
      if (!next) break; const [id, t] = next; V = Math.max(V, t.due);
      if (t.rep) t.due += t.ms; else timers.delete(id); ran++; try { t.f(...t.a); } catch (e) { console.error(e); } }
    V = target;
    const q = rafQ; rafQ = []; ran += q.length; for (const r of q) { try { r.cb(V); } catch (e) { console.error(e); } }
    track();
    // seek each animation; once past its end, finish() it — a paused animation never resolves its `finished` promise on its
    // own, and code awaiting it (e.g. framer-motion's AnimatePresence mode="wait") would wait forever
    const live = new Set(document.getAnimations());
    for (const a of anims) { if (!a.effect || a.playState === 'finished' || !live.has(a)) { anims.delete(a); continue; }
      try { const t = (a.currentTime ?? 0) + dt, end = a.effect.getComputedTiming().endTime; ran++;
        if (Number.isFinite(end) && t >= end) { a.finish(); anims.delete(a); } else a.currentTime = t; } catch {} }
    const d = dirty || ran > 0; dirty = false; return d;
  };
});
const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p);
await cdp.send('Animation.enable');
// the direct screenshot call ignores the context's pixel density unless it's set on the page explicitly
await cdp.send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: DPR, mobile: false });
p.setDefaultTimeout(600000);
let stepping = false;
const freezeAnims = () => stepping && cdp.send('Animation.setPlaybackRate', { playbackRate: 0 }).catch(() => {});
p.on('domcontentloaded', freezeAnims); p.on('load', freezeAnims);
// While a main-frame navigation is in flight the browser won't run anything in the old document (an evaluate or a
// screenshot just hangs), and the new document can't arrive until the clock moves. So during it we only advance the
// clock, and the clip holds its last frame; stepping resumes once the new document has taken over.
let navPending = false;
p.on('request', r => { if (r.isNavigationRequest() && r.frame() === p.mainFrame()) navPending = true; });
p.on('framenavigated', f => { if (f === p.mainFrame()) navPending = false; });
p.on('requestfailed', r => { if (r.isNavigationRequest() && r.frame() === p.mainFrame()) navPending = false; });

// ── frames ──
let n = 0, G = 0, rate = 1, capturing = false, last = null, shots = 0, maxShotMs = 0, mx = W / 2, my = H * 0.8;
const events = [], mouse = [];   // mouse: [frame, x, y] for every output frame (the real pointer path)
const tOut = () => +(n / FPS).toFixed(4);
const ev = (type, extra = {}) => { events.push({ type, t: tOut(), ...extra }); console.log(type, tOut().toFixed(2), `real ${((Date.now() - T) / 1000).toFixed(0)}s`); };
// a call into the page that doesn't answer within 2 s real time (a navigation just started) is skipped for this frame
const within = (pr, fallback, ms = 2000) => Promise.race([pr.catch(() => fallback), new Promise(r => setTimeout(() => r(fallback), ms))]);
const frame = async (force = false) => {
  const dt = DT * rate; G += dt;
  await fetch(`${BASE}/__vt?t=${G.toFixed(3)}`).catch(() => {});
  // CDP evaluate runs in whatever document is current right now; page.evaluate would wait for a pending navigation,
  // which itself waits for this clock to move (the proxy holds the response) — a deadlock
  const changed = navPending ? false : await within(cdp.send('Runtime.evaluate', { expression: `window.__step ? window.__step(${dt}) : true`, returnByValue: true })
    .then(r => r.result?.value !== false), true);
  if (!capturing) return;
  if (!navPending && (force || changed || !last)) { const t0 = Date.now(); const shot = await within(cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true }), null); if (shot) last = Buffer.from(shot.data, 'base64');
    shots++; maxShotMs = Math.max(maxShotMs, Date.now() - t0); }
  mouse.push([n, +mx.toFixed(1), +my.toFixed(1)]);
  await put(last); n++;
};
const holdMs = async ms => { const k = Math.max(0, Math.round(ms / (DT * rate))); for (let i = 0; i < k; i++) await frame(); };   // ms of APP time
const until = async (cond, what, maxMs = 120000) => { const t0 = G; while (!(await cond().catch(() => false))) { if (G - t0 > maxMs) throw new Error(`timed out waiting for ${what}`); await frame(); } };

// ── targets, cursor, scrolling ──
const loc = t => t.css ? p.locator(t.css).first() : t.role ? p.getByRole(t.role, { name: new RegExp(t.name) }).first() : p.getByText(t.text).first();
const box = async l => { const bb = await l.boundingBox(); return bb && { x: bb.x, y: bb.y, w: bb.width, h: bb.height }; };
const visible = l => async () => (await l.count()) > 0 && await l.isVisible();
const rnd = (a, c) => a + Math.random() * (c - a);
// stepped scroll of the page (or the largest scrollable element), eased, one position per output frame
// `to`: 'bottom' | 'top' scrolls exactly to that end of the container (dy is ignored), e.g. to reveal a whole overflowing outline
const steppedScroll = async (dy, ms, page, to) => {
  const d = await p.evaluate(([page, to]) => { let el = document.scrollingElement;
    if (!page) { const els = [...document.querySelectorAll('*')].filter(e => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight + 50; });
      // inside an open dialog, scroll the dialog (not the page behind it)
      const dlg = document.querySelector('[role=dialog]'); const pool = dlg ? els.filter(e => dlg.contains(e)) : els;
      el = (pool.length ? pool : els).sort((a, c) => c.clientHeight - a.clientHeight)[0] || el; }
    window.__sEl = el; window.__sY0 = el.scrollTop;
    return to === 'bottom' ? el.scrollHeight - el.clientHeight - el.scrollTop : to === 'top' ? -el.scrollTop : null; }, [!!page, to || null]);
  if (d != null) dy = d;
  const k = Math.max(1, Math.round(ms / 1000 * FPS / rate));   // in a sped-up stretch scrolls are sped up too
  for (let i = 1; i <= k; i++) {
    await p.evaluate(([dy, u]) => { const e = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; window.__sEl.scrollTop = window.__sY0 + dy * e(u); }, [dy, i / k]);
    await frame(true); } };
const ensureVisible = async l => { const bb = await box(l); if (!bb || (bb.y >= 0 && bb.y + bb.h <= H)) return;
  if (await l.evaluate(e => { for (; e; e = e.parentElement) if (getComputedStyle(e).position === 'fixed') return true; return false; }).catch(() => true)) return;
  const margin = 90; let dy = 0;
  if (bb.y + bb.h > H - margin) dy = Math.min(bb.y + bb.h - H + margin + 40, bb.y - margin);
  else if (bb.y < margin) dy = bb.y - margin - 40;
  if (Math.abs(dy) < 4) return;
  const page = await p.evaluate(() => document.scrollingElement.scrollHeight > innerHeight + 50);
  ev('scroll', { dy, ms: 900, auto: true }); await steppedScroll(dy, Math.min(1300, 600 + Math.abs(dy) * 0.9), page); await holdMs(250); };
// The real mouse glides to the target one step per frame (so hover states play exactly as a person would trigger them),
// on the same schedule the edit's drawn cursor uses: Fitts-law travel time, sine ease, arriving before the click.
const travel = d => Math.min(0.7, 0.25 + 0.12 * Math.log2(1 + d / 60)) * 1000;
const glide = async (x, y) => { const x0 = mx, y0 = my, d = Math.hypot(x - x0, y - y0); if (d < 1) return;
  const k = Math.max(rate > 1 ? 1 : 2, Math.round(travel(d) / (DT * rate)));   // in a sped-up stretch the hand moves faster too
  for (let i = 1; i <= k; i++) { const u = (1 - Math.cos(Math.PI * i / k)) / 2; mx = x0 + (x - x0) * u; my = y0 + (y - y0) * u; await p.mouse.move(mx, my); await frame(true); } };
const moveTo = async (l, what = 'target') => { await until(visible(l), `${what} to appear`, 20000); await ensureVisible(l); const bb = await box(l); await glide(bb.x + bb.w / 2, bb.y + bb.h / 2); return bb; };
// navigate without blocking: responses only arrive as virtual time moves, so keep stepping until the URL changes
const nav = async (to, re) => { navPending = true; p.goto(to, { waitUntil: 'commit' }).catch(() => {}); await until(async () => re.test(p.url()), to, 30000); await freezeAnims(); };
const press = async () => { await p.mouse.down(); await frame(); if (rate === 1) await frame(); await p.mouse.up(); await frame(); };   // 3 frames, 2 when sped up

const steps = {
  pause: async s => holdMs(s.ms),
  // speed: fast plays the app x× faster in the clip (default SPEED.x = 5); normal restores real pace
  speed: async s => { rate = s.k === 'normal' ? 1 : Math.max(1, s.x ?? SPEED.x); await fetch(`${BASE}/__anchor`).catch(() => {}); ev('speed', { k: s.k, F: rate }); },
  mark: async () => {},
  hover: async s => { await moveTo(loc(s.target), JSON.stringify(s.target)); },
  click: async s => { const l = loc(s.target); const bb = await moveTo(l, JSON.stringify(s.target)); await holdMs(s.dwell ?? 140);
    const href = s.expect_url ? await l.getAttribute('href').catch(() => null) : null;
    ev('click', { target: s.as || JSON.stringify(s.target), box: bb }); await press();
    // "cut": true on a click that navigates edits out everything until the new page has loaded (the frozen old page)
    if (s.cut) { capturing = false; last = null; }
    // a link that should navigate: give it 4 s, then load its href directly. A button with no href (e.g. Generate)
    // isn't waited on here — the script's next `wait` step covers it, so a following `speed` step applies to the wait
    if (s.expect_url && href) { const re = new RegExp(s.expect_url);
      try { await until(async () => re.test(p.url()), s.expect_url, 4000); }
      catch { ev('nav_fallback', { href }); await nav(BASE + href, re); } }
    if (s.cut) { const n0 = G; if (s.expect_url) await steps.wait({ for: { load: true } }); await holdMs(s.settle ?? 400);
      capturing = true; last = null; ev('cut', { removed: +((G - n0) / 1000).toFixed(3) }); } },
  type: async s => { const keys = [];
    for (const ch of s.text) { await p.keyboard.type(ch); keys.push(tOut());
      let d = rnd(32, 62); if (ch === ' ') d += rnd(40, 110); if (',—-/.'.includes(ch)) d += rnd(120, 220); if (ch !== ' ' && Math.random() < 0.04) d += rnd(150, 260);
      await holdMs(d); }
    ev('keys', { times: keys, text: s.text }); },
  wait: async s => { if (s.cut) {             // edit out dead time (loading/blank transitions): keep stepping, stop saving frames
      capturing = false; const n0 = G; await steps.wait({ ...s, cut: false }); await holdMs(s.settle ?? 400);
      capturing = true; last = null; ev('cut', { removed: +((G - n0) / 1000).toFixed(3) });
      return; }
    const f = s.for;
    if (f.load) { await until(async () => !navPending && (await within(cdp.send('Runtime.evaluate', { expression: 'document.readyState', returnByValue: true }).then(r => r.result?.value), null)) === 'complete', 'page load');
      let quiet = 0, t0 = G;                   // then until the proxy has nothing in flight for 0.3 s (max 6 s)
      while (quiet < 0.3 * FPS && G - t0 < 6000) { const r = await fetch(`${BASE}/__vt?t=${G.toFixed(3)}`).then(r => r.json()).catch(() => ({ pending: 0 }));
        quiet = r.pending ? 0 : quiet + 1; await frame(); } }
    else if (f.url) await until(async () => new RegExp(f.url).test(p.url()), f.url);
    else if (f.enabled) { const l = loc(f.enabled); await until(async () => (await visible(l)()) && await l.isEnabled(), 'button to be enabled'); }
    else await until(visible(loc(f)), JSON.stringify(f)); },
  press: async s => { if (s.target) { const l = loc(s.target); const bb = await moveTo(l); await holdMs(140); ev('click', { target: s.as || 'press', box: bb }); await press(); }
    for (let i = 0; i < (s.times || 1); i++) { await p.keyboard.press(s.key); ev('press', { key: s.key }); await holdMs(s.gap ?? 260); } },
  scroll: async s => { ev('scroll', { dy: s.dy, ms: s.ms, to: s.to }); await steppedScroll(s.dy ?? 0, s.ms, s.page, s.to); },
};

// login (real time, not recorded)
await fetch(`${BASE}/__real`).catch(() => {});          // a crashed earlier run may have left the proxy on the virtual clock
await p.goto(BASE + '/auth/login', { waitUntil: 'networkidle' });
await p.fill('input[type="email"]', reel.account || 'john.doe@the-memora.com'); await p.fill('input[type="password"]', process.env.DEMO_PASSWORD);
await p.locator('button[type=submit]').first().click(); await p.waitForURL(u => !u.pathname.startsWith('/auth'));
// switch to stepped time: from here every document starts frozen, and the proxy delivers on the virtual clock
await p.evaluate(() => sessionStorage.setItem('__stepped', '1')); stepping = true;
await fetch(`${BASE}/__vt?t=0`).catch(() => {});
const esc = x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
await nav(BASE + reel.start_url, new RegExp('^' + esc(BASE + reel.start_url) + '([?#]|$)'));
await steps.wait({ for: { load: true } }); await holdMs(1500);       // load + settle, not recorded

// record
capturing = true; await p.mouse.move(mx, my);
ev('rec_start');
for (const s of reel.steps) { await steps[s.do](s);
  // "box": target on a marked step records where that element is on screen right then (beats can frame it: region "box")
  if (s.mark) { const bb = s.box ? await within(box(loc(s.box)), null) : null;
    if (s.box && !bb) throw new Error(`step "${s.mark}": its box target ${JSON.stringify(s.box)} is not on the page`);
    ev(s.mark, bb ? { box: bb } : {}); } }
await frame(); ev('rec_end');
fs.writeFileSync(`${OUT}/mouse.json`, JSON.stringify(mouse));
fs.writeFileSync(`${OUT}/events.json`, JSON.stringify({ reel: reel.name, viewport: { w: W, h: H }, dpr: DPR, fps: FPS, frames: n, events }, null, 1));
await b.close(); await fetch(`${BASE}/__real`).catch(() => {});
enc.stdin.end(); await encDone;   // near-lossless, long keyframe spacing: the edit re-encodes this clip, so it must not add its own pulsing
const real = (Date.now() - T) / 1000;
fs.writeFileSync(`${OUT}/capture.json`, JSON.stringify({ frames: n, clip_s: +(n / FPS).toFixed(2), screenshots: shots, reused: n - shots, slowest_screenshot_ms: maxShotMs, real_s: +real.toFixed(1) }, null, 1));
console.log(`DONE ${OUT}/clip.mp4 — ${n} frames, ${(n / FPS).toFixed(1)}s video, ${shots} screenshots (${n - shots} reused), ${real.toFixed(0)}s real`);
