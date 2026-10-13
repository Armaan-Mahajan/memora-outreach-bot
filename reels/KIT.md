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
  {"id": "run",  "kind": "footage", "from": "ff_start", "to": "ff_end", "max": 4}  // a slice of the recording between two anchors;
                                                                                 // "max": at most 4 reel seconds (plays faster to fit, ≤ 6×)
 ],
 "beats": [{"ev": "results_open", "region": "box"}],   // optional camera framing (see Beats)
 "vo": {"voice": "Belle B", "lines": [
   {"text": "…", "at": "seg:hook+0.2"},       // seconds after a segment starts
   {"text": "…", "at": "ev:results_open+0.3"},// when a recording moment is on screen
   {"text": "…", "end": "end-1.2"}           // ends 1.2 s before the reel does
 ]}
}
```
**Anchors** name a moment in the recording: `rec_start`, `rec_end`, any `mark` you put on a capture step, or `click:<as>`;
then optional `#n` (n-th occurrence) and `+s`/`-s`. `resolve_plan.py` lists the known anchors when one is wrong.
**`max`** caps a footage segment's length: a longer slice plays faster to fit (frames dropped, up to 6×; beyond that `check` fails —
record that stretch faster with `speed` instead). Use it for fast-forwards; combine with `speed: fast` (x 8-12) in the capture so
little needs dropping.
**Voice**: 2-10 lines, ≤ 600 characters. **Budget 2.4 words per second** (the roster voices on eleven_v4 measure 2.4-2.6;
estimating faster is how lines end up ~25% too long). `validate` prints each line's estimate. Overlapping lines are pushed later;
if the words outrun the picture the last segment is held up to 3 s, beyond that `check` fails: cut words or lengthen a segment.
Every reel keeps ≥ 1 s of picture after the last word.
**Beats** (optional): the automatic camera frames typing (a read-zoom on the field, released 0.7 s after the typing ends unless
another shot takes over), the Agent flow, and results pages. In the Agent flow the outline and the build are framed as the
**whole dialog** (every node in view), and a course is shown **full-page**; it zooms in only for a flashcard or quiz used
inside a lesson — clicks whose `as` contains `card`, `flip`, `quiz`, `option`, `answer`, `check` or `mcq` — and goes back to
full-page 1.6 s after the last one. Held shots are perfectly still (no slow push-in). Everything else stays wide; add a beat to frame something it
wouldn't (a results panel, a chart, a card). `region` is one of:
- `"box"` — **preferred**: the element the event recorded. Clicks record their target; for any other moment put `"mark"` and
  `"box": <target>` on the capture step (e.g. `{"do":"wait","for":{"text":"Review Complete"},"mark":"results_open","box":{"css":"…"}}`).
- `"click"` — the click target with context around it. `"WIDE"` — the whole window.
- `{x, y, w, h}` — a box in the 1320×860 viewport. Only from a recording you've looked at, never guessed from what the page
  "probably" shows: content depends on the seeded data (e.g. Autopilot has two exam cards, not four).
`check` measures every beat against the real recording and **fails if the camera would settle on an empty area**.

## capture.json
`{"name": "<slug>", "start_url": "/autopilot", "viewport": {"w": 1320, "h": 860}, "steps": [...]}`
Steps: `pause {ms ≤ 5000}` · `hover {target}` · `click {target, as?, expect_url?, cut?}` (cut: edit out the wait for the next page) · `type {text}` (≤ 180 chars total) ·
`wait {for: {load|url|enabled|css|role+name|text}, cut?}` · `press {key, times?}` · `scroll {dy | to: "top"|"bottom", ms}` (scrolls the
open dialog if there is one, else the main scroll area; `to` goes exactly to that end) · `speed {k: fast|normal, x?}` ·
any step can carry `"mark": "name"` (plus `"box": <target>` to record where an element is, for a `"box"` beat). Start URL per
type is checked (`validate_capture.py`).
The recorder is frame-stepped: animations are smooth at any speed, the real mouse glides to each target, a missing target fails
in 20 s. Recording is slow in real time (roughly 10-13× the clip length: every frame is a lossless screenshot), so keep scripts purposeful.

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
- `RunProgress` — a progress bar in the app's style pinned at the top of the reel, counting the recording's own clicks:
  `<RunProgress R={R} count={['correct','incorrect']} total={10} label="…" tally={{ correct: '✓', incorrect: '✗' }} />` (top level,
  not inside a `<Seg>`; it shows while those clicks are on screen). Don't put another label at the top while it shows.
- Click and typing sounds are automatically silent while the recording ran sped up.
- `mark(R, 'results_open')` = reel time of a recording event (to sync scene graphics with the footage).
- `ReelShell` props: `captions={{ y, variant: 'pill' | 'lower' }}` or `false` (only if the words are shown another way);
  `sfx=[{ at, kind: 'click'|'key'|'done'|'whoosh' }]` in reel seconds (clicks and typing in footage already have sound).
- Tokens: `C` colors, `TYPE` sizes (nothing under 26 px), `SAFE` (keep text between y 220 and 1590: Instagram covers the rest).

`lint_reel.py` enforces: only `react`, `remotion`, `../../kit` and local imports; no network, timers, effects, randomness or
dates (frames render out of order — everything is a pure function of time); every timeline segment has a `<Seg>`, every footage
segment an `<AppWindow>` — each segment id must appear in the code as a string literal (`id="run"`, or listed in an array you
map over: `{['open', 'run'].map(id => <Seg R={R} id={id} key={id}>…)}`); no urgency copy, no user/scale counts.

## Agent courses (`content/course.json`)
Plan a real-sized course: **7-9 nodes**, even if the reel only opens the first two or three (nodes after the first generate in
parallel, so the build takes no longer on camera). Author `node_content` for at least the first 3 nodes (and any node the reel
opens); the rest get a key-concept outline from the demo app. `expected_tokens` and `structure.error` are optional (install fills
them; the outline no longer shows word estimates). `validate` checks all of this.

## Running phases
`prepare`, `record` and `finish` report in `status.json` (poll that). `validate`, `voice` and `check` report in
`status-<phase>.json` and their own output, so running them while `prepare` works never overwrites its status.
`check` also re-verifies the recording itself: a clip cut off mid-write (e.g. the container paused) fails with
"RECORDING UNREADABLE" — re-record it with `plan.sh record <slug>`.
