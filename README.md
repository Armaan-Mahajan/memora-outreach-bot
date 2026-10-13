# memora-outreach-bot

> **TODO:** add the Instagram profile URL here once the bot is live.

Instagram growth automation for [Memora](https://the-memora.com), the AI study tool I'm building for 13-18 year-olds. Two automations live here: a **reels pipeline** that films the real app and cuts it into short videos, and an **image pipeline** that drafts single-image posts and slideshow carousels. Both stop at a human: I review everything before it goes anywhere near the real account. Nothing here auto-posts.

This repository is public so that Claude can read it from scheduled cloud runs. Commit history starts fresh as of 2026-09-11: older commits had exposed a Supabase anon/publishable key (since rotated) in a planning doc that never should have been committed. Squashing was simpler than rewriting 14 commits to scrub it out.

## reels (`reels/`)

The reels are real product demos, not AI-generated video. Every frame of the app is a recording of the actual site doing the actual thing, and everything around it (framing, camera moves, captions, voiceover) is built in code. The whole run is unattended, so it's built to fail loudly instead of guessing.

### how a reel gets made

1. **A demo build of the app.** Recording happens against `demo-recording-mode-v2`, a branch of the private `memora-web` repo that never merges back toward `main`. Every AI route there plays back pre-written content (with the same response shapes and streaming as production), so a recording is identical every time, costs nothing, and can't produce a wrong answer on camera. A seed script resets a disposable demo account to a known state before each run.
2. **Capture** (`reels/capture/`). Playwright drives headless Chromium through a declarative script per reel (`capture/reels/*.json`) in stepped time: the page's clock, timers and animations are frozen between frames, and each frame moves everything forward exactly 1/30 s before it's captured, so 3D transforms and animations stay smooth however slow a screenshot is. `vproxy.cjs` delivers the app's responses on the same clock, so generation streams at its real pace, or genuinely faster under `speed: fast`. Every step logs a timestamped event for the edit to sync against.
3. **Voiceover** (`reels/voice/`). `tts.mjs` sends each script line to ElevenLabs and keeps the word-level timestamps, which drive the on-screen captions word by word.
4. **Edit and render** (`reels/remotion/`). Remotion builds the 1080x1920 reel in React: `director.ts` turns the recorded events into camera moves and a cursor, and the app window sits in a branded frame. The picture always runs at least a second past the last word; if the voice runs long, the last frame is held.
5. **Check and deliver.** Every output is checked for length, resolution and loudness (normalised to -15 LUFS), and a contact sheet of stills is looked at before anything is delivered. Finished MP4s land in the run's chat for me to review; nothing goes to Supabase, the dashboard or Instagram from this pipeline.

The scheduled session plans every reel itself. It picks the reel types and topics, then writes each reel's recording script, demo content, voiceover and Remotion scene code. No templates are involved. There are six reel types: Agent, quiz, flashcards, Autopilot, platform overview and adaptive run.

`reels/plan.sh` does the mechanical work in phases (`validate`, `prepare`, `check`, `finish`) and rejects any plan that breaks the rules. It checks content safety, curriculum-free generated content, selectors on the demo app only, and deterministic scene code. `reels/REELS-RUNBOOK.md` is the planner's brief, with `APP-MAP.md` (what the demo app shows and how to drive it) and `KIT.md` (the plan format and the Remotion kit) beside it.

Voices rotate across four ElevenLabs voices on `eleven_v4`. The old fixed four-reel pipeline, `reels/run.sh`, stays as the fallback if planning or recording fails outright.

### running unattended

Most runs happen while I'm asleep, so:

- **Temporary failures retry, permanent ones don't.** Network errors, timeouts and rate limits are retried a small, fixed number of times (clone, installs, seed, each recording, each voiceover line, each render), with one whole-run restart if setup fails before recording starts. A bad token or wrong password stops the run immediately. Every retry is written into the run's summary.
- **Secrets never touch disk in a repo.** The `memora-web` token is passed to git only as a one-off header for the clone and never written into `.git/config`; the ElevenLabs key lives only in Vault.

### what's next

A normal run makes three planned reels. Next: deeper coverage of the quiz viewer's adaptive rebuild, and the posting step once an approval flow exists.

## images (`pipeline/`, `post-templates/`)

The original automation: single-image posts and slideshow carousels, drafted daily by a Claude Code routine that follows `RUNBOOK.md` and ends its report with the commands to open the review dashboard locally.

- **Topics.** `topics.json` is a curated allowlist of about 190 topics, split roughly evenly between upper high school (AP, IB DP, A-Level) and younger high school (ages 13-15), each tagged with its `level`. `pipeline/assign.py` rotates through it deterministically and never repeats a topic until the list is used up. The content step isn't allowed to write about anything outside it.
- **Design as code.** Templates, layouts and design rules live in `post-templates/`, and the content step reads them before writing copy. Slideshows carry no diagrams on purpose: a wrong diagram looks right and slips past review.
- **Fact-checking.** A fresh subagent with no memory of how the copy was written checks every factual claim and has to say what it actually checked, not just return a verdict.
- **Verify-and-queue.** After rendering, another fresh subagent compares the size of the file actually stored against what the Worker reported, which catches the one failure that can look like a successful upload, and only then inserts the draft. Every post gets its own subagents and posts run one at a time, so a mistake in one can't leak into another, and each post can see the ones queued before it.
- **Rendering.** Rendering runs in a separate Cloudflare Worker, `memora-render-worker`, which renders and uploads to Supabase Storage itself. Earlier attempts pushed image bytes through an LLM's tool calls, through this repo, and through Make.com; each was slow, fragile or blocked by the sandbox's network limits. This repo just queues a `render_requests` row; a database trigger hands it to the Worker. A small private repo, `memora-outreach-render-previews`, mirrors every render so the run's vision check can see it, since the container can't reach Storage directly.
- **Review.** Finished posts are queued in `outreach_drafts`, which a small local review dashboard (`npm run dev`) reads; I approve, reject or schedule every post by hand. Approving doesn't post anything yet: the posting automation hasn't been built, and it will run from the dashboard side, never from a run.

## status

Under active, one-feature-at-a-time construction. Nothing here posts to Instagram automatically.
