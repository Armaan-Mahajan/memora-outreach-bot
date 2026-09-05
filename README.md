# memora-outreach-bot

Instagram growth automation for [Memora](https://the-memora.com) — the AI study tool I'm building for 13-18 year-olds. This bot finds Instagram accounts worth engaging with, drafts posts about what Memora actually does, and queues them up for me to look at before anything gets anywhere near the real account. Nothing here auto-posts. That's on purpose, for now.

## what this actually does

- **tracks topics** worth posting about and avoids repeating itself (`topics.json`, `pipeline/history.py`)
- **renders posts from code** — single-image cards and slideshow carousels, no design tool in the loop (`post-templates/`)
- **queues drafts** into a Supabase table (`outreach_drafts`) that a small review dashboard reads from, so a human (me) approves, rejects, or schedules every single post by hand before it's real

## getting a rendered image into Supabase Storage

First attempt at this relayed raw base64 image bytes straight through a model's tool call into a SQL insert. Works, technically, right up until you notice a ~200KB image is a 250,000+ character string that has to get *retyped*, character by character, by an LLM, to go anywhere. Slow, absurdly expensive in tokens, and a single flipped character silently corrupts the image. Retired that approach the same day it was built.

Current approach: this repo primarily functions as the relay. A rendered image gets pushed here under `drafts/`, and a Supabase Edge Function fetches it straight from GitHub's raw content, server-side, and writes it into Storage. No image bytes ever pass through a model's context — just a short URL does. The full history of why (including the base64 disaster) is in `pipeline-plan.md`, if you want the whole story.

## status

Under active, one-feature-at-a-time construction. Nothing here posts to Instagram automatically — that needs a Zapier hookup that doesn't exist yet. Reels are intentionally not built (needs real screen recording, different problem for a different week).

Solo project.
