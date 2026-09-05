# Batch run

The brief for the scheduled task. Every firing starts a **fresh, empty cloud
container with no memory of how any of this was built**, so this file is the
whole story — read it in full before doing anything. See `pipeline-plan.md`
for the reasoning behind each stage; this file is the "just tell me what to
run" version of the same plan.

## Where you are

**A Cowork scheduled task — plain, not bound to any device.** This got
built as a Mac-bound task for a while, specifically to work around an
unattended-git-push problem (see below); that's no longer needed. Once
Make.com is handling image delivery (see Stage 8), nothing in this run
touches git at all, so there's no reason for it to run anywhere but a
normal cloud container. **Not yet re-confirmed end-to-end as a plain
cloud task since this change** -- the last thing actually proven working
was the Mac-bound version, before the redesign below.

For the record, since it's a real platform boundary worth remembering:
two designs got tried and confirmed empirically on 2026-09-05 before
landing on "git push just isn't this run's job at all" as the actual
fix. A plain (non-device-bound) scheduled task can't push to GitHub in
normal permission mode (blocked at the command-classifier layer on the
very first `git clone`) or in `bypassPermissions` mode either
(clone/commit get through, but `git push` is rejected by a separate
git-egress proxy that skip mode has no effect on). There's no
self-service way to add a repo to that proxy's allowed set. None of this
matters for image delivery anymore -- Make.com's webhook relay (Stage 8)
never touches git -- but keep it in mind if some future stage ever needs
this run to push to GitHub for a different reason; the same wall is
still there.

Supabase project: `memora-outreach` (id `dtyiuknezuzqohdxicbg`,
`https://dtyiuknezuzqohdxicbg.supabase.co`). This is the isolated dashboard
project, not memora-web's -- never point anything at memora-web's project.
Every Supabase read, write, and file upload goes through `execute_sql` (an
MCP tool call) -- never a raw HTTP client in the shell.

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
  repair-loop exhaustion, upload failure) must not take down the rest of
  the batch.

## Steps

Run once per post in the batch (`--count` from the invocation; batch
size/cadence is still an open decision — see pipeline-plan.md §7 — so
until that's settled, run whatever count you were actually asked for).

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

### Stage 3 — Verify the claims (subagent)

For anything with a factual claim (mainly slideshows, and `flow-outline`'s
hardcoded-adjacent copy), spin up a **subagent** — a fresh Agent tool call
with zero memory of Stage 2 — and hand it the content without "this is our
content" framing. Ask it to find what's wrong and say what it actually
checked, not just return a bare verdict. This is a tool call inside this
same run, not a separate scheduled task. Confirmed working 2026-09-04 (see
pipeline-plan.md Stage 3).

Anything below confident goes into a `notes` string, carried through to
Stage 8.

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
Stage 8's `notes` column rather than discarding the post.

### Stage 8 — Publish to the queue

**Not finalized -- the Make.com integration isn't built yet.** The plan
(full history of how this got decided is in pipeline-plan.md's "Getting
bytes into Storage from the cloud"): POST the rendered image (multipart,
straight from disk) to a Make.com webhook; Make base64-encodes it
server-side and calls the `upload-asset` Edge Function itself, which
returns `{ok, bytes_written, public_url}` the same as always. Two things
still need confirming before this is real, not assumed: whether the
cloud sandbox's shell can even reach Make's webhook ingestion domain, and
Make's flat 5MB webhook payload cap against this pipeline's 8MB render
ceiling.

This repo used to double as the image relay -- rendered images got
pushed to `drafts/`, with a dedicated SSH deploy key and a macOS
`launchd` job keeping it unattended. That's been torn down on purpose,
not left half-working, now that Make.com does the same job without any
of that side infrastructure. If Stage 8 comes up in a run before the
Make.com integration is finished, **stop and report rather than
improvising a git-based upload path** -- that door is deliberately
closed, not just currently broken.

**Never use `pipeline/publish.py upload-sql`** (the base64-inlined variant)
for a real post -- it's kept only for tiny test fixtures, for the same
reason (an LLM retyping a whole image as base64) that made a relay
necessary in the first place.

Once every image for this post is confirmed uploaded (however Stage 8
ends up confirming that):

```bash
python3 pipeline/publish.py insert-sql \
  --format <format> --archetype <archetype> \
  [--feature <feature>] [--topic <topic slug>] [--layout <layout>] \
  --content content.json \
  --asset-urls <public_url_1> [<public_url_2> ...] \
  --notes "<Stage 3 / Stage 7 flags, or omit>"
```

Run the printed `sql` via `execute_sql` once. That's the draft queued as
`status='pending'` for Armaan's dashboard review — nothing posts to
Instagram itself yet (Zapier automation is a separate, later build).

### Stage 9 — Report

Per post: made / flagged / failed, with reasons. Stdout is fine for now —
the dashboard is the real review surface, this is just for debugging a run
that didn't go as expected.
