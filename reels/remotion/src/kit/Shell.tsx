import React from 'react';
import { AbsoluteFill, staticFile } from 'remotion';
import type { Resolved } from './types';
import { C, FONT } from './tokens';
import { Captions } from './Captions';
import { ReelAudio } from './Audio';
/**
 * Outer wrapper every generated reel uses: black ground, Geist, voiceover + music + app sound effects, and captions.
 * captions={false} hides them (only if the reel shows the spoken words some other way, e.g. kinetic type).
 */
export const ReelShell: React.FC<{ R: Resolved; children: React.ReactNode; captions?: false | { y?: number; variant?: 'pill' | 'lower' };
  sfx?: { at: number; kind: 'click' | 'key' | 'done' | 'whoosh'; volume?: number }[] }> = ({ R, children, captions = {}, sfx }) => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT, color: C.text }}>
    <style>{`@font-face{font-family:Geist;src:url(${staticFile('geist.woff2')}) format('woff2');font-weight:100 900;}`}</style>
    {children}
    {captions !== false && <Captions R={R} {...captions} />}
    <ReelAudio R={R} sfx={sfx} />
  </AbsoluteFill>);
