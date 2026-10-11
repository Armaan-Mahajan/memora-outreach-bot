import React, { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import type { Resolved, Word } from './types';
import { C } from './tokens';
type Phrase = { words: Word[]; s: number; e: number };
const phrasesOf = (R: Resolved): Phrase[] => { const out: Phrase[] = [];
  for (const L of R.vo.lines) { let cur: Word[] = [];
    const flush = () => { if (cur.length) out.push({ words: cur, s: cur[0].s - 0.05, e: cur[cur.length - 1].e + 0.25 }); cur = []; };
    for (const w of L.words) { cur.push(w); if (/[.,:;!?]$/.test(w.w) || cur.length >= 4) flush(); } flush(); }
  out.forEach((p, i) => { const n = out[i + 1]; if (n && p.e > n.s) p.e = n.s; }); return out; };
/** Word-timed captions from the voiceover (≤4 words per phrase, current word highlighted). Place at the top level, not inside a <Seg>. */
export const Captions: React.FC<{ R: Resolved; y?: number; variant?: 'pill' | 'lower' }> = ({ R, y = 1580, variant = 'pill' }) => {
  const phrases = useMemo(() => phrasesOf(R), [R.slug]); const t = useCurrentFrame() / useVideoConfig().fps;
  const p = phrases.find(p => t >= p.s && t < p.e); if (!p) return null; const k = Math.min(1, (t - p.s) / 0.12);
  if (variant === 'lower') return <div style={{ position: 'absolute', top: y, left: 70, right: 70, opacity: k, transform: `translateY(${(1 - k) * 12}px)`,
    fontSize: 54, fontWeight: 600, letterSpacing: -0.8, lineHeight: 1.2, color: C.textSoft, borderLeft: `4px solid ${C.violetL}`, paddingLeft: 26 }}>
    {p.words.map((w, i) => <span key={i} style={{ color: t >= w.s && t < w.e + 0.08 ? '#fff' : C.muted }}>{w.w}{i < p.words.length - 1 ? ' ' : ''}</span>)}</div>;
  return <div style={{ position: 'absolute', top: y, left: 0, right: 0, display: 'flex', justifyContent: 'center', transform: `translateY(-50%) scale(${0.94 + 0.06 * k})`, opacity: k }}>
    <div style={{ maxWidth: 940, padding: '14px 30px', borderRadius: 22, background: 'rgba(0,0,0,0.62)', textAlign: 'center',
      fontSize: 62, fontWeight: 700, letterSpacing: -1.2, lineHeight: 1.15, color: C.text }}>
      {p.words.map((w, i) => <span key={i} style={{ color: t >= w.s && t < w.e + 0.08 ? C.violetL : C.text }}>{w.w}{i < p.words.length - 1 ? ' ' : ''}</span>)}</div></div>; };
