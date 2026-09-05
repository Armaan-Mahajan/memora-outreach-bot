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
failed raw upload attempt) — every Supabase read, write, and file upload
in this run goes through `execute_sql` (an MCP tool call), never through
`curl`/`requests`/a raw HTTP client in the shell.

**First step of every run, before anything else:**

```bash
git clone https://x-access-token:$GITHUB_PUSH_TOKEN@github.com/Armaan-Mahajan/memora-outreach-bot.git outreach-bot && cd outreach-bot
```

The repo is `Armaan-Mahajan/memora-outreach-bot`, **private**. `$GITHUB_PUSH_TOKEN`
is the fine-grained PAT (Contents: Read and write, scoped to just this repo)
this same run needs later for Stage 8's push too -- set once as an
environment value for the run, never hardcoded. A fresh container has
nothing on disk otherwise: no templates, no `topics.json`, no `pipeline/`
scripts.

**UNVERIFIED as of 2026-09-05, capability test pending:** whether a fresh
scheduled-task container can authenticate git operations against GitHub at
all. An interactive Cowork session hit a proxy that silently discards any
credential it's given and only allows repos already on a pre-authorized
list for that session, with no self-service way to add one -- confirmed by
direct testing, not assumed (see pipeline-plan.md §7). If a scheduled
task's container turns out to be gated the same way, this clone step (and
Stage 8's push) will fail no matter what token they're given, and the
git-relay upload mechanism needs a different plan for unattended runs. If
this clone fails with something like "access denied by the git proxy" or
"not in this session's authorized repository set": **stop and report it
exactly as-is. Do not try to work around it** (don't unset proxy
environment variables, don't try alternate hosts/URLs, don't retry with a
different auth scheme) -- that specific workaround was attempted once,
during interactive testing, and was blocked by the platform itself before
it could do anything. Treat a proxy-origin failure here as a hard stop for
the whole run, not a per-post failure.

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

**The image is pushed to GitHub first; uploading into Storage happens via a
tiny SQL call that references its URL, never the image bytes** — see
pipeline-plan.md's "Getting bytes into Storage from the cloud" for the full
reasoning, and its §7 for how this was proven end-to-end on 2026-09-05.
Two steps, per image, in slide order:

**8a. Commit and push the rendered image to `drafts/`:**

```bash
git add drafts/<format>/<slug>/<NN>.<ext>
git commit -m "Add <slug> draft"
git push
```

If this fails with a proxy/authorization error, stop the whole run and
report it (see the note on this in "First step of every run" above) —
don't fall back to any other upload path for this post.

**8b. Build and run the upload SQL:**

```bash
python3 pipeline/publish.py github-upload-sql \
  --supabase-url "https://dtyiuknezuzqohdxicbg.supabase.co" \
  --anon-key "$SUPABASE_ANON_KEY" \
  --repo Armaan-Mahajan/memora-outreach-bot \
  --format <format> --slug <slug> --index <1-based index> \
  --image <path to rendered jpg>
```

This prints `{"repo_path", "source_url", "public_url", "sql"}`. Run the
`sql` value via `execute_sql`, then check the result:

```sql
select status_code, content, error_msg from net._http_response where id = <request_id>;
```

**Confirm `status_code = 200` and `content` contains `"ok":true` for every
image before continuing.** Do not build the insert on an unconfirmed
upload — a non-200/non-ok response almost always means the push in 8a
hasn't landed yet, or the path doesn't match. `$SUPABASE_ANON_KEY` is the
legacy anon JWT the `upload-asset` Edge Function needs to authenticate the
invocation — get it via `mcp__Supabase__get_publishable_keys` if it's not
already in the environment; never hardcode it in a committed file.

**Never use `pipeline/publish.py upload-sql`** (the base64-inlined variant)
for a real post — it's kept only for tiny test fixtures and is exactly the
slow, expensive, silently-corruptible mechanism this whole design replaced.

Once every image for this post is confirmed uploaded:

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
