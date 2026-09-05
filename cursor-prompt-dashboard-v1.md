# Cursor prompt: Outreach post-review dashboard (v1)

Paste everything below into Cursor. This builds the first version of the
internal dashboard where drafted Instagram posts get reviewed, approved or
rejected, and scheduled — before anything actually goes to Instagram.

---

## Context

Memora's outreach bot will run as two separate content pipelines: a
cloud-run one that generates single-image and slideshow (carousel) posts
from code-rendered templates (already built for single-image — see
`outreach-bot/single-image-card/`), and a separate local pipeline for Reels
later, since those need actual screen recording on my machine. Both
pipelines need to write their drafts somewhere a human reviews before
anything is public. That shared place is this dashboard.

This dashboard runs on its own separate Supabase project, not memora-web's
— see the data model section below for why and for the connection details.
Isolation was the deciding factor: this is new, unproven code, and a
mistake in it should never be able to reach product data.

This v1 covers single-image and slideshow drafts only — leave Reels out
entirely for now (their pipeline doesn't exist yet, and we haven't
confirmed they're feasible). Don't build anything Reels-specific; just
don't make choices that would block adding it later (e.g. keep the format
field an open enum, not a boolean).

This is an internal tool for one person (me) reviewing drafts before they
go live — not customer-facing. Keep it simple: no auth system, runs locally
via `npm run dev`, not deployed anywhere public. (Flag it back to me if
that assumption is wrong — I might want to check it from my phone later,
which would need a real deployment + login.)

There is deliberately **no inline post-editing UI** in this version. If I
want a draft changed, I'll prompt a separate Claude-driven process to edit
it directly (outside this dashboard's UI). What that means for you: the
data model must support an external process updating an existing draft's
fields and its rendered asset **in place** — same row, same identity, old
version overwritten — not just inserting new rows. Don't build anything
that assumes a draft is immutable once created.

## Data model — a separate Supabase project, already provisioned

This dashboard does NOT reuse memora-web's Supabase project. It runs on its
own, brand-new project — deliberately isolated, so nothing this dashboard
does (a bad migration, a bug, an exposed key) can ever touch product data.
The project is already created and the schema already exists, so you don't
need migration tooling or org-level Supabase access for this at all — just
wire the app up to it:

- Project URL: `https://dtyiuknezuzqohdxicbg.supabase.co`
- Publishable key (safe to put in `.env.local` / client bundle, this is
  the anon/publishable key by design): `sb_publishable_yAnp_s5dyP-Nu4BveMtk4g_FB2XB24c`
- `outreach_drafts` table already exists with:
  - `id` (uuid, pk, default `gen_random_uuid()`)
  - `format` (text — `'single_image'` | `'slideshow'` | `'reel'`; `'reel'`
    is a valid value even though nothing produces it yet)
  - `feature` (text — e.g. `'agent'`, `'flashcards'`, `'quizzes'`, `'mora'`)
  - `status` (text, default `'pending'` — `'pending'` | `'approved'` |
    `'rejected'` | `'scheduled'` | `'posted'`)
  - `headline`, `subhead`, `caption` (text)
  - `hashtags` (text array, default `{}`)
  - `content_json` (jsonb — the raw fill-in data that produced the
    render, e.g. matching `outreach-bot/single-image-card/content-example.json`'s
    shape for single-image drafts; opaque to this dashboard, just stored
    and displayed as-is, not parsed field-by-field, since slideshow's shape
    doesn't exist yet and shouldn't need this dashboard to change when it
    does)
  - `asset_urls` (text array, default `{}` — one URL for single-image,
    several in display order for slideshow)
  - `scheduled_for` (timestamptz, nullable)
  - `created_at`, `updated_at` (timestamptz, default `now()` — a trigger
    already bumps `updated_at` on every row update, so you don't need to
    set it manually)
- A `outreach-assets` Storage bucket already exists (public read) for the
  rendered images.
- Row Level Security is intentionally OFF on this table — this is a
  single-user, unauthenticated local tool with its own isolated project
  holding nothing but draft marketing copy, so this is an accepted
  tradeoff for v1, not an oversight. Don't "fix" it by enabling RLS without
  policies (that would just lock the app out); revisit only if this ever
  gets a real deployment or login.

## What the UI needs

Three views/tabs:

1. **Pending** — every draft with `status = 'pending'`. Each card shows its
   image(s) (all of them in order, for slideshow), headline, caption,
   hashtags, feature, and format, plus two buttons: **Approve** (sets
   `status = 'approved'`) and **Reject** (sets `status = 'rejected'`).
2. **Scheduling** — every draft with `status = 'approved'` (not yet
   scheduled) or `'scheduled'`. An approved-but-unscheduled draft gets a
   date field (a simple calendar/date-picker) and a time field; picking
   both and clicking a "Schedule" button sets `status = 'scheduled'` and
   stores the chosen timestamp in `scheduled_for`. Once scheduled, show it
   in a "scheduled" list sorted by `scheduled_for` so it's easy to see
   what's coming up. **Put a visible note here that scheduling only
   records intent — nothing actually posts to Instagram yet, since the
   Zapier integration isn't built.**
3. **Rejected** — every draft with `status = 'rejected'`. Just a list, no
   actions needed. Don't hard-delete rejected drafts; keep them around
   (useful for avoiding repeat content later).

## Setup

1. New sibling directory, e.g. `../outreach-dashboard`, as its own
   Next.js + Tailwind app — not a subfolder of memora-web, following the
   same pattern as `memora-demo`.
2. Point its Supabase client at the project URL and publishable key given
   above (its own `.env.local`, separate from memora-web's).
3. Seed one real example draft so this can be checked against something
   real, not an empty screen: upload
   `outreach-bot/single-image-card/output/feature-card-agent.png` to the
   `outreach-assets` bucket, and insert one `outreach_drafts` row
   referencing it (`format: 'single_image'`, `feature: 'agent'`,
   `status: 'pending'`, headline/subhead/caption/hashtags matching
   `outreach-bot/single-image-card/content-example.json`).

## Explicitly out of scope for this version

- Reels support (data model should allow it later; nothing else needed now)
- Inline editing of a draft's content or image
- Actually posting anything, anywhere (no Zapier integration yet)
- The generation pipeline itself (what decides what to draft, duplicate
  checking, rendering) — this dashboard only displays and manages what
  already landed in `outreach_drafts`
- Auth / public deployment

## Done when

- `npm run dev` shows the seeded Agent example under Pending, with working
  Approve and Reject buttons that update its row in Supabase.
- Approving it moves it to Scheduling; picking a date via the calendar
  picker and a time, then clicking Schedule, sets `status = 'scheduled'`
  and stores `scheduled_for`, and it shows up in the scheduled list.
- Rejecting a (separate, or re-seeded) draft moves it to the Rejected tab
  and it stays there rather than disappearing.
- Nothing in memora-web or its repo/Supabase project was touched at all —
  this app only ever talks to the new `memora-outreach` project above.
