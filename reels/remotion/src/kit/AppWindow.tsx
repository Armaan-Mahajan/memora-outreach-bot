import React, { useMemo } from 'react';
import { OffthreadVideo, Freeze, staticFile, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { direct, PAGE } from '../director';
import type { Resolved } from './types';
import { seg } from './timeline';
import { C } from './tokens';

const Arrow: React.FC<{ size: number }> = ({ size }) => (
  <svg width={size * 0.72} height={size} viewBox="0 0 18 25" style={{ overflow: 'visible', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.55))' }}>
    <path d="M1.5 1.5 L1.5 19.2 L6.1 15.0 L9.3 22.6 L12.3 21.3 L9.2 13.9 L15.4 13.9 Z" fill="#fff" stroke="#0b0b0f" strokeWidth="1.4" strokeLinejoin="round" /></svg>);
const Lock: React.FC = () => <svg width="16" height="18" viewBox="0 0 16 18"><rect x="2" y="8" width="12" height="9" rx="2" fill="#a1a1aa" /><path d="M5 8V5.5a3 3 0 0 1 6 0V8" stroke="#a1a1aa" strokeWidth="2" fill="none" /></svg>;
const FF: React.FC = () => <svg width="28" height="20" viewBox="0 0 30 22"><path d="M1 1 L14 11 L1 21Z M15 1 L28 11 L15 21Z" fill="#fff" /></svg>;

export type WindowLayout = { w?: number; midY?: number; hMax?: number; chrome?: boolean; url?: string; radius?: number; glow?: boolean };
/** cached camera/cursor plan for this recording at this window size */
export const useDirection = (R: Resolved, w: number, hMax: number) => {
  const { fps } = useVideoConfig(); const evs = R.footage.events.events; const t0 = evs.find(e => e.type === 'rec_start')!.t;
  return useMemo(() => direct(evs, R.footage.regions, { w, hMax }, fps, t0, R.footage.clipDur, R.footage.beats), [R.slug, w, hMax]); };

/**
 * The real app, recorded, inside the approved browser window, with the automatic camera (zoom/pan) and drawn cursor.
 * Must be placed inside <Seg id="…"> for a FOOTAGE segment: it plays that segment's slice of the recording.
 * Window top-center sits at midY − h/2; its height grows as the camera zooms (up to hMax).
 */
export const AppWindow: React.FC<{ R: Resolved; id: string; layout?: WindowLayout; intro?: number }> = ({ R, id, layout = {}, intro = 0.3 }) => {
  const { w = 920, midY = 950, hMax = 1100, chrome = true, url = 'the-memora.com', radius = 26, glow = false } = layout;
  const f = useCurrentFrame(); const { fps } = useVideoConfig(); const s = seg(R, id);
  if (s.kind !== 'footage') throw new Error(`AppWindow needs a footage segment, "${id}" is a ${s.kind}`);
  const D = useDirection(R, w, hMax);
  const clipT = (s.clipIn ?? 0) + f / fps, cf = Math.max(0, Math.min(D.cam.length - 1, Math.round(clipT * fps)));
  const cam = D.cam[cf], cur = D.cursor[cf];
  const h = cam.h, top = midY - h / 2, X = (1080 - w) / 2, CH = chrome ? 54 : 0;
  const tx = w / 2 - cam.cx * cam.s, ty = h / 2 - cam.cy * cam.s;
  const px = (x: number) => x * cam.s + tx, py = (y: number) => y * cam.s + ty;
  const size = 36 * Math.pow(cam.s / 1.3, 0.35) * (cur.press ? 0.82 : 1);
  const ripple = D.ripples.find(r => clipT >= r.t && clipT < r.t + 0.45);
  const k = intro > 0 ? interpolate(f / fps, [0, intro], [0, 1], { extrapolateRight: 'clamp' }) : 1;
  const clipFrames = Math.floor(R.footage.clipDur * fps), startFrom = Math.round((s.clipIn ?? 0) * fps);
  const evs = R.footage.events.events, t0 = evs.find(e => e.type === 'rec_start')!.t;
  // "Sped up" chip: shown exactly while the recording was compressed (from each speed event with F > 1 to the next speed event)
  const spd = evs.filter(e => e.type === 'speed'), endT = evs[evs.length - 1].t;
  const chip = Math.max(0, ...spd.flatMap((e: any, i) => e.F > 1 ? [[e.t - t0, Math.max(e.t + 0.3, spd[i + 1]?.t ?? endT) - t0]] : [])
    .map(([a, b]) => interpolate(clipT, [a - 0.15, a + 0.15, b - 0.1, b + 0.2], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })));
  const video = <OffthreadVideo src={staticFile(R.footage.clip)} style={{ width: PAGE.w * 2, height: PAGE.h * 2 }} muted />;
  return <>
    {glow && <div style={{ position: 'absolute', left: X - 60, top: top - 60, width: w + 120, height: h + 120, borderRadius: 60, background: `${C.violet}33`, filter: 'blur(60px)', opacity: k }} />}
    {chrome && <div style={{ position: 'absolute', left: X, top: top - CH, width: w, height: CH + 2, borderRadius: `${radius}px ${radius}px 0 0`, background: C.panelHi,
      boxShadow: `0 0 0 1.5px ${C.lineSoft}`, opacity: k, display: 'flex', alignItems: 'center', padding: '0 22px', gap: 10 }}>
      {['#ff5f57', '#febc2e', '#28c840'].map(c => <div key={c} style={{ width: 15, height: 15, borderRadius: 8, background: c }} />)}
      <div style={{ marginLeft: 'auto', marginRight: 'auto', display: 'flex', alignItems: 'center', gap: 10, padding: '7px 26px', borderRadius: 10, background: '#2a2a31', color: '#d4d4d8', fontSize: 24 }}>
        <Lock />{url}</div><div style={{ width: 75 }} /></div>}
    <div style={{ position: 'absolute', left: X, top, width: w, height: h, borderRadius: chrome ? `0 0 ${radius}px ${radius}px` : radius, overflow: 'hidden', background: '#000',
      boxShadow: `0 0 0 1.5px ${C.lineSoft}`, opacity: k, transform: `scale(${0.97 + 0.03 * k})` }}>
      {/* capture is 2× (2640×1720): scale s/2 so 1 page px = s window px */}
      <div style={{ position: 'absolute', left: 0, top: 0, width: PAGE.w * 2, height: PAGE.h * 2, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${cam.s / 2})` }}>
        {startFrom + f < clipFrames - 1 ? <OffthreadVideo src={staticFile(R.footage.clip)} startFrom={startFrom} style={{ width: PAGE.w * 2, height: PAGE.h * 2 }} muted />
          : <Freeze frame={clipFrames - 2}>{video}</Freeze>}
      </div>
      {ripple && (() => { const q = (clipT - ripple.t) / 0.45, r = 10 + 38 * (1 - Math.pow(1 - q, 3));
        return <div style={{ position: 'absolute', left: px(ripple.x) - r, top: py(ripple.y) - r, width: 2 * r, height: 2 * r, borderRadius: '50%',
          border: `3px solid ${C.violetL}`, background: `${C.violetL}22`, opacity: 0.85 * (1 - q) }} />; })()}
      <div style={{ position: 'absolute', left: px(cur.x) - 2, top: py(cur.y) - 2, opacity: cur.opacity }}><Arrow size={size} /></div>
    </div>
    {chip > 0 && <div style={{ position: 'absolute', top: top - CH - 72, right: X + 6, opacity: chip, transform: `translateY(${(1 - chip) * -10}px)`, display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 22px', borderRadius: 999, background: 'rgba(16,16,20,.85)', border: '1.5px solid #ffffff2e', color: '#fff', fontSize: 30, fontWeight: 600 }}><FF />Sped up</div>}
  </>; };
