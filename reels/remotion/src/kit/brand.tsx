import React from 'react';
import { AbsoluteFill, Img, staticFile } from 'remotion';
import { C, GRAD } from './tokens';
export const Logo: React.FC<{ size?: number; withName?: boolean; style?: React.CSSProperties }> = ({ size = 40, withName = true, style }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: size * 0.32, color: C.textSoft, fontSize: size * 0.85, fontWeight: 600, ...style }}>
    <Img src={staticFile('logo.png')} style={{ width: size, height: size }} />{withName && 'Memora'}</div>);
/** text filled with the brand violet→blue gradient */
export const Grad: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <span style={{ backgroundImage: GRAD, WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', ...style }}>{children}</span>);
/** approved subtle grounds: dots (Agent), grid (Quiz), cross (Flashcards), or plain. Always with the soft vignette. */
export const Ground: React.FC<{ pattern?: 'dots' | 'grid' | 'cross' | 'plain' }> = ({ pattern = 'dots' }) => {
  const p: Record<string, React.CSSProperties> = {
    dots: { backgroundImage: 'radial-gradient(#ffffff1c 1.6px, transparent 1.9px)', backgroundSize: '34px 34px' },
    grid: { backgroundImage: 'linear-gradient(#ffffff0b 1.5px, transparent 1.5px), linear-gradient(90deg, #ffffff0b 1.5px, transparent 1.5px)', backgroundSize: '48px 48px', backgroundPosition: '-1px -1px' },
    cross: { backgroundImage: `url("data:image/svg+xml,${encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' width='44' height='44'><path d='M22 16v12M16 22h12' stroke='#ffffff' stroke-opacity='0.12' stroke-width='2' stroke-linecap='round'/></svg>")}")`, backgroundSize: '44px 44px' },
    plain: {} };
  return <AbsoluteFill style={{ background: C.ground, ...p[pattern] }}>
    <AbsoluteFill style={{ background: 'radial-gradient(circle at 50% 50%, transparent 45%, #000000d0 92%)' }} /></AbsoluteFill>; };
/** soft brand glow, for emphasis behind a headline or card (keep subtle) */
export const Glow: React.FC<{ y?: number; color?: string; strength?: number }> = ({ y = 960, color = C.violet, strength = 0.22 }) => (
  <AbsoluteFill style={{ background: `radial-gradient(760px 560px at 50% ${y}px, ${color}${Math.round(strength * 255).toString(16).padStart(2, '0')}, transparent 70%)` }} />);
/** rounded panel in the app's own surface style */
export const Panel: React.FC<{ children?: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: C.panel, border: `1.5px solid ${C.lineSoft}`, borderRadius: 28, ...style }}>{children}</div>);
/** the approved step tracker: pills joined by gradient rails; `active` = how many steps are lit (1-based) */
export const Steps: React.FC<{ labels: string[]; active: number; top?: number }> = ({ labels, active, top = 230 }) => (
  <div style={{ position: 'absolute', top, left: 60, right: 60, display: 'flex', alignItems: 'center' }}>
    {labels.map((l, i) => { const on = i < active, cur = i === active - 1;
      return <React.Fragment key={i}>
        {i > 0 && <div style={{ flex: 1, height: 4, margin: '0 10px', borderRadius: 2, background: C.line, overflow: 'hidden' }}>
          <div style={{ width: on ? '100%' : '0%', height: '100%', background: GRAD }} /></div>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderRadius: 999, fontSize: 28, fontWeight: 600, whiteSpace: 'nowrap',
          background: cur ? GRAD : on ? '#18181b' : '#0f0f11', color: cur ? '#0b0b0f' : on ? C.textSoft : C.faint, border: `1.5px solid ${cur ? 'transparent' : on ? '#3f3f46' : C.line}`,
          transform: `scale(${cur ? 1.04 : 1})` }}>
          <span style={{ width: 34, height: 34, borderRadius: 17, display: 'grid', placeItems: 'center', fontSize: 22, background: cur ? '#0b0b0f22' : C.line, color: cur ? '#0b0b0f' : C.muted }}>{i + 1}</span>{l}</div>
      </React.Fragment>; })}
  </div>);
