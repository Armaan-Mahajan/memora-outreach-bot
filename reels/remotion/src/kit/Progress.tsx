import React, { useMemo } from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import type { Resolved } from './types';
import { clipToReel } from './Audio';
import { C } from './tokens';
import { clamp01, easeOut } from './motion';

/**
 * A progress bar in the app's own style (violet fill on a dark track), pinned near the top of the reel, that counts what the
 * recording actually did: each click whose `as` is in `count` advances it by one (e.g. count={['correct','incorrect']} total={10}).
 * Optional `tally` shows how many of each so far (e.g. {correct: '✓', incorrect: '✗'}). Place it at the TOP LEVEL of the
 * reel (not inside a <Seg>: it runs on the reel clock); it shows only between `from` and `to` (reel seconds; default: from 0.6 s before the first counted click until
 * 0.6 s after the last, fading out before that footage segment ends).
 */
export const RunProgress: React.FC<{ R: Resolved; count: string[]; total: number; label?: string; tally?: Record<string, string>;
  from?: number; to?: number; top?: number }> = ({ R, count, total, label = 'Progress', tally, from, to, top = 236 }) => {
  const { fps } = useVideoConfig(); const t = useCurrentFrame() / fps;   // reel seconds
  const hits = useMemo(() => { const evs = R.footage.events.events, t0 = evs.find(e => e.type === 'rec_start')!.t;
    return evs.filter((e: any) => e.type === 'click' && count.includes(e.target)).map((e: any) => ({ k: e.target as string, at: clipToReel(R, e.t - t0) }))
      .filter((h): h is { k: string; at: number } => h.at != null).sort((a, b) => a.at - b.at); }, [R.slug]);
  if (!hits.length) return null;
  const lastAt = hits[hits.length - 1].at, segEnd = R.segments.find(sg => sg.kind === 'footage' && lastAt >= sg.start && lastAt <= sg.end)?.end ?? lastAt + 0.9;
  const a = from ?? hits[0].at - 0.6, b = to ?? Math.min(lastAt + 0.6, segEnd - 0.3);   // gone by the end of the fast-forward's segment
  return <ProgressAt t={t} hits={hits} a={a} b={b} total={total} label={label} tally={tally} top={top} />; };

const ProgressAt: React.FC<{ t: number; hits: { k: string; at: number }[]; a: number; b: number; total: number; label: string; tally?: Record<string, string>; top: number }> =
  ({ t, hits, a, b, total, label, tally, top }) => {
  const vis = Math.min(clamp01((t - a) / 0.25), clamp01((b + 0.3 - t) / 0.3)); if (vis <= 0) return null;
  const done = hits.filter(h => h.at <= t); const last = done[done.length - 1];
  const fill = Math.min(total, done.length - 1 + (last ? easeOut((t - last.at) / 0.18) : 0)) / total;
  return <div style={{ position: 'absolute', top, left: 70, right: 70, opacity: vis, transform: `translateY(${(1 - vis) * -12}px)` }}>
    <div style={{ background: 'rgba(20,20,24,0.92)', border: `1.5px solid ${C.lineSoft}`, borderRadius: 26, padding: '22px 30px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 30, fontWeight: 600, color: C.muted, letterSpacing: 1.5, textTransform: 'uppercase' }}>{label}</span>
        <span style={{ fontSize: 40, fontWeight: 700, color: C.text, fontVariantNumeric: 'tabular-nums' }}>{done.length} / {total}</span></div>
      <div style={{ marginTop: 16, height: 16, borderRadius: 8, background: C.line, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, fill) * 100}%`, height: '100%', borderRadius: 8, background: '#a78bfa' }} /></div>
      {tally && <div style={{ marginTop: 14, display: 'flex', gap: 28, fontSize: 30, fontWeight: 600 }}>
        {Object.entries(tally).map(([k, sym]) => <span key={k} style={{ color: k === 'incorrect' ? C.red : k === 'correct' ? C.green : C.textSoft }}>
          {sym} {done.filter(h => h.k === k).length}</span>)}</div>}
    </div></div>; };
