# Cursor prompt: Memora deterministic demo build (v2)

Paste everything below into Cursor, pointed at a fresh clone of the memora-web repo. This revises an earlier version: this build runs against the real Supabase backend with a real (disposable) test account, strips the OpenAI integration out entirely rather than gating it, and works from bot-authored content files instead of a one-time fixture set.

---

## Context

Memora (the-memora.com) is a Next.js 16 / React 19 app using Supabase for auth/data and OpenAI's Responses API for AI generation, deployed on Vercel. I'm building an Instagram outreach bot that needs to capture polished screen recordings of the product. Recording against live generation doesn't work: it's slow, non-deterministic, and the content shown needs to be whatever the outreach bot decides to showcase that day, not whatever a real prompt happens to generate.

Your job: clone this repo into a sibling directory, remove the real AI-generation code entirely, and replace it with a mechanism that plays back content from simple data files — through a real Supabase-backed account, with the exact same streaming and "reasoning" UX the real product has, so recordings are indistinguishable from the live product.

## The test account

Use this real, disposable Supabase account for everything — it already exists in the real project:

- UID: `4c4fb5de-7844-465e-9fb3-0ce4d8fdbc2a`
- Name: John Doe
- Email: `john.doe@the-memora.com`
- Password: `xymHez-cycku3-dardek`

Every piece of demo content gets written into the real tables under this one UID. Never read, write, or touch any other user's data.

## Setup

1. Clone the repo into a new sibling directory, e.g. `../memora-demo`, as an independent working copy — not a subfolder of the existing repo.
2. Inside that clone, create and check out a new branch, e.g. `demo-recording-mode`. Never merge it toward `main`.

## Strip the AI generation code — don't just gate it

Remove the real OpenAI integration from this clone entirely, not behind a flag:

- Gut the actual model calls in `src/app/api/agent/_utils/openai.ts`, `src/app/api/flashcards/_utils/openai.ts`, `src/app/api/mora/_utils/openai.ts`, `src/app/api/quizzes/_utils/openai.ts`, and any route that calls into them directly.
- This clone should run with zero OpenAI API keys and no OpenAI SDK calls actually firing — not "configured but unused," genuinely not wired up.
- Reimplement the generation routes (`generate-structure`, `generate-node`, `edit-structure`, `generate-card`, `generate-answer`, `hint`, `generate-mcq`, `generate-oe`, the `mcq-generate-*`/`oe-generate-*` helpers, `name-flow`, `repair-diagram`, and Mora's main `[id]` chat route) to read from the bot-authored content files described below instead. The request/response shape and streaming behavior the frontend already expects must stay identical — no frontend changes should be needed.
- The credit system (`src/credits/`, `decrease_user_credits`/`add_permanent_credits`) has nothing to gate anymore once there's no real generation call — either skip the credit-check-and-deduct step in these routes, or just top up the test account's balance once via `add_permanent_credits` so it's never a factor.

## Content data structures — the bot fills these in

Add a `demo-content/` directory at the repo root with one editable data file per content type. Match the real schema rather than inventing one — check `src/database.types.ts` for the actual tables/RPCs (`courses`, `flows` + `flow_messages`, `create_flashcard_deck`/`get_flashcard_deck_by_id`, `create_quiz`/`get_quiz_by_id`, `profiles`, `create_subject`/`create_topic`) so the seed script below writes content the real app already knows how to read:

- `demo-content/course.json` — a syllabus plus the full Agent course structure and node content, shaped to match `courses` / the agent's `course-storage.ts`.
- `demo-content/flashcards.json` — one deck's worth of cards, shaped to match `create_flashcard_deck`.
- `demo-content/quiz.json` — one quiz (MCQ + open-ended mix, answers and explanations included), shaped to match `create_quiz`.
- `demo-content/mora-flow.json` — a scripted conversation as an ordered list of messages, each with its text and optionally a Mermaid diagram, KaTeX content, and a fake reasoning duration in seconds — shaped to match `flows` / `flow_messages`.

Add one script, `scripts/seed-demo-content.ts`, that reads whichever of these files exist and upserts their content into the real Supabase project under UID `4c4fb5de-7844-465e-9fb3-0ce4d8fdbc2a`. Make it idempotent — safe to edit a JSON file and re-run before every recording session without duplicating rows (delete-and-recreate that user's demo content, or upsert against fixed known IDs, your call).

This is the actual day-to-day workflow going forward: edit the relevant JSON file with whatever content should be shown that day, run the seed script once, then record. No code changes per session.

## Preserve the streaming and "reasoning" UX exactly

This matters as much as the content — recordings need to look like live generation, not a static page. I checked the real Mora route already (`src/app/api/mora/[id]/route.ts`): it responds with `Content-Type: text/event-stream` via a `TransformStream`, using a `sendEvent(writer, type, payload)` helper that emits named SSE events — including `reasoning_start` (`{ startedAt }`) and `reasoning_end` (`{ durationSec }`) — and it injects a specially-marked block into the message text (a fenced block tagged `system_message_ai_must_not_output_this_code_block` containing `Thought for N seconds`) that the frontend parses into its "thinking" indicator. There's a token/delta event alongside these for the actual streamed text — read the rest of that file to get its exact name and payload shape before reimplementing it.

For the demo version of this route: replay the pre-written message from `mora-flow.json` through this same event protocol. Emit `reasoning_start`, wait however long that message's fake reasoning duration says, emit `reasoning_end` with that duration, then stream the real text out via the same delta-event mechanism in small chunks with a short delay between them (a few words at a time reads well on camera) instead of sending it all at once. The frontend shouldn't need any changes, since it's speaking the protocol it already expects.

Do the same audit for any other streaming or progressive-reveal behavior elsewhere (Agent's node-content generation, for instance) and replicate whatever mechanism already exists rather than inventing a new one.

## Guardrails

- Never write to any UID other than `4c4fb5de-7844-465e-9fb3-0ce4d8fdbc2a`.
- Zero visual or styling changes — this needs to be pixel-identical to production, since it's recorded as real Memora footage. Only the content source, generation logic, and reasoning timing change.
- Don't touch the real repo. Never merge this branch toward `main`.
- Leave a short README in the clone covering: how to run the seed script, where each content file lives, and how the reasoning/streaming replay works — this needs to be editable later without re-discovering it.

## Done when

- The clone runs with zero OpenAI API keys configured and no OpenAI SDK calls actually firing anywhere.
- Logging in as `john.doe@the-memora.com` / `xymHez-cycku3-dardek` shows a dashboard populated with real Supabase-backed content for that account.
- Editing any `demo-content/*.json` file and re-running the seed script changes what's shown — no code changes needed.
- Opening the scripted Mora conversation shows the same "Thought for N seconds" reasoning indicator and word-by-word streaming the real product has, indistinguishable on camera from live generation.
- No other user's data is touched by any of this.
