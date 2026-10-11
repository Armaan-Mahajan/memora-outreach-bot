import React from 'react';
import { Sequence, useVideoConfig } from 'remotion';
import type { Resolved, Segment } from './types';
export const seg = (R: Resolved, id: string): Segment => { const s = R.segments.find(s => s.id === id); if (!s) throw new Error(`no segment "${id}" in timeline`); return s; };
/** Renders children only during timeline segment `id`; inside, useT() counts from the segment's start. */
export const Seg: React.FC<{ R: Resolved; id: string; children: React.ReactNode; pad?: number }> = ({ R, id, children, pad = 0 }) => {
  const { fps } = useVideoConfig(); const s = seg(R, id);
  const from = Math.max(0, Math.round((s.start - pad) * fps)), to = Math.round((s.end + pad) * fps);
  return <Sequence from={from} durationInFrames={Math.max(1, to - from)} layout="none">{children}</Sequence>; };
/** reel time of a recording event, e.g. mark(R, 'click:generate') — undefined if it isn't on screen in this reel */
export const mark = (R: Resolved, name: string): number | undefined => R.marks[name];
