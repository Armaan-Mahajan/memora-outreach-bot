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

## status

Under active, one-feature-at-a-time construction. Nothing here posts to Instagram automatically — that needs a Make.com hookup that doesn't exist yet. Reels are intentionally not built (needs real screen recording, different problem for a different week).

Solo project.
