import React, { useMemo } from 'react';
import { Audio, Sequence, staticFile, useVideoConfig } from 'remotion';
import { direct } from '../director';
import type { Resolved } from './types';
/** clip time → reel time, if that moment of the recording is on screen in some footage segment */
export const clipToReel = (R: Resolved, ct: number): number | undefined => {
  for (const s of R.segments) if (s.kind === 'footage' && ct >= (s.clipIn ?? 0) && ct < (s.clipOut ?? 0)) return s.start + (ct - (s.clipIn ?? 0)) / (s.rate ?? 1); return undefined; };
/** true while the recording ran sped up (speed event F > 1 until the next speed event): no click/key sounds there */
export const inFastStretch = (R: Resolved, ct: number): boolean => { const evs = R.footage.events.events, t0 = evs.find(e => e.type === 'rec_start')!.t;
  const last = [...evs].reverse().find(e => e.type === 'speed' && e.t - t0 <= ct + 1e-6) as any; return !!last && last.F > 1; };
/** Voiceover, the very quiet music bed (ducks under the voice), and the app's sound effects for whatever footage is on screen. */
export const ReelAudio: React.FC<{ R: Resolved; sfx?: { at: number; kind: 'click' | 'key' | 'done' | 'whoosh'; volume?: number }[] }> = ({ R, sfx = [] }) => {
  const { fps, durationInFrames } = useVideoConfig(); const end = durationInFrames / fps;
  const evs = R.footage.events.events, t0 = evs.find(e => e.type === 'rec_start')!.t;
  const D = useMemo(() => direct(evs, R.footage.regions, { w: 920, hMax: 1100 }, fps, t0, R.footage.clipDur, R.footage.beats), [R.slug]);
  const keys = evs.filter(e => e.type === 'keys').flatMap(e => e.times || []).filter(k => !inFastStretch(R, k - t0)).map(k => clipToReel(R, k - t0)).filter((x): x is number => x != null);
  const clicks = D.ripples.filter(r => !inFastStretch(R, r.t)).map(r => clipToReel(R, r.t)).filter((x): x is number => x != null);
  const done = evs.find(e => e.type === 'course_gen_done'); const doneAt = done ? clipToReel(R, done.t - t0) : undefined;
  const bed = (t: number) => { const speaking = R.vo.lines.some(l => t > l.at - 0.25 && t < l.at + l.dur + 0.25);
    return (speaking ? 0.045 : 0.09) * Math.min(1, t / 1.5) * Math.min(1, Math.max(0, (end - t) / 1.5)); };
  const at = (t: number) => Math.max(0, Math.round(t * fps));
  const file = { click: 'audio/click.wav', key: 'audio/softkey1.wav', done: 'audio/done.wav', whoosh: 'audio/click.wav' };
  return <>
    {R.vo.lines.map((l, i) => <Sequence key={'vo' + i} from={at(l.at)}><Audio src={staticFile(R.voDir + l.file)} /></Sequence>)}
    <Audio src={staticFile('audio/bed.wav')} volume={f => bed(f / fps)} />
    {keys.map((k, i) => <Sequence key={'k' + i} from={at(k)} durationInFrames={5}><Audio src={staticFile(`audio/softkey${1 + (i * 7) % 4}.wav`)} volume={0.045 + 0.01 * ((i * 5) % 3) / 2} playbackRate={0.96 + ((i * 37) % 9) / 100} /></Sequence>)}
    {clicks.map((c, i) => <Sequence key={'c' + i} from={at(c)} durationInFrames={8}><Audio src={staticFile('audio/click.wav')} volume={0.28} /></Sequence>)}
    {doneAt != null && <Sequence from={at(doneAt)} durationInFrames={55}><Audio src={staticFile('audio/done.wav')} volume={0.16} /></Sequence>}
    {sfx.map((s, i) => <Sequence key={'s' + i} from={at(s.at)} durationInFrames={55}><Audio src={staticFile(file[s.kind])} volume={s.volume ?? 0.2} /></Sequence>)}
  </>; };
