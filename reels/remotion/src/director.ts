// director.ts — turns a runner events.json into a per-frame camera + cursor track.
// Pure and deterministic: same events in → same video out. All coordinates are page CSS px
// (the runner's 1320×860 viewport); `s` is output px per CSS px inside the app card.
//
// ─── CAMERA RULES ────────────────────────────────────────────────────────────────
// 1. Every shot is a region of the page. The camera frames it with 12% padding:
//      s = clamp(min(card.w / padded.w, card.h / padded.h), S_WIDE, S_MAX)
//    S_WIDE = the smallest zoom that still fills the card; S_MAX = 2.0 (1:1 with the 2× capture).
// 2. Shots come from events (see buildShots). Clicks are ANTICIPATED (camera arrives LEAD s
//    before the click); things the app does in response (dialog opens, toast, new page) are
//    REACTED to (camera moves REACT s after they appear).
// 3. Typing gets a READ zoom (S_TYPE) and the camera follows the caret.
// 4. Long holds (> 3 s) get a slow 6% push-in so the frame never feels frozen.
// 5. A far jump (pan > 55% of the visible width) dips out to a wider zoom halfway, so the
//    viewer keeps their bearings instead of seeing a whip-pan.
// 6. Motion = the shot targets passed through TWO cascaded critically-damped springs on
//    (cx, cy, log s): S-shaped ease-in/ease-out, no overshoot, never a hard cut.
//    Zoom is smoothed in log space so zooming in and out feel equally fast.
// 7. The visible rect is always clamped inside the page — never shows past the app's edges.
//
// ─── CURSOR RULES ────────────────────────────────────────────────────────────────
// 1. The cursor is drawn (the capture has none). It travels to each click target on a
//    gentle curve (quadratic Bézier, bow = 14% of the distance, alternating sides).
// 2. Travel time follows Fitts' law: 0.32 s + 0.14 s·log2(1 + d/60), capped at 0.85 s,
//    eased in-out, and it ARRIVES 0.14 s before the click (a human settles, then clicks).
// 3. Click: cursor dips to 82% for 90 ms + a brand-violet ring expands from the tip (0.45 s).
// 4. While typing, the cursor fades out (0.25 s) and returns when it next moves.
// 5. When stationary for > 0.8 s it drifts a pixel or two, so it looks held, not pasted.
// 6. Size is ~36 px on screen at a typical zoom and grows only gently with zoom (^0.35).

export type Box = { x: number; y: number; w: number; h: number };
export type Ev = { type: string; t: number; box?: Box; times?: number[]; text?: string; target?: string };
export type Regions = Record<string, Box>;
// Per-reel beats: frame `region` (a page box, 'WIDE', or 'click' = the click target with context)
// at event `ev` (an event type or 'click:<target>'), the i-th occurrence (or every one, i = 'all'), offset dt seconds.
export type Beat = { ev: string; i?: number | 'all'; dt?: number; region: Box | 'WIDE' | 'click'; s?: number };
export type Cam = { cx: number; cy: number; s: number; h: number };
export type Cur = { x: number; y: number; opacity: number; press: number };
export type Ripple = { t: number; x: number; y: number };

export const PAGE = { w: 1320, h: 860 };
export const S_MAX = 2.0, S_TYPE = 1.75, LEAD = 0.45, REACT = 0.15, PAD = 0.12;
// ─── VARIABLE-HEIGHT WINDOW ──────────────────────────────────────────────────────
// Unzoomed, the window shows the WHOLE app (fit to width, no crop) → height = page.h × s_wide.
// As the camera zooms in, the window grows taller (smoothstep) until it reaches H_MAX at S_FULL,
// so zoomed shots get more vertical context instead of a letterbox.
export const H_MAX = 1640, S_FULL = 1.6;
export const cardH = (s: number, w: number, hMax = H_MAX) => { const sw = w / PAGE.w, h0 = PAGE.h * sw;
  const k = Math.min(1, Math.max(0, (s - sw) / (S_FULL - sw))), e = k * k * (3 - 2 * k); return h0 + (hMax - h0) * e; };

type Shot = { t: number; cx: number; cy: number; s: number; hCap?: number };

export function direct(events: Ev[], regions: Regions, card: { w: number; hMax?: number }, fps: number, t0: number, dur: number, beats: Beat[] = []) {
  const HM = card.hMax ?? H_MAX; const S_WIDE = card.w / PAGE.w; const H = (s: number) => cardH(s, card.w, HM);
  const ev = events.map(e => ({ ...e, t: e.t - t0, times: e.times?.map(x => x - t0) }));
  const find = (type: string, i = 0) => ev.filter(e => e.type === type)[i];
  const clicks = ev.filter(e => e.type === 'click');
  const center = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 });
  const fit = (b: Box, sMax = S_MAX): Omit<Shot, 't'> => {
    const pw = b.w * (1 + 2 * PAD), ph = b.h * (1 + 2 * PAD);
    let s = sMax; while (s > S_WIDE && (pw * s > card.w || ph * s > H(s))) s -= 0.005;   // largest zoom whose window fits it
    s = Math.max(s, S_WIDE); const c = center(b);
    return { cx: c.x, cy: c.y, s, hCap: ph * s };       // window never taller than the framed region needs
  };
  const WIDE = { cx: PAGE.w / 2, cy: PAGE.h / 2, s: S_WIDE };

  // ── shots from events ──
  const shots: Shot[] = [{ t: 0, ...WIDE }];
  const keySegs = ev.filter(e => e.type === 'keys' && e.times?.length);
  const keys = keySegs[0];
  for (const k of keySegs) {          // every typing burst: read-zoom on the field it went into, following the caret
    const c = [...clicks].reverse().find(c => c.t <= k.times![0] && c.box); if (!c?.box) continue;
    const b = c.box, visW = card.w / S_TYPE, multi = c.target === 'textarea', cy = multi ? b.y + 100 : b.y + b.h / 2, cw = 7.4;
    shots.push({ t: c.t - LEAD, cx: b.x - 40 + visW / 2, cy, s: S_TYPE });
    for (let i = 0; i < k.times!.length; i += 6) {
      const caretX = b.x + (multi ? 20 : 14) + cw * (i + 1), left = Math.max(b.x - 40, caretX - 0.65 * visW);
      shots.push({ t: k.times![i], cx: left + visW / 2, cy, s: S_TYPE });
    }
  }
  const gen = clicks.find(c => c.target === 'generate');
  if (gen?.box) { const c = center(gen.box); shots.push({ t: gen.t - LEAD, cx: c.x - 120, cy: c.y - 20, s: S_TYPE }); }
  const oOpen = find('outline_open'), oDone = find('outline_done');
  if (oOpen && regions.dialog) shots.push({ t: oOpen.t + REACT, ...fit(regions.dialog) });
  if (oDone && regions.outline) shots.push({ t: oDone.t + REACT + 0.2, ...fit(regions.outline) });
  const pro = clicks.find(c => c.target === 'proceed');
  if (pro?.box) shots.push({ t: pro.t - LEAD, ...fit({ ...pro.box, x: pro.box.x - 260, w: pro.box.w + 300, y: pro.box.y - 120, h: pro.box.h + 160 }) });
  const cgs = find('course_gen_start');
  if (cgs && regions.outline) shots.push({ t: cgs.t + REACT + 0.25, ...fit(regions.outline) });
  const cgd = find('course_gen_done');
  if (cgd && regions.toast) shots.push({ t: cgd.t + REACT, ...fit(regions.toast, 1.9) });
  const vo = find('viewer_open');
  if (vo && regions.content) shots.push({ t: vo.t + 0.3, ...fit(regions.content) });
  // generic rule for creation flows (quiz, flashcards): when the results page opens, frame its results column
  const ro = find('results_open');
  if (ro) shots.push({ t: ro.t + REACT + 0.25, ...(regions.results ? fit(regions.results) : WIDE) });
  for (const bt of beats) {
    const pool = bt.ev.startsWith('click:') ? clicks.filter(c => c.target === bt.ev.slice(6)) : ev.filter(e => e.type === bt.ev);
    const hits = bt.i === 'all' ? pool : [pool[bt.i ?? 0]].filter(Boolean);
    for (const e of hits) { const dt = bt.dt ?? (e.type === 'click' ? -LEAD : REACT);
      let r: Omit<Shot, 't'>;
      if (bt.region === 'WIDE') r = WIDE;
      else if (bt.region === 'click') { if (!e.box) continue; const c = center(e.box); r = fit({ x: c.x - 300, y: c.y - 170, w: 600, h: 340 }, bt.s ?? S_MAX); }
      else r = fit(bt.region, bt.s ?? S_MAX);
      shots.push({ t: e.t + dt, ...r }); }
  }
  const end = find('rec_end');
  shots.push({ t: (end ? end.t : dur) - 1.4, ...WIDE });
  shots.sort((a, b) => a.t - b.t);

  // rule 4: slow push-in on long holds
  const withHolds: Shot[] = [];
  shots.forEach((sh, i) => { withHolds.push(sh); const next = shots[i + 1];
    if (next && next.t - sh.t > 3 && sh.s < S_MAX) withHolds.push({ ...sh, t: next.t - 0.05, s: Math.min(sh.s * 1.06, S_MAX) }); });
  // rule 5: dip out on far jumps
  const plan: (Shot & { ramp?: boolean })[] = [];
  withHolds.forEach((sh, i) => { const prev = plan[plan.length - 1];
    if (prev) { const visW = card.w / prev.s, d = Math.hypot(sh.cx - prev.cx, sh.cy - prev.cy);
      if (d > 0.55 * visW && sh.t - prev.t > 0.5) plan.push({ t: sh.t - 0.28, cx: (sh.cx + prev.cx) / 2, cy: (sh.cy + prev.cy) / 2, s: Math.max(S_WIDE, Math.min(prev.s, sh.s) * 0.8) }); }
    plan.push(sh); });
  // targets that ramp linearly (hold push-ins) vs step (everything else)
  const target = (t: number) => { let i = 0; while (i + 1 < plan.length && plan[i + 1].t <= t) i++;
    const a = plan[i], b = plan[i + 1];
    if (b && b.cx === a.cx && b.cy === a.cy && b.s !== a.s && b.t - a.t > 3) { const k = (t - a.t) / (b.t - a.t); return { cx: a.cx, cy: a.cy, ls: Math.log(a.s) + k * (Math.log(b.s) - Math.log(a.s)), hc: a.hCap ?? 9999 }; }
    return { cx: a.cx, cy: a.cy, ls: Math.log(a.s), hc: a.hCap ?? 9999 }; };

  // rule 6: two cascaded critically-damped springs (ω = 8.5 rad/s each), 4 substeps/frame
  const N = Math.round(dur * fps), W = 8.5, sub = 4, dt = 1 / fps / sub;
  // hc (window-height cap) is smoothed too, clamped to the real range so the spring never chases 9999
  const clampH = (o: any) => ({ ...o, hc: Math.min(o.hc, HM) });
  const st0 = clampH(target(0)); const s1 = { ...st0 }, v1 = { cx: 0, cy: 0, ls: 0, hc: 0 }, s2 = { ...st0 }, v2 = { cx: 0, cy: 0, ls: 0, hc: 0 };
  const cam: Cam[] = [];
  for (let f = 0; f < N; f++) {
    for (let k = 0; k < sub; k++) { const tg = clampH(target(f / fps + k * dt));
      for (const key of ['cx', 'cy', 'ls', 'hc'] as const) {
        v1[key] += (-2 * W * v1[key] - W * W * (s1[key] - tg[key])) * dt; s1[key] += v1[key] * dt;
        v2[key] += (-2 * W * v2[key] - W * W * (s2[key] - s1[key])) * dt; s2[key] += v2[key] * dt; } }
    let s = Math.exp(s2.ls); s = Math.min(Math.max(s, S_WIDE), S_MAX);
    const h = Math.max(PAGE.h * S_WIDE, Math.min(H(s), s2.hc));   // zoom-based height, capped by the shot's need
    const vw = card.w / s, vh = h / s;               // rule 7: clamp inside the page
    const cx = Math.min(Math.max(s2.cx, vw / 2), PAGE.w - vw / 2), cy = Math.min(Math.max(s2.cy, vh / 2), PAGE.h - vh / 2);
    cam.push({ cx, cy, s, h });
  }

  // ── cursor ──
  type Way = { t: number; x: number; y: number; click: boolean };
  const ways: Way[] = [];
  for (const c of clicks) { if (!c.box) continue;
    const p = c.target === 'textarea' ? { x: c.box.x + c.box.w * 0.3, y: c.box.y + 40 } : center(c.box);
    ways.push({ t: c.t, x: p.x, y: p.y, click: true }); }
  if (vo) ways.push({ t: vo.t + 1.6, x: 790, y: 470, click: false });  // drift into the content after navigation
  ways.sort((a, b) => a.t - b.t);
  const ease = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
  const legs = ways.map((w, i) => { const from = i === 0 ? { x: 760, y: 700 } : ways[i - 1];
    const d = Math.hypot(w.x - from.x, w.y - from.y), D = Math.min(0.85, 0.32 + 0.14 * Math.log2(1 + d / 60));
    const arrive = w.click ? w.t - 0.14 : w.t, start = arrive - D;
    const nx = -(w.y - from.y) / (d || 1), ny = (w.x - from.x) / (d || 1), bow = 0.14 * d * (i % 2 ? 1 : -1);
    return { start, arrive, from, to: w, ctrl: { x: (from.x + w.x) / 2 + nx * bow, y: (from.y + w.y) / 2 + ny * bow } }; });
  const cursor: Cur[] = [];
  for (let f = 0; f < N; f++) { const t = f / fps;
    let pos = legs.length ? { ...legs[0].from } : { x: 760, y: 700 }, moving = false, lastArrive = -9;
    for (const L of legs) {
      if (t >= L.arrive) { pos = { x: L.to.x, y: L.to.y }; lastArrive = L.arrive; }
      else if (t >= L.start) { const u = ease((t - L.start) / (L.arrive - L.start)), a = 1 - u;
        pos = { x: a * a * L.from.x + 2 * a * u * L.ctrl.x + u * u * L.to.x, y: a * a * L.from.y + 2 * a * u * L.ctrl.y + u * u * L.to.y }; moving = true; break; }
      else break; }
    if (!moving && t - lastArrive > 0.8) { const q = t - lastArrive; pos.x += 1.6 * Math.sin(q * 1.3); pos.y += 1.1 * Math.sin(q * 0.9 + 1); }
    let opacity = 1;
    for (const k of keySegs) { const ts = k.times![0], te = k.times!.at(-1)!, nextMove = legs.find(L => L.start >= te)?.start ?? Infinity;
      if (t > ts + 0.15 && t < nextMove) opacity = Math.min(opacity, Math.max(0, 1 - (t - ts - 0.15) / 0.25));
      else if (t >= nextMove && t < nextMove + 0.2) opacity = Math.min(opacity, (t - nextMove) / 0.2); }
    const c = clicks.find(k => t >= k.t && t < k.t + 0.09);
    cursor.push({ x: pos.x, y: pos.y, opacity, press: c ? 1 : 0 });
  }
  const ripples: Ripple[] = ways.filter(w => w.click).map(w => ({ t: w.t, x: w.x, y: w.y }));
  return { cam, cursor, ripples, S_WIDE, shots: plan, H };
}
