// Small deterministic animation helpers. Everything is a pure function of time (no timers, no randomness):
// Remotion renders frames out of order and in parallel.
import { useCurrentFrame, useVideoConfig } from 'remotion';
export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const easeOut = (x: number) => 1 - Math.pow(1 - clamp01(x), 3);
export const easeInOut = (x: number) => { const k = clamp01(x); return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; };
/** seconds since the start of the current <Sequence>/<Seg> */
export const useT = () => { const f = useCurrentFrame(); const { fps } = useVideoConfig(); return f / fps; };
/** 0→1 over [start, start+dur] seconds, eased out */
export const enter = (t: number, start = 0, dur = 0.35) => easeOut((t - start) / dur);
/** 1→0 over the last `dur` seconds before `end` */
export const exit = (t: number, end: number, dur = 0.3) => 1 - easeOut((t - (end - dur)) / dur);
/** characters of `text` revealed at time t when typed at `cps` chars/s from `start` */
export const typed = (text: string, t: number, start = 0, cps = 28) => text.slice(0, Math.max(0, Math.floor((t - start) * cps)));
/** deterministic pseudo-random in [0,1) from an integer seed (use instead of Math.random) */
export const rand = (seed: number) => { const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453; return x - Math.floor(x); };
