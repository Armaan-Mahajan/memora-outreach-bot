# memora-outreach-bot

Instagram growth automation for [Memora](https://the-memora.com) — the AI study tool I'm building for 13-18 year-olds. This bot drafts posts about what Memora actually does, and queues them up for me to look at before anything gets anywhere near the real account. Nothing here auto-posts.

This repository is currently public so that Claude can access it when the scheduled task runs (1AM IST every day).

Commit history here starts fresh as of 2026-09-11 — older commits had exposed a Supabase anon/publishable key (since rotated) in a planning doc that never should have been committed. Squashing was simpler than rewriting 14 commits to scrub it out.

## what this actually does

- **tracks topics** worth posting about and avoids repeating itself (`topics.json`, `pipeline/history.py`)
- **designs posts as code** — single-image cards and slideshow carousels, no design tool in the loop. The templates, layouts, and design rationale live here (`post-templates/`) and are what the content-writing step looks at before writing copy — but the actual headless-Chrome rendering runs in a separate sibling repo, `memora-render-worker` (see below), not in this one.
- **queues drafts** into a Supabase table (`outreach_drafts`) that a small review dashboard reads from, so a human (me) approves, rejects, or schedules every single post by hand before it's real

## getting a rendered image into Supabase Storage

First attempt at this relayed raw base64 image bytes straight through a model's tool call into a SQL insert. Works, technically, right up until you notice a ~200KB image is a 250,000+ character string that has to get *retyped*, character by character, by an LLM, to go anywhere. Slow, absurdly expensive in tokens, and a single flipped character silently corrupts the image. Retired that approach the same day it was built.

Second attempt: this repo doubled as the relay instead. A rendered image got pushed here under `drafts/`, and a Supabase Edge Function fetched it straight from GitHub's raw content, server-side, and wrote it into Storage. It worked end-to-end on a real post, but keeping it unattended needed its own dedicated SSH deploy key, a macOS job polling for pending commits, and a repo-scoped read token on the Edge Function — a lot of standing infrastructure just to relay bytes past a wall.

Third attempt: Make.com as the relay instead, more directly — same day, before the second attempt's ink was even dry. Turned out to be a dead end: a reachability test found that no Claude-driven shell (this cloud sandbox, or a Mac linked via the device bridge) can reach Make's webhook host, or any third-party host, at all. Same restriction blocks a direct shell call to Supabase's own API, which is why every upload here used to go through `execute_sql`/`pg_net` instead. Google Drive and Dropbox were checked too, as a possible "upload here, hand Make the URL" step — both would still need the image's bytes passed inline as a tool-call parameter, so neither would have helped either.

Fourth attempt replicated the first attempt's workflow, but split into small pre-computed chunks that Postgres reassembled itself and a hash check caught any dropped chunk with, delegated to a cheap subagent model (Haiku) so the token cost and the noise both stayed off the main run — worked, but it was still fundamentally an LLM retyping image bytes as text, just in smaller, cheaper pieces.

**Current approach: pull rendering out of this repo's runtime entirely.** `memora-render-worker` is a separate Cloudflare Worker that does the actual headless-browser rendering *and* uploads the result straight to Supabase Storage itself, server-side, with its own credentials — no chunking, no relay, no image bytes ever passing through an LLM tool call in either direction. This repo inserts one row into a `render_requests` queue table per post and polls it; a Database trigger hands the row to the Worker over `pg_net`. See `memora-render-worker`'s own `SETUP.md` for how that's deployed, and this repo's `RUNBOOK.md` Stage 4 for exactly how the queueing works.

However, the Claude container's own network egress is restrictive enough (as of September 2026) that it can't reach either Supabase Storage or the Worker's `*.workers.dev` URL directly (confirmed 2026-09-11), so the vision-QC step (`RUNBOOK.md` Stage 5) that needs to actually look at the rendered image can't just fetch it from either of those. `memora-render-previews` is a small private repo that exists purely to bridge that gap — the Worker pushes a copy of every render there via GitHub's Contents API, which this container *can* reach.

## how the subagents are split up

A batch run isn't one model doing everything end to end — specific stages get handed off to fresh subagents, on purpose. Both currently run on Sonnet:

- **Fact-check (Stage 3).** For anything with a factual claim, a fresh subagent with zero memory of how the content was written gets handed the copy with no "this is our content" framing, and has to say what it actually checked, not just return a verdict.
- **Verify-and-queue (Stage 8).** By this point `memora-render-worker` has already rendered and uploaded the image(s) itself — there's no upload step left in this repo to hand to a subagent. What's left is a numbers check: comparing `storage.objects`' actual stored byte size against what the Worker itself measured and reported (`render_requests.sizes`), catching the one failure mode that can slip past a successful-looking upload. Still its own fresh subagent — kept independent so it doesn't just trust Stage 4's own success report, since this stage also does the actual `outreach_drafts` insert once the numbers check out.
- **One fresh subagent per post, never shared across posts, in either of the above.** A batch making several posts still runs them one at a time in the orchestrator's own loop — not as parallel subagents — because Stage 1's duplicate-avoidance needs each post to see the ones already queued earlier in the same batch. But within a post, every subagent call is spun up fresh: an error, a bad tool call, or a hallucination inside one post's fact-check or verify-and-queue subagent has no way to reach another post's, because they share no context at all. See `RUNBOOK.md` Stage 3 and Stage 8 for the exact procedure each one follows.

## status

Under active, one-feature-at-a-time construction. Nothing here posts to Instagram automatically — that uses a Make.com hookup that connects to the dashboard. Reels are intentionally not built in this repository since it'll be a local agent working (needs real screen recording, different problem entirely).
