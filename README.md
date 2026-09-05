# memora-outreach-bot

Instagram growth automation for [Memora](https://the-memora.com) — the AI study tool I'm building for 13-18 year-olds. This bot finds Instagram accounts worth engaging with, drafts posts about what Memora actually does, and queues them up for me to look at before anything gets anywhere near the real account. Nothing here auto-posts. That's on purpose, for now.

## what this actually does

- **tracks topics** worth posting about and avoids repeating itself (`topics.json`, `pipeline/history.py`)
- **renders posts from code** — single-image cards and slideshow carousels, no design tool in the loop (`post-templates/`)
- **queues drafts** into a Supabase table (`outreach_drafts`) that a small review dashboard reads from, so a human (me) approves, rejects, or schedules every single post by hand before it's real

## getting a rendered image into Supabase Storage

First attempt at this relayed raw base64 image bytes straight through a model's tool call into a SQL insert. Works, technically, right up until you notice a ~200KB image is a 250,000+ character string that has to get *retyped*, character by character, by an LLM, to go anywhere. Slow, absurdly expensive in tokens, and a single flipped character silently corrupts the image. Retired that approach the same day it was built.

Second attempt: this repo doubled as the relay instead. A rendered image got pushed here under `drafts/`, and a Supabase Edge Function fetched it straight from GitHub's raw content, server-side, and wrote it into Storage. It worked end-to-end on a real post, but keeping it unattended needed its own dedicated SSH deploy key, a macOS job polling for pending commits, and a repo-scoped read token on the Edge Function — a lot of standing infrastructure just to relay bytes past a wall.

Third attempt: Make.com as the relay instead, more directly -- same day, before the second attempt's ink was even dry. Turned out to be a dead end: a reachability test found that no Claude-driven shell (this cloud sandbox, or a Mac linked via the device bridge) can reach Make's webhook host, or any third-party host, at all. Same restriction blocks a direct shell call to Supabase's own API, which is why every upload here goes through `execute_sql`/`pg_net` instead. Google Drive and Dropbox were checked too, as a possible "upload here, hand Make the URL" step -- both would still need the image's bytes passed inline as a tool-call parameter, so neither would have helped either.

Current approach: no relay at all. The orchestrating model just pays the base64 cost directly, the same way the first attempt did -- except split into small chunks that Postgres reassembles itself (so no single call is enormous, and a dropped chunk gets caught by a hash check instead of silently corrupting the image), and delegated to a cheap subagent model so the cost and the noise both stay off the main run. The full history of why (including the base64 disaster and both relay detours) is in `pipeline-plan.md`, if you want the whole story.

## how the subagents are split up

A batch run isn't one model doing everything end to end -- specific stages get handed off to fresh subagents, on purpose, and the model each one runs on is chosen deliberately rather than defaulting to whatever's orchestrating the run:

- **Fact-check (Stage 3) runs on Sonnet.** For anything with a factual claim, a fresh subagent with zero memory of how the content was written gets handed the copy with no "this is our content" framing, and has to say what it actually checked, not just return a verdict. This one stays on the strong model on purpose -- it's a judgment call about whether a claim is right or overstated, not a mechanical task, so it needs a model that's actually good at spotting a wrong one.
- **Uploading the rendered image (Stage 8) runs on Haiku.** There's no relay moving image bytes anywhere anymore (see above) -- the orchestrator pays the base64 cost directly, via `pipeline/publish.py chunk-upload`, which splits the image into small pre-computed chunks and hands them to a subagent to relay into `execute_sql` calls one at a time. That's pure mechanical retyping with zero judgment involved, so it runs on the cheap model instead: Haiku's output pricing is roughly half Sonnet's, and just as importantly, the 60-90k tokens of base64 noise a real image produces never touch the orchestrator's own context at all.
- **Verifying the upload (Stage 9) runs on a second, separate Haiku subagent** -- not the one that did the upload. It independently re-queries `storage.objects` for the stored file's actual byte size and compares it against what was sent, before the draft gets queued. This exists because a dropped or duplicated chunk during the upload can still leave Supabase's own HTTP response reporting `200`/`ok:true` -- a self-reported success isn't the same as a second, independent check, so this stage doesn't take Stage 8's word for it.
- **One fresh subagent per post, never shared across posts, in any of the above.** A batch making several posts still runs them one at a time in the orchestrator's own loop -- not as parallel subagents -- because Stage 1's duplicate-avoidance needs each post to see the ones already queued earlier in the same batch. But within a post, every subagent call is spun up fresh: an error, a bad tool call, or a hallucination inside one post's fact-check or upload subagent has no way to reach another post's, because they share no context at all. See `RUNBOOK.md` Stages 3, 8, and 9 for the exact procedure each one follows.

## status

Under active, one-feature-at-a-time construction. Nothing here posts to Instagram automatically — that needs a Make.com hookup that doesn't exist yet. Reels are intentionally not built (needs real screen recording, different problem for a different week).

Solo project.
