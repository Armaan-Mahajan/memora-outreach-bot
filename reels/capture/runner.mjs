// reel.json runner: executes a declarative step list against memora-demo with time-dilated,
// native-2x capture, then writes events.json and a 30 fps clip.mp4. No model in the loop.
// Usage: DEMO_PASSWORD=... node runner.mjs reel.json
import { chromium } from 'playwright'; import fs from 'fs'; import { execFileSync } from 'child_process';
const reel = JSON.parse(fs.readFileSync(process.argv[2] || 'reel.json', 'utf8'));
const BASE = reel.base || 'http://localhost:3000', OUT = `out/${reel.name}`, SPEED = reel.speed || { normal: 11, fast: 3 };
const { w: W, h: H } = reel.viewport || { w: 1320, h: 860 };
const T = Date.now(); fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT + '/frames', { recursive: true });

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: 'dark' });
// optional "hide": [css selectors] — removed from every page (e.g. the floating navbar on quiz/flashcard reels)
if (reel.hide?.length) await ctx.addInitScript(css => {
  const add = () => { const s = document.createElement('style'); s.textContent = css; (document.head || document.documentElement).appendChild(s); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', add) : add();
}, reel.hide.map(sel => `${sel}{display:none!important}`).join('\n'));
await ctx.addInitScript(() => {            // page-side virtual clock
  const pn = performance.now.bind(performance), dn = Date.now, OD = Date; const d0 = dn(), p0 = pn();
  const vc = { K: 1, rb: pn(), vb: pn() };
  performance.now = () => vc.vb + (pn() - vc.rb) / vc.K;
  window.__setK = k => { vc.vb = performance.now(); vc.rb = pn(); vc.K = k; };
  const vnow = () => d0 + (performance.now() - p0);
  function D(...a) { if (!new.target) return new OD(vnow()).toString(); return a.length ? new OD(...a) : new OD(vnow()); }
  D.prototype = OD.prototype; D.now = vnow; D.parse = OD.parse; D.UTC = OD.UTC; Object.setPrototypeOf(D, OD); window.Date = D;
  const st = setTimeout, si = setInterval, raf = requestAnimationFrame.bind(window);
  window.setTimeout = (f, ms = 0, ...r) => st(f, (+ms || 0) * vc.K, ...r);
  window.setInterval = (f, ms = 0, ...r) => si(f, (+ms || 0) * vc.K, ...r);
  window.requestAnimationFrame = cb => raf(() => cb(performance.now()));
});
const p = await ctx.newPage(); const cdp = await ctx.newCDPSession(p); await cdp.send('Animation.enable');
p.setDefaultTimeout(600000);

let K = 1, rb = Date.now(), vb = 0; const vt = () => vb + (Date.now() - rb) / 1000 / K;
const applyK = () => Promise.all([p.evaluate(k => window.__setK && window.__setK(k), K).catch(() => {}),
  cdp.send('Animation.setPlaybackRate', { playbackRate: 1 / K }).catch(() => {})]);
const setK = async k => { vb = vt(); rb = Date.now(); K = k; await Promise.all([applyK(), fetch(BASE + '/__k?k=' + k).catch(() => {})]); };
p.on('load', () => { applyK(); });
const sleep = ms => new Promise(r => setTimeout(r, ms * K));
const frames = [], events = []; let rec = false, loopP;
const ev = (type, extra = {}) => { const t = +vt().toFixed(4); events.push({ type, t, K, ...extra }); console.log(type, t.toFixed(2), `K=${K}`, `real ${((Date.now() - T) / 1000).toFixed(0)}s`); };
const box = async l => { const bb = await l.boundingBox(); return bb && { x: bb.x, y: bb.y, w: bb.width, h: bb.height }; };
const loc = t => t.css ? p.locator(t.css).first() : t.role ? p.getByRole(t.role, { name: new RegExp(t.name) }).first() : p.getByText(t.text).first();
const rnd = (a, c) => a + Math.random() * (c - a);
// bring an off-screen target into view with a smooth, frame-stepped scroll (instead of Playwright's instant jump)
const ensureVisible = async l => { const bb = await box(l); if (!bb || (bb.y >= 0 && bb.y + bb.h <= H)) return;   // only when (partly) off-screen
  if (await l.evaluate(e => { for (; e; e = e.parentElement) if (getComputedStyle(e).position === 'fixed') return true; return false; }).catch(() => true)) return;
  const margin = 90; let dy = 0;
  if (bb.y + bb.h > H - margin) dy = Math.min(bb.y + bb.h - H + margin + 40, bb.y - margin);
  else if (bb.y < margin) dy = bb.y - margin - 40;
  if (Math.abs(dy) < 4) return;
  const page = await p.evaluate(() => document.scrollingElement.scrollHeight > innerHeight + 50);
  ev('scroll', { dy, ms: 900, auto: true }); await steppedScroll(dy, Math.min(1300, 600 + Math.abs(dy) * 0.9), page); await sleep(250); };
const moveTo = async l => { await ensureVisible(l); const bb = await box(l); await p.mouse.move(bb.x + bb.w / 2, bb.y + bb.h / 2, { steps: 15 }); return bb; };
const shot = async t => { const buf = await p.screenshot({ type: 'jpeg', quality: 90, scale: 'device', caret: 'initial', animations: 'allow' });
  const fn = String(frames.length).padStart(5, '0') + '.jpg'; fs.writeFileSync(`${OUT}/frames/${fn}`, buf); frames.push({ fn, t: +t.toFixed(4), K }); };
const startLoop = () => { rec = true; loopP = (async () => { while (rec) { const a = vt(); const buf = await p.screenshot({ type: 'jpeg', quality: 90, scale: 'device', caret: 'initial', animations: 'allow' });
  const t = (a + vt()) / 2, fn = String(frames.length).padStart(5, '0') + '.jpg'; fs.writeFileSync(`${OUT}/frames/${fn}`, buf); frames.push({ fn, t: +t.toFixed(4), K }); } })(); };
const stopLoop = async () => { rec = false; await loopP; };
// Frame-stepped scroll: pause free-running capture, then for each 1/30 s set the exact eased scroll position,
// wait two animation frames so the page has fully painted, and take exactly one screenshot. No sampling → no judder/tearing.
const steppedScroll = async (dy, ms, page) => {
  await stopLoop(); const t0 = vt(), n = Math.max(1, Math.round(ms / 1000 * 30));
  await p.evaluate(page => { let el = document.scrollingElement;
    if (!page) { const els = [...document.querySelectorAll('*')].filter(e => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.scrollHeight > e.clientHeight + 50; });
      el = els.sort((a, c) => c.clientHeight - a.clientHeight)[0] || el; }
    window.__sEl = el; window.__sY0 = el.scrollTop; }, !!page);
  for (let i = 1; i <= n; i++) {
    await p.evaluate(async ([dy, k]) => { const e = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
      window.__sEl.scrollTop = window.__sY0 + dy * e(k); await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }, [dy, i / n]);
    await shot(t0 + i / 30); }
  vb = t0 + n / 30; rb = Date.now();                 // virtual clock advances exactly the scroll's duration
  await applyK(); startLoop(); };

const steps = {
  pause: async s => sleep(s.ms),
  speed: async s => { await setK(SPEED[s.k] ?? s.k); },
  mark: async () => {},
  hover: async s => { const l = loc(s.target); await l.waitFor(); await moveTo(l); },
  click: async s => { const l = loc(s.target); await l.waitFor(); const bb = await moveTo(l); await sleep(s.dwell ?? 220);
    const href = s.expect_url ? await l.getAttribute('href').catch(() => null) : null;
    ev('click', { target: s.as || JSON.stringify(s.target), box: bb }); await l.click({ timeout: 5000 * K }).catch(() => {});
    if (s.expect_url) { const re = new RegExp(s.expect_url);
      await Promise.race([p.waitForURL(re).catch(() => {}), sleep(1500)]);
      if (!re.test(p.url()) && href) { ev('nav_fallback', { href }); await p.goto(BASE + href); } } },
  type: async s => { const keys = [];
    for (const ch of s.text) { await p.keyboard.type(ch); keys.push(+vt().toFixed(4));
      let d = rnd(32, 62); if (ch === ' ') d += rnd(40, 110); if (',—-/.'.includes(ch)) d += rnd(120, 220); if (ch !== ' ' && Math.random() < 0.04) d += rnd(150, 260);
      await sleep(d); }
    ev('keys', { times: keys, text: s.text }); },
  wait: async s => { if (s.cut) {             // edit out dead time (loading/blank transitions): stop capturing, wait, settle, rewind the clock
      await stopLoop(); const a = vt(); await steps.wait({ ...s, cut: false }); await sleep(s.settle ?? 400);
      const removed = +(vt() - a).toFixed(3); vb = a; rb = Date.now(); ev('cut', { removed }); await applyK(); startLoop(); return; }
    const f = s.for;
    if (f.load) { await p.waitForLoadState('load'); await p.waitForLoadState('networkidle', { timeout: 6000 * K }).catch(() => {}); }
    else if (f.url) await p.waitForURL(new RegExp(f.url));
    else if (f.enabled) { const l = loc(f.enabled); await l.waitFor(); while (!(await l.isEnabled())) await p.waitForTimeout(100); }
    else await loc(f).waitFor(); },
  press: async s => { if (s.target) { const l = loc(s.target); await l.waitFor(); const bb = await moveTo(l); await sleep(180); ev('click', { target: s.as || 'press', box: bb }); await l.click(); }
    for (let i = 0; i < (s.times || 1); i++) { await p.keyboard.press(s.key); ev('press', { key: s.key }); await sleep(s.gap ?? 260); } },
  scroll: async s => { ev('scroll', { dy: s.dy, ms: s.ms }); await steppedScroll(s.dy, s.ms, s.page); },
};

// login + start page (not recorded)
await p.goto(BASE + '/auth/login', { waitUntil: 'networkidle' });
await p.fill('input[type="email"]', reel.account || 'john.doe@the-memora.com'); await p.fill('input[type="password"]', process.env.DEMO_PASSWORD);
await p.locator('button[type=submit]').first().click(); await p.waitForURL(u => !u.pathname.startsWith('/auth'));
await p.goto(BASE + reel.start_url, { waitUntil: 'load' }); await p.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {}); await p.waitForTimeout(1500);

// record
await setK(SPEED.normal); startLoop();
ev('rec_start');
for (const s of reel.steps) { await steps[s.do](s); if (s.mark) ev(s.mark); }
ev('rec_end'); await stopLoop();
fs.writeFileSync(`${OUT}/events.json`, JSON.stringify({ reel: reel.name, viewport: { w: W, h: H }, dpr: 2, speed: SPEED, events, frames }, null, 1));
await b.close();

// resample to constant 30 fps and encode
const t0 = events[0].t, t1 = events.at(-1).t; fs.mkdirSync(`${OUT}/cfr`, { recursive: true });
let j = 0; const n = Math.floor((t1 - t0) * 30);
for (let i = 0; i < n; i++) { const t = t0 + i / 30; while (j + 1 < frames.length && frames[j + 1].t <= t) j++;
  fs.symlinkSync(fs.realpathSync(`${OUT}/frames/${frames[j].fn}`), `${OUT}/cfr/${String(i).padStart(5, '0')}.jpg`); }
execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-framerate', '30', '-i', `${OUT}/cfr/%05d.jpg`,
  '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', `${OUT}/clip.mp4`]);
console.log(`DONE ${OUT}/clip.mp4 — ${frames.length} frames, ${(t1 - t0).toFixed(1)}s video, ${((Date.now() - T) / 1000).toFixed(0)}s real`);
