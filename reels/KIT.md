# KIT — writing a planned reel

A planned reel is a folder `~/reels-run/plans/<slug>/`:

| File | What it is |
|---|---|
| `plan.json` | type, topic, length target, timeline, voiceover, camera beats |
| `capture.json` | the recording script the runner plays against the demo app (APP-MAP.md has the pages and selectors) |
| `content/*.json` | optional: what the app "generates" on camera (flashcards.json / quiz.json / course.json) |
| `Reel.tsx` (+ any `./*.tsx`) | the reel's own Remotion code, built from the kit |

`plan.sh validate <slug>` checks all of it offline in seconds. Run it after every edit.

## plan.json
```json
{
 "slug": "adaptive-forces-run",            // = folder name; lowercase-hyphen
 "feature": "adaptive",                    // agent | quiz | flashcards | autopilot | overview | adaptive
 "topic": {"subject": "Physics", "topic": "Forces and motion", "level": "younger"},
 "format": "one line: the shape you chose and why it suits this reel",
 "hook": "the first words / on-screen line",
 "seconds": [25, 45],                      // the final length must land inside (15-60)
 "timeline": [
  {"id": "hook", "kind": "scene", "dur": 2.8},                                   // a designed scene, fixed length
  {"id": "run",  "kind": "footage", "from": "deck_open-0.3", "to": "ff_end+0.5"} // a slice of the recording between two anchors
 ],
 "beats": [{"ev": "results_open", "region": {"x": 300, "y": 120, "w": 720, "h": 520}}],   // optional camera framing
 "vo": {"voice": "Belle B", "lines": [
   {"text": "…", "at": "seg:hook+0.2"},       // seconds after a segment starts
   {"text": "…", "at": "ev:results_open+0.3"},// when a recording moment is on screen
   {"text": "…", "end": "end-1.2"}           // ends 1.2 s before the reel does
 ]}
}
```
**Anchors** name a moment in the recording: `rec_start`, `rec_end`, any `mark` you put on a capture step, or `click:<as>`;
then optional `#n` (n-th occurrence) and `+s`/`-s`. `resolve_plan.py` lists the known anchors when one is wrong.
**Voice**: 2-10 lines, ≤ 600 characters. Overlapping lines are pushed later; if the words outrun the picture the last segment is
held up to 3 s, beyond that `check` fails: cut words or lengthen a segment. Every reel keeps ≥ 1 s of picture after the last word.
**Beats** (optional): `region` is a page box in the 1320×860 viewport, `"WIDE"`, or `"click"`; the automatic camera already
follows clicks and typing, so add beats only to frame something it wouldn't (a results panel, a chart).

## capture.json
`{"name": "<slug>", "start_url": "/autopilot", "viewport": {"w": 1320, "h": 860}, "steps": [...]}`
Steps: `pause {ms ≤ 5000}` · `hover {target}` · `click {target, as?, expect_url?}` · `type {text}` (≤ 180 chars total) ·
`wait {for: {load|url|enabled|css|role+name|text}, cut?}` · `press {key, times?}` · `scroll {dy, ms}` · `speed {k: fast|normal, x?}` ·
any step can carry `"mark": "name"`. Start URL per type is checked (`validate_capture.py`).
The recorder is frame-stepped: animations are smooth at any speed, the real mouse glides to each target, a missing target fails
in 20 s. Recording is slow in real time (roughly 8-10× the clip length), so keep scripts purposeful.

## Reel.tsx
```tsx
import React from 'react';
import { ReelShell, Seg, AppWindow, Ground, Glow, Grad, Logo, Panel, Steps, C, TYPE, SAFE, useT, enter, exit, typed, rand, seg, mark, type Resolved } from '../../kit';
export default function Reel({ R }: { R: Resolved }) {
  return <ReelShell R={R}>                       {/* black ground, font, voice + music + sfx, captions */}
    <Ground pattern="grid" />
    <Seg R={R} id="hook">…your scene…</Seg>        {/* children only render during that segment; useT() = seconds into it */}
    <Seg R={R} id="run"><AppWindow R={R} id="run" layout={{ url: 'the-memora.com/flashcards', midY: 950 }} /></Seg>
  </ReelShell>; }
```
- `AppWindow` = the real recording in a browser frame, with the automatic camera, drawn cursor, click ripples and the
  "Sped up" chip (shown exactly while the recording ran fast). `layout`: `w` (920), `midY` (950), `hMax` (1100), `chrome`, `url`, `glow`.
- `Ground` (`dots` | `grid` | `cross` | `plain`), `Glow`, `Grad` (gradient text), `Panel`, `Logo`, `Steps` (step tracker).
- Motion: `useT()`, `enter(t, start, dur)`, `exit(t, end, dur)`, `typed(text, t, start, cps)`, `rand(seed)`, `easeOut`, `easeInOut`.
- `mark(R, 'results_open')` = reel time of a recording event (to sync scene graphics with the footage).
- `ReelShell` props: `captions={{ y, variant: 'pill' | 'lower' }}` or `false` (only if the words are shown another way);
  `sfx=[{ at, kind: 'click'|'key'|'done'|'whoosh' }]` in reel seconds (clicks and typing in footage already have sound).
- Tokens: `C` colors, `TYPE` sizes (nothing under 26 px), `SAFE` (keep text between y 220 and 1590: Instagram covers the rest).

`lint_reel.py` enforces: only `react`, `remotion`, `../../kit` and local imports; no network, timers, effects, randomness or
dates (frames render out of order — everything is a pure function of time); every timeline segment has a `<Seg>`, every footage
segment an `<AppWindow>`; no urgency copy, no user/scale counts.
