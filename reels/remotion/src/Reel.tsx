import React, { useMemo } from 'react';
import { AbsoluteFill, OffthreadVideo, Freeze, Img, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { direct, PAGE, Ev, Regions, Beat, cardH } from './director';
import agentEv from './footage/agent/events.json'; import agentVo from './footage/agent/vo.json';
import quizEv from './footage/quiz/events.json'; import quizVo from './footage/quiz/vo.json';
import flashEv from './footage/flash/events.json'; import flashVo from './footage/flash/vo.json';
import courseEv from './footage/course/events.json'; import courseVo from './footage/course/vo.json';
import lessonEv from './footage/lesson/events.json'; import lessonVo from './footage/lesson/vo.json';
import quizfEv from './footage/quizfull/events.json'; import quizfVo from './footage/quizfull/vo.json';
import flashfEv from './footage/flashfull/events.json'; import flashfVo from './footage/flashfull/vo.json';

// Layout of the 1080×1920 frame (captions/voiceover band sits above the card later).
export const CARD = { x: 40, w: 1000, r: 26, midY: 960 };   // height is variable: cardH(zoom)
const VIOLET = '#8b5cf6', BLUE = '#3b82f6', VIOLET_L = '#a78bfa';

// Named page regions for the Agent flow (page CSS px). Future runner versions log these automatically.
const REGIONS: Regions = {
  dialog: { x: 170, y: 32, w: 980, h: 796 },     // "Draft: Course Structure" modal
  outline: { x: 190, y: 90, w: 640, h: 430 },    // title + node/subnode tree inside the modal
  toast: { x: 900, y: 16, w: 404, h: 110 },      // "Course generated" toast, top-right
  content: { x: 395, y: 120, w: 830, h: 640 },   // course viewer text column
};
const RESULTS: Regions = { results: { x: 330, y: 150, w: 660, h: 640 } };   // quiz / flashcard "Save" page: heading + preview list
// Full-length reels (2026-10-03): per-reel beats tell the director what to frame beyond the built-in rules.
const SIDEBAR = { x: 0, y: 60, w: 760, h: 430 };                 // course sidebar + the start of the text column
const EMB_CARD = { x: 395, y: 215, w: 830, h: 480 };             // embedded flashcard inside a lesson (after the 330 px scroll)
const QUIZ_Q = { x: 440, y: 185, w: 760, h: 270 };               // quiz viewer: question + options, check button at the right edge
const STUDY_CARD = { x: 600, y: 440, w: 560, h: 320 };           // flashcard study view: card text + Correct/Incorrect buttons
const NODE_BEATS: Beat[] = [{ ev: 'click:sidebar', i: 'all', region: SIDEBAR, s: 1.5 }, { ev: 'cut', i: 'all', dt: 0.2, region: REGIONS.content }];
// One entry per recording: runner events + voiceover + where its clip and audio live
type Footage = { events: any; vo: any; clip: string; voDir: string; regions: Regions; beats?: Beat[] };
export const FOOTAGE: Record<string, Footage> = {
  agent: { events: agentEv, vo: agentVo, clip: 'footage/agent/clip.mp4', voDir: 'vo/agent/', regions: REGIONS },
  quiz:  { events: quizEv,  vo: quizVo,  clip: 'footage/quiz/clip.mp4',  voDir: 'vo/quiz/',  regions: RESULTS },
  flash: { events: flashEv, vo: flashVo, clip: 'footage/flash/clip.mp4', voDir: 'vo/flash/', regions: RESULTS },
  course: { events: courseEv, vo: courseVo, clip: 'footage/course/clip.mp4', voDir: 'vo/course/', regions: REGIONS, beats: NODE_BEATS },
  lesson: { events: lessonEv, vo: lessonVo, clip: 'footage/lesson/clip.mp4', voDir: 'vo/lesson/', regions: REGIONS, beats: [
    { ev: 'card_flip', dt: -0.6, region: EMB_CARD }, { ev: 'card_flip2', dt: 0.3, region: EMB_CARD, s: 1.45 },
    { ev: 'subnode2', dt: 0.25, region: REGIONS.content }, ...NODE_BEATS] },
  quizfull: { events: quizfEv, vo: quizfVo, clip: 'footage/quizfull/clip.mp4', voDir: 'vo/quizfull/', regions: RESULTS, beats: [
    { ev: 'click:slider', region: 'click', s: 1.8 }, { ev: 'click:save', region: 'click', s: 1.6 }, { ev: 'list_open', region: 'WIDE' },
    { ev: 'click:start', region: 'click', s: 1.5 }, { ev: 'viewer_open', dt: 0.35, region: QUIZ_Q }] },
  flashfull: { events: flashfEv, vo: flashfVo, clip: 'footage/flashfull/clip.mp4', voDir: 'vo/flashfull/', regions: RESULTS, beats: [
    { ev: 'click:save', region: 'click', s: 1.6 }, { ev: 'viewer_open', dt: 0.35, region: STUDY_CARD }] },
};

// ─── CAPTIONS ─────────────────────────────────────────────────────────────────────
// Word-timed from the voiceover. Phrases break at punctuation or every 4 words; the word being
// spoken is highlighted in brand violet. Fixed at y≈1460: below the window when it's small,
// on a dark pill over the window's lower part when it's tall.
type W = { w: string; s: number; e: number };
type Phrase = { words: W[]; s: number; e: number };
const buildPhrases = (vo: any): Phrase[] => { const out: Phrase[] = [];
  for (const L of vo.lines) { let cur: W[] = [];
    const flush = () => { if (cur.length) out.push({ words: cur, s: cur[0].s - 0.05, e: cur[cur.length - 1].e + 0.25 }); cur = []; };
    for (const w of L.words as W[]) { cur.push(w); if (/[.,:;!?]$/.test(w.w) || cur.length >= 4) flush(); } flush(); }
  out.forEach((p, i) => { const n = out[i + 1]; if (n && p.e > n.s) p.e = n.s; }); return out; };
const Captions: React.FC<{ t: number; y?: number; phrases: Phrase[]; lower?: boolean }> = ({ t, y = 1460, phrases, lower }) => {
  const p = phrases.find(p => t >= p.s && t < p.e); if (!p) return null;
  const k = Math.min(1, (t - p.s) / 0.12);
  if (lower) return <div style={{ position: 'absolute', top: y, left: 70, right: 70, opacity: k, transform: `translateY(${(1 - k) * 12}px)`,
      fontSize: 54, fontWeight: 600, letterSpacing: -0.8, lineHeight: 1.2, color: '#e4e4e7', borderLeft: `4px solid ${VIOLET_L}`, paddingLeft: 26 }}>
      {p.words.map((w, i) => <span key={i} style={{ color: t >= w.s && t < w.e + 0.08 ? '#fff' : '#a1a1aa' }}>{w.w}{i < p.words.length - 1 ? ' ' : ''}</span>)}</div>;
  return <div style={{ position: 'absolute', top: y, left: 0, right: 0, display: 'flex', justifyContent: 'center', transform: `translateY(-50%) scale(${0.94 + 0.06 * k})`, opacity: k }}>
    <div style={{ maxWidth: 940, padding: '14px 30px', borderRadius: 22, background: 'rgba(0,0,0,0.62)', backdropFilter: 'blur(10px)', textAlign: 'center',
      fontSize: 62, fontWeight: 700, letterSpacing: -1.2, lineHeight: 1.15, color: '#fafafa' }}>
      {p.words.map((w, i) => <span key={i} style={{ color: t >= w.s && t < w.e + 0.08 ? VIOLET_L : '#fafafa' }}>{w.w}{i < p.words.length - 1 ? ' ' : ''}</span>)}
    </div></div>; };
const FF: React.FC = () => <svg width="28" height="20" viewBox="0 0 30 22"><path d="M1 1 L14 11 L1 21Z M15 1 L28 11 L15 21Z" fill="#fff" /></svg>;

// ─── FRAME VARIANTS (everything outside the app window) ─────────────────────────────
type Variant = { midY: number; hMax: number; capY: number; chrome?: boolean; w?: number; dots?: boolean; steps?: boolean; r?: number; kind?: string;
  pattern?: 'dots' | 'grid' | 'cross'; url?: string; labels?: string[]; stepMarks?: 'agent' | 'create' | string[] };
const VARIANTS: Record<string, Variant> = {
  base:     { midY: 960,  hMax: 1640, capY: 1460 },
  hook:     { midY: 1070, hMax: 1160, capY: 1540 },   // A: persistent headline band + brand glow + URL footer
  browser:  { midY: 990,  hMax: 1360, capY: 1560, chrome: true },  // B: macOS browser window on a dot grid
  coldopen: { midY: 1040, hMax: 1220, capY: 1560 },   // C: 1.5 s kinetic-type cold open, then the window flies in
  steps:    { midY: 1080, hMax: 1140, capY: 1560 },   // D: 3-step progress rail that lights up with the flow
  // B + D (chosen 2026-10-02): browser window with more side padding on the dot grid, step tracker on top
  // ─── THE SERIES (approved 2026-10-02): browser window + step tracker on a patterned ground, one pattern per Reel type ───
  browsersteps: { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'dots',
                  url: 'the-memora.com/agent', labels: ['Type a topic', 'Get the outline', 'Get the course'], stepMarks: 'agent' },
  quizsteps:    { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'grid',
                  url: 'the-memora.com/quizzes', labels: ['Type a topic', 'Generate', 'Review the quiz'], stepMarks: 'create' },
  flashsteps:   { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'cross',
                  url: 'the-memora.com/flashcards', labels: ['Type a topic', 'Generate', 'Review the deck'], stepMarks: 'create' },
  // full-length versions (2026-10-03): same series, step tracker covers the whole flow
  coursesteps: { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'dots',
                 url: 'the-memora.com/agent', labels: ['Type a topic', 'Get the outline', 'Get the course'], stepMarks: ['rec_start', 'click:generate', 'click:proceed'] },
  lessonsteps: { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'dots',
                 url: 'the-memora.com/agent', labels: ['Type a topic', 'Get the course', 'Study a lesson'], stepMarks: ['rec_start', 'click:proceed', 'viewer_open+0.3'] },
  quizfullsteps: { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'grid',
                 url: 'the-memora.com/quizzes', labels: ['Type a topic', 'Generate', 'Practice'], stepMarks: ['rec_start', 'click:generate-0.7', 'viewer_open+0.3'] },
  flashfullsteps: { midY: 950, hMax: 1100, capY: 1580, chrome: true, w: 920, steps: true, pattern: 'cross',
                 url: 'the-memora.com/flashcards', labels: ['Type a topic', 'Generate', 'Study'], stepMarks: ['rec_start', 'click:generate-0.7', 'viewer_open+0.3'] },
  // ─── per-content-type frames (2026-10-02) ───
  cinematic: { midY: 900,  hMax: 1120, capY: 1610, w: 1080, r: 0, kind: 'cinematic' },  // Agent course: full-bleed product film, lower-third captions
  prompt:    { midY: 1190, hMax: 980,  capY: 1665, kind: 'prompt' },                   // Agent outline: the typed prompt as a big quote card above
  lesson:    { midY: 1010, hMax: 1160, capY: 1590, w: 930, kind: 'lesson' },           // Subnode walk-through: breadcrumb + reading progress, ruled paper
  challenge: { midY: 1070, hMax: 1100, capY: 1600, kind: 'challenge' },                // Quiz: "Can you ace this one?" + A–D pills, glowing window
  qhook:     { midY: 1250, hMax: 860,  capY: 1720, kind: 'qhook' },                    // Quiz: a real generated question on top, the window below
  stack:     { midY: 1060, hMax: 1080, capY: 1610, w: 900, kind: 'stack' },            // Flashcards: window on a deck of tilted cards
};
const GRAD = `linear-gradient(90deg, ${VIOLET_L}, #60a5fa)`;
const Lock: React.FC = () => <svg width="16" height="18" viewBox="0 0 16 18"><rect x="2" y="8" width="12" height="9" rx="2" fill="#a1a1aa" /><path d="M5 8V5.5a3 3 0 0 1 6 0V8" stroke="#a1a1aa" strokeWidth="2" fill="none" /></svg>;
const Steps: React.FC<{ t: number; marks: number[]; labels?: string[] }> = ({ t, marks, labels = ['Type a topic', 'Get the outline', 'Get the course'] }) => {
  const active = marks.filter(m => t >= m).length;   // 1..3
  return <div style={{ position: 'absolute', top: 230, left: 60, right: 60, display: 'flex', alignItems: 'center' }}>
    {labels.map((l, i) => { const on = i < active, cur = i === active - 1;
      return <React.Fragment key={i}>
        {i > 0 && <div style={{ flex: 1, height: 4, margin: '0 10px', borderRadius: 2, background: '#27272a', overflow: 'hidden' }}>
          <div style={{ width: on ? '100%' : '0%', height: '100%', background: GRAD, transition: 'none' }} /></div>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderRadius: 999, fontSize: 28, fontWeight: 600, whiteSpace: 'nowrap',
          background: cur ? GRAD : on ? '#18181b' : '#0f0f11', color: cur ? '#0b0b0f' : on ? '#e4e4e7' : '#52525b', border: `1.5px solid ${cur ? 'transparent' : on ? '#3f3f46' : '#27272a'}`,
          transform: `scale(${cur ? 1.04 : 1})` }}>
          <span style={{ width: 34, height: 34, borderRadius: 17, display: 'grid', placeItems: 'center', fontSize: 22, background: cur ? '#0b0b0f22' : '#27272a', color: cur ? '#0b0b0f' : '#a1a1aa' }}>{i + 1}</span>{l}</div>
      </React.Fragment>; })}
  </div>; };

const Arrow: React.FC<{ size: number }> = ({ size }) => (   // macOS-style pointer
  <svg width={size * 0.72} height={size} viewBox="0 0 18 25" style={{ overflow: 'visible', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.55))' }}>
    <path d="M1.5 1.5 L1.5 19.2 L6.1 15.0 L9.3 22.6 L12.3 21.3 L9.2 13.9 L15.4 13.9 Z" fill="#fff" stroke="#0b0b0f" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);

export const Reel: React.FC<{ variant?: string; footage?: string }> = ({ variant = 'base', footage = 'agent' }) => {
  const V = VARIANTS[variant] ?? VARIANTS.base; const F = FOOTAGE[footage]; const vo = F.vo;
  const phrases = useMemo(() => buildPhrases(vo), [footage]);
  const CW = V.w ?? CARD.w, CX = (1080 - CW) / 2;
  const frame = useCurrentFrame(); const { fps, durationInFrames } = useVideoConfig(); const t = frame / fps;
  const evs = (F.events as { events: Ev[] }).events; const t0 = evs.find(e => e.type === 'rec_start')!.t;
  const clipFrames = Math.floor((evs.find(e => e.type === 'rec_end')!.t - t0) * fps);   // recording length; anything after is end hold
  const D = useMemo(() => direct(evs, F.regions, { w: CW, hMax: V.hMax }, fps, t0, durationInFrames / fps, F.beats ?? []), [variant, footage]);
  const cam = D.cam[Math.min(frame, D.cam.length - 1)], cur = D.cursor[Math.min(frame, D.cursor.length - 1)];
  // page px → card px
  const h = cam.h, top = V.midY - h / 2;
  const tx = CW / 2 - cam.cx * cam.s, ty = h / 2 - cam.cy * cam.s;
  const px = (x: number) => x * cam.s + tx, py = (y: number) => y * cam.s + ty;
  const size = 36 * Math.pow(cam.s / 1.3, 0.35) * (cur.press ? 0.82 : 1);
  const ripple = D.ripples.find(r => t >= r.t && t < r.t + 0.45);
  const introAt = variant === 'coldopen' ? 1.25 : 0;
  const intro = interpolate(t, [introAt, introAt + 0.45], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const CH = V.chrome ? 54 : 0;   // browser title-bar height
  const rel = (type: string, i = 0) => { const e = evs.filter(e => e.type === type)[i]; return e ? e.t - t0 : null; };
  const spedA = rel('sped_up_start'), genDone = rel('course_gen_done');
  const chip = spedA != null && genDone != null ? interpolate(t, [spedA - 0.15, spedA + 0.15, genDone - 0.1, genDone + 0.2], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }) : 0;
  const keyTimes: number[] = (evs.find(e => e.type === 'keys')?.times || []).map((k: number) => k - t0);
  const allKeys: number[] = evs.filter(e => e.type === 'keys').flatMap(e => e.times || []).map((k: number) => k - t0);
  // step-tracker mark spec: "event", "click:<target>", optional "+0.3" / "-0.7" offset
  const at = (spec: string) => { const m = spec.match(/^([a-z_]+)(?::([a-z_]+))?([+-][\d.]+)?$/)!; const e = m[2] ? evs.find(e => e.type === 'click' && e.target === m[2]) : evs.find(e => e.type === m[1]);
    return e ? e.t - t0 + (m[3] ? parseFloat(m[3]) : 0) : 999; };
  // music bed: very subtle, ducks further under the voice (0.25 s ramps)
  const bedVol = (tt: number) => { const speaking = vo.lines.some((l: any) => tt > l.at - 0.25 && tt < l.at + l.dur + 0.25);
    const end = durationInFrames / fps; return (speaking ? 0.045 : 0.09) * Math.min(1, tt / 1.5) * Math.min(1, Math.max(0, (end - tt) / 1.5)); };

  return (
    <AbsoluteFill style={{ background: '#000', fontFamily: 'Geist, sans-serif' }}>
      <style>{`@font-face{font-family:Geist;src:url(${staticFile('geist.woff2')}) format('woff2');font-weight:100 900;}`}</style>
      {variant === 'hook' && <>
        <AbsoluteFill style={{ background: `radial-gradient(700px 520px at 50% ${V.midY}px, ${VIOLET}38, transparent 70%)` }} />
        <div style={{ position: 'absolute', top: 175, width: '100%', textAlign: 'center', fontWeight: 700, letterSpacing: -2.5, lineHeight: 1.08 }}>
          <div style={{ fontSize: 80, color: '#fafafa' }}>One sentence →</div>
          <div style={{ fontSize: 80, backgroundImage: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' }}>a full AP Bio course.</div></div>
        <div style={{ position: 'absolute', top: 1790, width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, color: '#a1a1aa', fontSize: 30, fontWeight: 500 }}>
          <Img src={staticFile('logo.png')} style={{ width: 34, height: 34 }} />the-memora.com</div></>}
      {V.pattern && <AbsoluteFill style={{ background: '#0a0a0c', ...({
          dots:  { backgroundImage: 'radial-gradient(#ffffff1c 1.6px, transparent 1.9px)', backgroundSize: '34px 34px' },
          grid:  { backgroundImage: 'linear-gradient(#ffffff0b 1.5px, transparent 1.5px), linear-gradient(90deg, #ffffff0b 1.5px, transparent 1.5px)', backgroundSize: '48px 48px', backgroundPosition: '-1px -1px' },
          cross: { backgroundImage: `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'44\' height=\'44\'><path d=\'M22 16v12M16 22h12\' stroke=\'#ffffff\' stroke-opacity=\'0.12\' stroke-width=\'2\' stroke-linecap=\'round\'/></svg>')}")`, backgroundSize: '44px 44px' },
        } as any)[V.pattern] }}>
        <AbsoluteFill style={{ background: 'radial-gradient(circle at 50% 50%, transparent 45%, #000000d0 92%)' }} /></AbsoluteFill>}
      {variant === 'browser' && <AbsoluteFill style={{ background: '#0a0a0c', backgroundImage: 'radial-gradient(#ffffff17 1.4px, transparent 1.6px)', backgroundSize: '34px 34px' }}>
        <AbsoluteFill style={{ background: 'radial-gradient(circle at 50% 50%, transparent 35%, #000 85%)' }} /></AbsoluteFill>}
      {variant === 'coldopen' && (() => { const words = ['I', 'typed', 'one', 'sentence.'];
        const move = interpolate(t, [1.15, 1.6], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }); const e = move * move * (3 - 2 * move);
        return <div style={{ position: 'absolute', left: 0, right: 0, top: 960 + (270 - 960) * e, transform: `translateY(-50%) scale(${1 - 0.42 * e})`, textAlign: 'center',
          fontSize: 104, fontWeight: 800, letterSpacing: -3.5, color: '#fafafa' }}>
          {words.map((w, i) => { const k = Math.min(1, Math.max(0, (t - 0.12 - i * 0.16) / 0.18));
            return <span key={i} style={{ display: 'inline-block', opacity: k, transform: `translateY(${(1 - k) * 30}px)`, marginRight: 26,
              ...(i === 3 ? { backgroundImage: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' } : {}) }}>{w}</span>; })}
        </div>; })()}
      {variant === 'steps' && <>
        <AbsoluteFill style={{ background: `radial-gradient(900px 420px at 50% 0px, ${VIOLET}2a, transparent 70%)` }} />
        <div style={{ position: 'absolute', top: 120, width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, color: '#e4e4e7', fontSize: 34, fontWeight: 600 }}>
          <Img src={staticFile('logo.png')} style={{ width: 38, height: 38 }} />Memora <span style={{ backgroundImage: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' }}>Agent</span></div>
        <Steps t={t} marks={[0, rel('click', 1) ?? 7.6, rel('click', 2) ?? 12]} /></>}
      {V.steps && <Steps t={t} labels={V.labels} marks={Array.isArray(V.stepMarks) ? V.stepMarks.map(at) : V.stepMarks === 'create'
        ? [0, (rel('click', 1) ?? 5) - 0.7, (rel('results_open') ?? 6) + 0.45]        // type → (cursor heads to Generate) → results page
        : [0, rel('click', 1) ?? 7.6, rel('click', 2) ?? 12]} />}
      {V.chrome && <div style={{ position: 'absolute', left: CX, top: top - CH, width: CW, height: CH + 2, borderRadius: `${CARD.r}px ${CARD.r}px 0 0`, background: '#1c1c21',
        boxShadow: '0 0 0 1.5px #ffffff1f', opacity: intro, display: 'flex', alignItems: 'center', padding: '0 22px', gap: 10 }}>
        {['#ff5f57', '#febc2e', '#28c840'].map(c => <div key={c} style={{ width: 15, height: 15, borderRadius: 8, background: c }} />)}
        <div style={{ marginLeft: 'auto', marginRight: 'auto', display: 'flex', alignItems: 'center', gap: 10, padding: '7px 26px', borderRadius: 10, background: '#2a2a31', color: '#d4d4d8', fontSize: 24 }}>
          <Lock />{V.url ?? 'the-memora.com/agent'}</div><div style={{ width: 75 }} /></div>}
      {/* ── per-content-type frames ── */}
      {V.kind === 'cinematic' && <>
        <div style={{ position: 'absolute', top: 150, left: 70, display: 'flex', alignItems: 'center', gap: 12, color: '#e4e4e7', fontSize: 32, fontWeight: 600 }}>
          <Img src={staticFile('logo.png')} style={{ width: 38, height: 38 }} />Memora</div>
        <div style={{ position: 'absolute', top: 205, left: 70, color: '#71717a', fontSize: 26, fontWeight: 500, letterSpacing: 3, textTransform: 'uppercase' }}>Agent · AP Biology</div>
        <div style={{ position: 'absolute', left: 0, right: 0, top: top - 3, height: 3, background: GRAD, opacity: intro }} />
        <div style={{ position: 'absolute', left: 0, right: 0, top: top + h, height: 3, background: GRAD, opacity: intro }} /></>}
      {V.kind === 'prompt' && (() => { const kev: any = evs.find(e => e.type === 'keys'); const text: string = kev?.text ?? '';
        const n = keyTimes.filter(k => t >= k).length, typing = n > 0 && n < text.length; const blink = Math.floor(t * 2.2) % 2 === 0;
        return <>
          <div style={{ position: 'absolute', top: 175, left: 70, right: 70, padding: '34px 40px', borderRadius: 28, background: '#111114', border: '1.5px solid #ffffff1a' }}>
            <div style={{ color: VIOLET_L, fontSize: 26, fontWeight: 600, letterSpacing: 2.5, textTransform: 'uppercase', marginBottom: 14 }}>The prompt</div>
            <div style={{ color: '#fafafa', fontSize: 50, fontWeight: 600, lineHeight: 1.2, letterSpacing: -1, minHeight: 120 }}>
              {text.slice(0, n) || <span style={{ color: '#52525b' }}>Type what you're studying…</span>}
              <span style={{ display: 'inline-block', width: 4, height: 50, marginLeft: 4, verticalAlign: '-6px', background: VIOLET_L, opacity: (typing || n === 0) && blink ? 1 : n >= text.length ? 0 : 0.2 }} /></div></div>
          <div style={{ position: 'absolute', left: 0, right: 0, top: top - 120, textAlign: 'center', color: '#52525b', fontSize: 64, opacity: intro }}>↓</div></>; })()}
      {V.kind === 'lesson' && (() => { const vOpen = rel('viewer_open') ?? 0, vEnd = rel('rec_end') ?? vOpen + 1;
        const prog = Math.min(1, Math.max(0, (t - vOpen) / (vEnd - vOpen))), shown = t >= vOpen - 0.3 ? 1 : 0;
        const crumbs = ['AP Biology', 'Photosynthesis', '1.2 Electron Transport Chain'];
        return <>
          <AbsoluteFill style={{ background: '#0b0b0d', backgroundImage: 'repeating-linear-gradient(0deg, #ffffff0a 0px, #ffffff0a 1.5px, transparent 1.5px, transparent 64px)' }} />
          <div style={{ position: 'absolute', top: 0, bottom: 0, left: 54, width: 2, background: `${VIOLET}55` }} />
          <div style={{ position: 'absolute', top: 205, left: 90, right: 40, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, fontSize: 30, fontWeight: 600, opacity: 0.35 + 0.65 * shown }}>
            {crumbs.map((c, i) => <React.Fragment key={i}>{i > 0 && <span style={{ color: '#52525b' }}>›</span>}
              <span style={{ padding: '10px 20px', borderRadius: 999, background: i === 2 ? GRAD : '#18181b', color: i === 2 ? '#0b0b0f' : '#d4d4d8', border: i === 2 ? 'none' : '1.5px solid #27272a' }}>{c}</span></React.Fragment>)}</div>
          <div style={{ position: 'absolute', left: CX + CW + 14, top: top, width: 6, height: h, borderRadius: 3, background: '#27272a', opacity: intro }}>
            <div style={{ width: '100%', height: `${prog * 100}%`, borderRadius: 3, background: GRAD }} /></div></>; })()}
      {V.kind === 'challenge' && <>
        <AbsoluteFill style={{ background: `linear-gradient(180deg, #23103d 0%, #0b0614 38%, #000 70%)` }} />
        <div style={{ position: 'absolute', top: 175, width: '100%', textAlign: 'center', fontSize: 86, fontWeight: 800, letterSpacing: -3, color: '#fafafa', lineHeight: 1.05 }}>
          Can you ace<br /><span style={{ backgroundImage: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' }}>this one?</span></div>
        <div style={{ position: 'absolute', top: 400, width: '100%', display: 'flex', justifyContent: 'center', gap: 18 }}>
          {['A', 'B', 'C', 'D'].map((l, i) => { const k = Math.min(1, Math.max(0, (t - 0.3 - i * 0.12) / 0.25));
            return <div key={l} style={{ width: 84, height: 84, borderRadius: 22, display: 'grid', placeItems: 'center', fontSize: 40, fontWeight: 700, color: '#e4e4e7',
              background: '#ffffff0d', border: '2px solid #ffffff22', opacity: k, transform: `translateY(${(1 - k) * 16}px)` }}>{l}</div>; })}</div></>}
      {V.kind === 'qhook' && (() => { const opts = ['Outer membrane', 'Stroma', 'Thylakoid membrane', 'Intermembrane space'];
        return <div style={{ position: 'absolute', top: 140, left: 60, right: 60 }}>
          <div style={{ color: VIOLET_L, fontSize: 26, fontWeight: 600, letterSpacing: 2.5, textTransform: 'uppercase' }}>Question 1 of 10</div>
          <div style={{ color: '#fafafa', fontSize: 50, fontWeight: 700, lineHeight: 1.15, letterSpacing: -1.2, margin: '14px 0 26px' }}>Which structure contains the photosynthetic pigments of a chloroplast?</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {opts.map((o, i) => { const k = Math.min(1, Math.max(0, (t - 0.2 - i * 0.1) / 0.25));
              return <div key={o} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '18px 20px', borderRadius: 18, background: '#141418', border: '1.5px solid #ffffff1a',
                color: '#e4e4e7', fontSize: 32, fontWeight: 500, opacity: k }}><span style={{ color: VIOLET_L, fontWeight: 700 }}>{'ABCD'[i]}</span>{o}</div>; })}</div></div>; })()}
      {V.kind === 'stack' && <>
        <AbsoluteFill style={{ background: `radial-gradient(800px 600px at 50% ${V.midY}px, ${BLUE}26, transparent 70%)` }} />
        <div style={{ position: 'absolute', top: 185, width: '100%', textAlign: 'center', fontWeight: 800, letterSpacing: -2.5, lineHeight: 1.08 }}>
          <div style={{ fontSize: 78, color: '#fafafa' }}>Photosynthesis</div>
          <div style={{ fontSize: 78, backgroundImage: GRAD, WebkitBackgroundClip: 'text', color: 'transparent' }}>→ 10 flashcards</div></div>
        {[{ r: -5, dx: -26, dy: 26, o: 0.55 }, { r: 3.5, dx: 22, dy: 14, o: 0.8 }].map((c, i) =>
          <div key={i} style={{ position: 'absolute', left: CX + c.dx, top: top + c.dy, width: CW, height: h, borderRadius: CARD.r, background: '#141418', border: '1.5px solid #ffffff18',
            transform: `rotate(${c.r * intro}deg)`, opacity: c.o * intro, boxShadow: '0 30px 80px -30px #000' }} />)}</>}
      {/* app card */}
      <div style={{ position: 'absolute', left: CX, top, width: CW, height: h, borderRadius: V.chrome ? `0 0 ${CARD.r}px ${CARD.r}px` : (V.r ?? CARD.r), overflow: 'hidden', background: '#000',
        boxShadow: V.kind === 'challenge' ? `0 0 0 2px ${VIOLET_L}, 0 0 90px -10px ${VIOLET}aa` : '0 0 0 1.5px #ffffff1f', opacity: intro, transform: `scale(${0.97 + 0.03 * intro})` }}>
        {/* capture is 2× (2640×1720): scale s/2 so 1 page px = s card px */}
        <div style={{ position: 'absolute', left: 0, top: 0, width: PAGE.w * 2, height: PAGE.h * 2, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${cam.s / 2})` }}>
          {/* past the end of the recording (end hold for a long voiceover): freeze its last frame */}
          {frame < clipFrames ? <OffthreadVideo src={staticFile(F.clip)} style={{ width: PAGE.w * 2, height: PAGE.h * 2 }} muted />
            : <Freeze frame={clipFrames - 2}><OffthreadVideo src={staticFile(F.clip)} style={{ width: PAGE.w * 2, height: PAGE.h * 2 }} muted /></Freeze>}
        </div>
        {ripple && (() => { const k = (t - ripple.t) / 0.45, r = 10 + 38 * (1 - Math.pow(1 - k, 3));
          return <div style={{ position: 'absolute', left: px(ripple.x) - r, top: py(ripple.y) - r, width: 2 * r, height: 2 * r, borderRadius: '50%',
            border: `3px solid ${VIOLET_L}`, background: `${VIOLET_L}22`, opacity: 0.85 * (1 - k) }} />; })()}
        <div style={{ position: 'absolute', left: px(cur.x) - 2, top: py(cur.y) - 2, opacity: cur.opacity }}><Arrow size={size} /></div>
      </div>
      {/* "Sped up" chip: shown whenever playback is faster than reality (course generation: ~30–40 s real) */}
        <div style={{ position: 'absolute', top: top - CH - 72, right: CX + 6, opacity: chip, transform: `translateY(${(1 - chip) * -10}px)`, display: 'flex', alignItems: 'center', gap: 12,
          padding: '12px 22px', borderRadius: 999, background: 'rgba(16,16,20,.85)', border: '1.5px solid #ffffff2e', color: '#fff', fontSize: 30, fontWeight: 600 }}><FF />Sped up</div>
      <Captions t={t} y={V.capY} phrases={phrases} lower={V.kind === 'cinematic'} />
      {/* audio */}
      {vo.lines.map((l: any, i: number) => <Sequence key={'vo' + i} from={Math.round(l.at * fps)}><Audio src={staticFile(F.voDir + l.file)} /></Sequence>)}
      <Audio src={staticFile('audio/bed.wav')} volume={f => bedVol(f / fps)} />
      {allKeys.map((k, i) => <Sequence key={'k' + i} from={Math.round(k * fps)} durationInFrames={5}><Audio src={staticFile(`audio/softkey${1 + (i * 7) % 4}.wav`)} volume={0.045 + 0.01 * ((i * 5) % 3) / 2} playbackRate={0.96 + ((i * 37) % 9) / 100} /></Sequence>)}
      {D.ripples.map((r, i) => <Sequence key={'c' + i} from={Math.round(r.t * fps)} durationInFrames={8}><Audio src={staticFile('audio/click.wav')} volume={0.28} /></Sequence>)}
      {genDone != null && <Sequence from={Math.round(genDone * fps)} durationInFrames={55}><Audio src={staticFile('audio/done.wav')} volume={0.16} /></Sequence>}
    </AbsoluteFill>
  );
};
