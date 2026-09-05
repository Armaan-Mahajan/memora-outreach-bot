# Batch run

The brief for the scheduled task. Every firing starts a **fresh, empty cloud
container with no memory of how any of this was built**, so this file is the
whole story — read it in full before doing anything. See `pipeline-plan.md`
for the reasoning behind each stage; this file is the "just tell me what to
run" version of the same plan.

## Where you are

**A Cowork scheduled task running entirely in the cloud container — no
device binding, and nothing here touches Armaan's Mac.** This isn't
assumed, it's been checked (see pipeline-plan.md §1 and the 2026-09-04
phone capability test): Playwright/Chromium is pre-installed, real outbound
network reaches npm/PyPI/GitHub, and the Supabase MCP connector works —
**but is proxied outside this container's own restricted shell egress**,
the same way memora-growth's MCP connectors are proxied outside ITS shell's
zero-network local Mac environment. Concretely: **the plain shell cannot
reach `*.supabase.co` directly** (confirmed by the capability test's own
failed raw upload attempt, and reconfirmed 2026-09-05 against Make.com's
webhook host too — this is a general outbound allowlist, not a
Supabase-specific block) — every Supabase read, write, and file upload
in this run goes through `execute_sql` (an MCP tool call), never through
`curl`/`requests`/a raw HTTP client in the shell.

**First step of every run, before anything else:**

```bash
git clone <REPO_URL> outreach-bot && cd outreach-bot
```

`<REPO_URL>` — fill in once the repo exists; see pipeline-plan.md §7's open
"where the pipeline repo lives" item. A fresh container has nothing on disk
otherwise: no templates, no `topics.json`, no `pipeline/` scripts.

Supabase project: `memora-outreach` (id `dtyiuknezuzqohdxicbg`,
`https://dtyiuknezuzqohdxicbg.supabase.co`). This is the isolated dashboard
project, not memora-web's — never point anything at memora-web's project.

## Hard rules

- **Format must be exactly `single_image`, `slideshow`, or `reel`** on the
  `outreach_drafts` insert — an actual `CHECK` constraint on the real
  table, underscore not hyphen. `feature` is also `NOT NULL`; for
  slideshows without a natural feature tie-in, `pipeline/publish.py`
  defaults it to the sentinel `"general"` (see that script's comment) —
  don't leave it blank.
- **Never mention or imply a user count or scale number** in any post, in
  any form. Memora is pre-launch (~86-90 registered users, 200+ beta
  testers) — content should read as authentic and early, never as an
  established brand.
- **No countdown/urgency elements, no fabricated testimonials or stats.**
  The audience skews to minors; see `claude-knowledge/outreach-bot-brief.md`
  for the full compliance rationale.
- **Slideshows only draw topics from `topics.json`.** Stage 2 does not get
  to invent a topic — the allowlist exists specifically to keep curriculum
  content out of territory where boards (IB/AP/GCSE/HSC/...) disagree.
- **Single-image cards only use the 7 layouts under
  `single-image-card/layouts/`**, assigned by `pipeline/assign.py` — never
  let Stage 2 invent a new layout or bypass the rotation.
- **Posting nothing beats posting something wrong.** If a stage fails after
  the repair loop's 3 attempts, or something looks wrong that isn't covered
  below, stop and report rather than improvising or shipping anyway — same
  discipline as memora-growth.
- **A batch's failures are independent.** One post failing (render error,
  repair-loop exhaustion, upload failure, verification failure) must not
  take down the rest of the batch. Mechanically: every subagent call in
  Stages 3, 8, and 9 is spun up fresh, per post, per stage — never one
  subagent handling more than one post's fact-check, upload, or
  verification in the same call. An error or bad tool call inside one
  post's subagent has no way to reach another post's, because they share
  no context at all. Run the posts in the batch one at a time in the
  orchestrator's own loop (not as parallel subagents) — Stage 1's
  duplicate-avoidance depends on each post seeing the ones already queued
  earlier in the same batch, which only works if they're assigned in
  order.

## Steps

Run once per post in the batch (`--count` from the invocation; batch
size/cadence is still an open decision — see pipeline-plan.md §7 — so
until that's settled, run whatever count and format split you were
actually asked for).

### Stage 0 — Load inputs

- `topics.json` (the allowlist).
- Recent history:
  ```sql
  select id, format, feature, topic, archetype, layout, headline, caption, status, created_at
  from outreach_drafts
  order by created_at desc
  limit 20;
  ```
  Save the result as `history_raw.json`, then:
  ```bash
  python3 pipeline/history.py history_raw.json > history_shaped.json
  ```
  Re-run this reload before assigning each subsequent post in the batch,
  not just once at the start — otherwise post 2 can't see post 1's
  freshly-queued row and the duplicate-avoidance in Stage 1 loses its
  teeth partway through a multi-post batch.
- `claude-knowledge/brand-voice.md`, `claude-knowledge/memora-overview.md`,
  and `claude-knowledge/outreach-bot-brief.md` for voice and product facts.
- The target format's template + render script (`single-image-card/` or
  `slideshow/`).

### Stage 1 — Plan the batch (deterministic)

```bash
python3 pipeline/assign.py --format <single_image|slideshow> --topics topics.json --history history_shaped.json
```

Gives you the assignment object (feature+layout, or topic+archetype) for
this post. Do not override this pick — it's the cheapest and most reliable
duplicate-avoidance layer specifically because it's deterministic.

### Stage 2 — Write the content (you, Claude)

Given the assignment, the voice docs, and `history_shaped.json`'s
`recent_by_feature` (or the relevant slice for the topic), write
`content.json` matching the target layout/format's `content-example.json`
shape. Don't repeat the angle of anything in the last ~10-15 posts for that
feature/topic.

### Stage 3 — Verify the claims (Sonnet subagent)

For anything with a factual claim (mainly slideshows, and `flow-outline`'s
hardcoded-adjacent copy), spin up a **fresh Agent tool call on Sonnet**
(`model: "sonnet"`) — zero memory of Stage 2 — and hand it the content
without "this is our content" framing. Ask it to find what's wrong and say
what it actually checked, not just return a bare verdict. This is a tool
call inside this same run, not a separate scheduled task. Confirmed
working 2026-09-04 (see pipeline-plan.md Stage 3).

Sonnet, not Haiku, deliberately: this stage is a judgment call about
factual accuracy, not a mechanical retype, so it needs a model that's
actually good at spotting a wrong or overstated claim. One fresh subagent
per post — never reuse one across posts, and never hand a single subagent
more than one post's content (see the batch-independence hard rule above).

Anything below confident goes into a `notes` string, carried through to
Stage 9.

### Stage 4 — Render (deterministic)

```bash
python3 single-image-card/render.py <layout> content.json
# or
python3 slideshow/render_slideshow.py content.json
```

Already asserts and raises on KaTeX errors, text/chrome collisions or hero
overflow, and the 8 MB file-size limit. If it raises, that's Stage 6's
repair loop, not a run-ending failure.

### Stage 5 — Look at it (you, Claude, vision)

Required for every post, both formats. Use the Read tool on the rendered
JPEG(s) — for slideshows, the contact sheet first, individual slides only
if something looks off. Check for orphaned words, cramped/empty
composition, whether the cover earns a swipe (slideshows), whether the deck
reads as a coherent sequence. Output: pass, or a specific list of fixes.

### Stage 6 — Repair loop

If Stage 4 or 5 failed, edit `content.json` and re-run 4-5. **Cap at 3
attempts.** On exhaustion, stop and report this post as failed — do not
ship a broken render, do not keep looping, and do not let it block the
rest of the batch.

### Stage 7 — Duplicate backstop (deterministic)

```bash
python3 pipeline/checks.py content.json history_shaped.json
```

**Flags, never blocks.** If `flagged` is true, carry its `note` into
Stage 9's `notes` column rather than discarding the post.

### Stage 8 — Upload the rendered image(s) (Haiku subagent)

**No relay exists for this — the orchestrator pays the token cost
directly.** The GitHub relay (drafts/ + SSH deploy key + launchd) was
torn down 2026-09-05, and the Make.com relay meant to replace it was
never built: reachability testing that same day found no Claude-driven
shell (this cloud sandbox, or a Mac linked via the device bridge) can
reach Make's webhook, or any third-party host, at all. Google Drive and
Dropbox were checked too as a possible "upload here, hand Make the URL"
step; neither has a way to receive a file without the bytes passed
inline as a tool-call argument, so neither would have helped anyway. See
`pipeline/publish.py`'s module docstring for the full history. None of
this touches Make.com's *other*, separate job of actually posting a
queued draft to Instagram later — that's a future build, unaffected.

For each rendered image, in slide order, spin up a **fresh Agent tool
call on Haiku** (`model: "haiku"`) — one subagent per image, or one
subagent looping over every image in this one post, but **never one
subagent spanning more than one post**. Haiku, not Sonnet, because this
step is purely mechanical (read a pre-generated chunk file, relay its
exact text into a tool call, repeat) with no judgment involved — running
it on the cheap model keeps both the dollar cost and the ~60-90k tokens
of base64 noise per image out of the orchestrator's own context entirely.

Hand the subagent:

```bash
python3 pipeline/publish.py chunk-upload \
  --supabase-url "https://dtyiuknezuzqohdxicbg.supabase.co" --anon-key "$SUPABASE_ANON_KEY" \
  --format <format> --slug <slug> --index <1-based index> \
  --image <path to rendered jpg> --out-dir <scratch dir>
```

This writes `00_create_table.sql`, `01_chunk_0000.sql` … `01_chunk_NNNN.sql`,
`02_verify.sql`, `03_trigger.sql`, `04_cleanup.sql`, and `manifest.json`
into `--out-dir`, and prints the manifest. Run them via `execute_sql`, in
this exact order:

1. `00_create_table.sql`
2. every `01_chunk_NNNN.sql`, ascending, none skipped or reordered
3. `02_verify.sql` — **`hash_matches` must be `true` before continuing.**
   `false` means a chunk got dropped or duplicated; do not run
   `03_trigger.sql` on a failed verify. Report this image failed and stop
   — this is exactly the silent-corruption failure mode chunking exists
   to catch, don't paper over it with a retry.
4. `03_trigger.sql` — the actual upload
5. `select status_code, content, error_msg from net._http_response where id = <request_id>;`
   — **confirm `status_code = 200` and `content` contains `"ok":true`.**
6. `04_cleanup.sql` — run regardless of steps 4-5's outcome, so a failed
   attempt doesn't leave chunk rows behind.

Return the manifest (`path`, `public_url`, `bytes`) and pass/fail verdict
to the orchestrator for every image. Do not proceed to Stage 9 on an
unconfirmed upload. `$SUPABASE_ANON_KEY` is the legacy anon JWT the
`upload-asset` Edge Function needs to authenticate the invocation — get
it via `mcp__Supabase__get_publishable_keys` if it's not already in the
environment; never hardcode it in a committed file.

### Stage 9 — Independently verify, then queue the draft

Don't take Stage 8's subagent's word for it. Spin up a **second, separate
fresh Agent call** (Haiku is enough — this is a numbers comparison, not a
judgment call) that did *not* do the upload itself, and for every image in
this post have it run:

```sql
select (metadata->>'size')::int as stored_bytes
from storage.objects
where bucket_id = '<bucket>' and name = '<path from the manifest>';
```

Compare `stored_bytes` to the `bytes` value from that image's Stage 8
manifest. **They must match exactly.** A mismatch means the stored object
is truncated or corrupted even though Stage 8's HTTP call reported
200/ok:true — treat it as a failed upload for this post and do not
continue to the insert below. This is the "posting nothing beats posting
something wrong" rule, applied specifically to the one failure mode that
can slip past a 200 status code.

Once every image for this post is confirmed uploaded (Stage 8) AND
independently verified (this stage), have that same subagent run:

```bash
python3 pipeline/publish.py insert-sql \
  --format <format> --archetype <archetype> \
  [--feature <feature>] [--topic <topic slug>] [--layout <layout>] \
  --content content.json \
  --asset-urls <public_url_1> [<public_url_2> ...] \
  --notes "<Stage 3 / Stage 7 flags, or omit>"
```

Run the printed `sql` via `execute_sql` once, then re-query the row back
by its returned `id` to confirm it actually exists with `status =
'pending'` and the expected `asset_urls` — don't just trust the INSERT's
own "returning id" as proof it landed. That's the draft queued as
`status='pending'` for Armaan's dashboard review — nothing posts to
Instagram itself yet (Make.com automation for posting is a separate,
later build, unrelated to the upload path above).

One fresh subagent per post here too, same reasoning as Stages 3 and 8.

### Stage 10 — Report

Per post: made / flagged / failed, with reasons. Stdout is fine for now —
the dashboard is the real review surface, this is just for debugging a run
that didn't go as expected.
