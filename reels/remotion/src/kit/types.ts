import type { Ev, Regions, Beat } from '../director';
/** One piece of the reel timeline, in reel seconds. Footage segments play clip time [clipIn, clipOut], `rate`× fast when the plan capped their length. */
export type Segment = { id: string; kind: 'scene' | 'footage'; start: number; end: number; clipIn?: number; clipOut?: number; rate?: number };
export type Word = { w: string; s: number; e: number };
export type VoLine = { at: number; dur: number; file: string; text: string; words: Word[] };
/** Everything a generated reel needs, produced by tools/resolve_plan.py from the plan + the real recording. */
export type Resolved = {
  slug: string; dur: number; hold: number;
  segments: Segment[];
  footage: { clip: string; events: { events: Ev[] }; regions: Regions; beats: Beat[]; clipDur: number };
  /** recording events mapped onto the reel clock: "click:generate", "results_open", … → reel seconds (only events inside footage segments) */
  marks: Record<string, number>;
  vo: { lines: VoLine[] }; voDir: string;
};
