# Outreach generation pipeline — plan

The piece that turns two template systems into a working loop. Everything
else exists: templates that render, a dashboard that displays, a database
that stores. Nothing connects them, and no draft has ever gone from nothing
to sitting in the queue without a human driving each step. This is that
connection.

Scope: single-image cards and slideshows only. Reels run on a separate
local pipeline later, for screen-recording reasons, and feed the same queue.

---

## 1. Where it runs

**A Cowork scheduled task, running entirely in the cloud container — no
device binding, and NOT the same shape as `memora-growth`** (an earlier
version of this doc claimed it was; that was wrong, corrected 2026-09-04).

This isn't assumed, it's checked. Every render this session ran through the
plain cloud shell — Playwright and headless Chromium are pre-installed
there, no setup needed — and every rendered image got inspected through the
plain cloud filesystem. None of it touched Armaan's actual machine. Reading
`memora-growth`'s own RUNBOOK confirms why THAT automation needs a device
and this one doesn't: its job ends with files that have to live permanently
in Armaan's local `Data Analysis` folder (xlsx/csv/pdf archives) — a
deliberate choice about where the deliverable lives, not a limit on where
the computation can happen. Notably, even that local shell has **zero
general network access** (git, curl, and pip all fail there); everything
network-related in both automations — Supabase, Gmail — goes through
Claude's own MCP connections, not the shell. Outreach's deliverable is a
Supabase row plus storage objects, with no local-residency requirement, so
there's no reason to pay for a device binding it doesn't need — the cloud
container is strictly more capable here, not less (real outbound network,
where the local Mac shell has none at all).

**The one real gap this raises: an ephemeral cloud session starts empty.**
`memora-growth` gets away with a bare local shell because its Mac disk
keeps a persistent checkout between monthly runs. A cloud scheduled task
gets a fresh container every firing — no repo, no templates, no
`topics.json` sitting around from last time. The pipeline's code needs to
live somewhere the run can fetch at its start. **Action item before the
first scheduled run: push `outreach-bot/` (pipeline scripts, templates,
assets, `topics.json`) to a git repo**, and have the run's first step
`git clone` it. The cloud container has real package-registry-grade network
access, confirmed, so this is a normal clone, not a blocker — just a setup
step that doesn't exist yet (`outreach-bot/` is currently loose files on
Armaan's Mac, not a repo).

The split that matters: anything that can be *measured* is deterministic
Python; anything that needs *judgement* is Claude.

| Deterministic (Python) | Judgement (Claude) |
| --- | --- |
| Pick the next assignment from rotation | Write the copy |
| Render, and assert on the output | Verify factual claims (fresh subagent — see Stage 3) |
| Upload to storage (via MCP, not the shell — see Stage 8), insert the row | Look at the render and say if it's right |
| Hash/similarity duplicate checks | Decide how to fix what's wrong |

The alternative — a standalone script calling an LLM API — buys determinism
and a lower per-run cost, but it means hand-building the vision loop,
managing another API key, and reimplementing what Cowork already provides.
Not worth it for v1. If per-run cost becomes the binding constraint later,
the deterministic half is already factored out and portable, so switching is
a contained change rather than a rewrite.

**One run = one batch, one scheduled task firing, start to finish** —
including verification (Stage 3), which now happens as a subagent call
inside this same run rather than a separate one. Each post in the batch is
independent: a failure on post 2 must not take down posts 1 and 3.

---

## 2. The stages

### Stage 0 — Load inputs
- `topics.json` — the curated allowlist (see §4).
- Recent history from `outreach_drafts`: last ~20 rows, all statuses.
- `claude-knowledge/brand-voice.md` and `outreach-bot-brief.md` for voice.
- The format's template + render script.

### Stage 1 — Plan the batch (deterministic)
Decide what to make: format, archetype, and then either `feature`
(single-image cards) or `topic` (slideshows). Rotation rules, in code:
- don't repeat the same `feature` back-to-back
- don't repeat a `topic` that appears anywhere in history
- spread across `archetype` so the account isn't all micro-lessons

**Single-image cards also get a `layout` assignment.** Seven hand-built
layouts exist (`post-templates/single-image-card/layouts/`) — one is still
Agent-specific (`flow-outline`), the rest are generic or tied to a
different feature (Flashcards → `flashcard-mockup`, Mora → `chat-mockup`).
Assignment logic: if `feature` has a natural layout, prefer it; otherwise
pick from the generic layouts (`stat-hero`, `quote-callout`, `comparison`,
`checklist`), rotating so the same one doesn't repeat back-to-back. This is
the resolution to the template-variety-vs-reliability tension: variety
comes from a deterministic choice among pre-verified layouts, not from
giving the content-writing step freedom to invent one — see that
directory's README for the full reasoning. New layouts get added to this
rotation the same way new topics get added to the allowlist: hand-built and
verified once, then available forever after.

Output: a small assignment object per post, now including `layout` for
single-image posts. **This is duplicate-avoidance layer 1, and it's the
cheapest and most reliable one** — a topic that never gets assigned can
never be written twice.

### Stage 2 — Write the content (Claude)
Given the assignment, the voice docs, the format's JSON schema, and the last
~10–15 headlines and captions used for that feature/topic, write the content
JSON. The recent-copy context is duplicate-avoidance layer 2 — it catches
paraphrased repeats that no string match would.

Output: `content.json` matching the shape in the format's
`content-example.json`.

### Stage 3 — Verify the claims (Claude, subagent — revised 2026-09-04)
Every factual claim gets checked by a **fresh subagent call that did not
write it** — not a separate Cowork scheduled task. Spinning up a whole
second scheduled run per verification is impractical, as Armaan flagged;
but the fix isn't folding verification into the authoring context, because
that reintroduces exactly the bias problem this stage exists to solve — the
same context asked "is this right?" reliably agrees with itself. A subagent
sidesteps this without the infra cost: it's a tool call inside the SAME
scheduled-task run (still "one run = one batch," per §1), it has zero
memory of Stage 2's authoring, and it returns a verdict rather than a whole
second session's worth of state. Bonus this unlocks over the original
design: a subagent can use web search to check a claim against a real
source, not just re-read the same context more skeptically.

Framing matters: hand it the deck without "this is our content" context, ask
it to find what's wrong, and require it to say what it actually checked
rather than returning a bare verdict.

Output: `{ ok, confidence, flags[] }`. Anything below confident goes into
`notes` on the draft so it arrives at review already marked.

This stage is why micro-lessons are viable at all. The brief says approval
should be a stamp, not an edit pass — and the topics worth posting about
span curricula nobody on this project personally sits, so "the human will
catch it" is not a real safety net.

**Confirmed 2026-09-04, not just assumed:** the phone capability test ran a
fresh subagent inside a real cloud scheduled-task session with a planted
false claim ("the French Revolution began in 1785") hidden among true ones
and no test-framing given to the subagent — it correctly flagged only the
planted error and validated the true claims. Subagent tool access inside a
scheduled-task session works the same way it does interactively.

### Stage 4 — Render (deterministic)
`render_slideshow.py` or `render.py`. Already asserts and raises on:
- KaTeX errors
- visible text colliding with the logo or progress bar
- file size over Instagram's 8 MB limit

Add: assert dimensions are exactly 1080×1350 and format is JPEG, since
that's the constraint that already bit once.

### Stage 5 — Look at it (Claude vision)
**Required, both formats.** The generator writes into templates it cannot
see, so the only way to catch what the assertions miss is to look:
- orphaned words and awkward line breaks
- visual balance, cramped or empty slides
- does the cover actually earn a swipe
- does the deck read as a coherent sequence

Cost note: check the **contact sheet first** — one image, all slides, catches
most layout problems — and only pull individual slides at full size when
something looks off or for the cover. The contact-sheet generator already
exists from the slideshow build.

Output: pass, or a specific list of fixes.

### Stage 6 — Repair loop
If stage 4 or 5 failed, edit the content JSON and re-run 4–5. **Cap at 3
attempts.** On exhaustion, stop and report — do not ship, do not keep
looping. Same discipline as `memora-growth`: posting nothing beats posting
something broken.

### Stage 7 — Duplicate backstop (deterministic)
Normalized headline hash against history — catches the dumb failure where
the same content gets submitted twice. Optionally a similarity check on the
caption. **Flags, never auto-blocks**: a false positive that silently kills
a good post is worse than one that arrives with a note on it.

### Stage 8 — Publish to the queue
- Upload JPEGs to the `outreach-assets` bucket on a fixed path convention:
  `<format>/<slug>/01.jpg`. **Not a direct upload from the run's shell** —
  see "Getting bytes into Storage from the cloud" below, confirmed
  2026-09-04.
- Insert one `outreach_drafts` row: format, feature, topic, archetype,
  headline, subhead, caption, hashtags, content_json, asset_urls (ordered),
  notes, `status='pending'`. **Constraints confirmed on the real table**
  (via the phone capability test, 2026-09-04): `format` and `feature` are
  `NOT NULL`, and `format` has a `CHECK` restricting it to exactly
  `single_image` / `slideshow` / `reel` — the insert must supply both and
  use one of those three literal values, not e.g. `single-image`.

#### Getting bytes into Storage from the cloud (confirmed 2026-09-04)

The cloud scheduled task's shell has **no direct route to Supabase
Storage** — its egress proxy blocks raw HTTPS to `*.supabase.co` (the
phone capability test hit this directly: a plain upload attempt failed).
Storage's real backend (the actual file bytes, as opposed to the
`storage.objects` metadata row) only accepts genuine binary HTTP bodies
via its REST/TUS/S3 API — there's no SQL-only path to it, and `pg_net`
(Postgres's async-HTTP extension) can't reach it directly either, since
`pg_net` **only supports JSON-bodied POST** (no PUT/PATCH, no raw binary).

The workaround, verified end-to-end rather than assumed: a small Supabase
**Edge Function** (`upload-asset`, source in `upload-asset-edge-fn.ts`,
deployed on `memora-outreach`) that accepts `{bucket, path, contentType,
data_base64}` as JSON, decodes the base64 server-side, and writes it to
Storage using the service-role client. `pg_net` **can** invoke an Edge
Function with a JSON body (a documented pattern), and the whole call is
triggered via `execute_sql` — which is proxied *outside* the sandbox's
restricted egress (already proven working for ordinary Supabase reads/
writes). So the only network hop that touches `*.supabase.co` directly
happens on Supabase's own infrastructure (pg_net → Edge Function → Storage),
never through the run's own blocked shell.

Live-tested on 2026-09-04: a real `net.http_post` call through
`execute_sql` invoked `upload-asset` with a small PNG payload, got back
`{"ok":true,"bytes_written":68,"public_url":"..."}`, and the object was
independently confirmed to exist in `storage.objects` with the right size
and mimetype. Mechanism confirmed working; not yet load-tested at a real
JPEG's size (100–400 KB base64), though nothing in pg_net's documented
limits (JSON-POST-only, ~200 req/sec, 6h response retention) suggests a
body-size ceiling that would matter at that scale.

**Fallback if this ever proves fragile in production:** host rendered
assets in the same git repo the pipeline already clones from (§1) and
reference their raw GitHub URLs as `asset_urls` instead of Supabase
Storage. GitHub connectivity is independently confirmed reachable from
the cloud shell. Not needed given the above works, but cheap to keep in
mind.

**Open item, needs Armaan's call, not made unilaterally:** whether to keep
`pg_net` + the `upload-asset` Edge Function as permanent project
infrastructure now that it's proven, or tear it down and revisit at build
time; and whether to delete the test object left at
`outreach-assets/test/capability-check-pgnet-tiny.png`.

### Stage 9 — Report
Log per post: made / flagged / failed, with reasons. The dashboard is the
real surface; the log is for debugging a bad run.

---

## 3. Data model changes

Four columns on `outreach_drafts`, all cheap and all needed by the above:

```sql
alter table outreach_drafts add column topic text;      -- slideshow rotation axis
alter table outreach_drafts add column archetype text;  -- micro-lesson | technique | agent-output | feature-highlight
alter table outreach_drafts add column layout text;     -- single-image layout used (flow-outline | stat-hero | ...), null for slideshows
alter table outreach_drafts add column notes text;      -- verification flags, duplicate warnings, repair-loop history
```

`topic` as a real column rather than a `content_json` path: rotation queries
run on every batch, and that's the hot path — JSON extraction is worse
ergonomics for the query we run most.

**Dashboard follow-up:** `notes` is useless if the review UI doesn't show
it. A flagged draft whose flag is invisible is worse than an unflagged one,
because it looks vetted. Small addition to `DraftCard`.

Also: the existing seeded Agent draft still points at the old PNG asset —
re-seed it with the JPEG when this lands.

---

## 4. The topic allowlist

`outreach-bot/topics.json`. Each entry: subject, topic, a slug matching the
`topic` column, and which curricula it's safe for.

Selection rules baked into the file, not the prompt:
- stable, well-established material only
- nothing where curricula meaningfully disagree (a real hazard across
  IB / AP / GCSE / HSC — "the right answer" can be board-specific)
- nothing that needs a diagram to teach, since diagrams are out

**The bot may propose additions; a human approves them.** Letting the
generator expand its own accuracy guardrail defeats the point of having one.

---

## 5. Layout

```
outreach-bot/
  pipeline/
    run.py            # orchestrator entry point; --format, --count, --dry-run
    assign.py         # stage 1: rotation and allowlist filtering
    history.py        # reads outreach_drafts, shapes recent-copy context
    publish.py        # stage 8: storage upload + row insert
    checks.py         # stage 7: hash + similarity
  topics.json
  single-image-card/  # existing — 7 layouts under layouts/, see its README
  slideshow/          # existing
  RUNBOOK.md          # what the scheduled task actually executes
```

This whole tree needs to live in a git repo the scheduled task clones at
the start of every run — see §1's action item. Unlike `memora-growth`'s
RUNBOOK (which opens by telling the fresh session where its already-checked-
out disk is), this one has to open with the clone step itself, since
nothing persists between firings.

`run.py --dry-run` renders and checks but never writes to Supabase — that's
the loop to iterate against while building.

---

## 6. Build order

0. **Push `outreach-bot/` to a git repo.** Everything downstream assumes the
   scheduled task can clone it — do this before step 1, not after, so step 1
   is tested the way it'll actually run.
1. **One draft, end to end, no cleverness.** Hardcode the assignment, write
   the content by hand, render, upload, insert, watch it appear in Pending —
   from the plain cloud shell, confirming no device is needed for any of it.
   Proves the plumbing.
2. **Claude writes the content** (stage 2) against a hardcoded assignment.
3. **The self-correction loop** (stages 4–6), including the vision check.
4. **Rotation and duplicate-avoidance** (stages 1, 7) — needs history to
   exist first, which is why it comes after a few drafts have been made.
5. **Verification pass** (stage 3) as a subagent call — confirm the subagent
   tool is actually reachable from this run before building the rest of the
   stage around it.
6. **Wrap it in a scheduled task**, with `requires_local_device` unset —
   confirm the whole thread still works once it's a scheduled firing rather
   than an interactive session, not just assumed from steps 1-5.

One working thread through the whole thing before any stage gets deep.
Steps 0–3 are the session; 4–6 can follow.

---

## 7. Open decisions

- **Batch size and cadence** — parked deliberately. Doesn't block any of the
  above; `run.py --count N` takes it as an argument.
- **Where the run log goes** — stdout only for now, or a table? Stdout is
  fine until a run fails while nobody's watching.
- **Whether the vision check (Stage 5) gets its own model call or rides in
  the orchestrator's context** — probably the latter for v1, since Claude is
  already the orchestrator and has the images to hand. Unlike Stage 3, there's
  no agreement-bias risk here (judging "does this look good" isn't the kind
  of claim the orchestrator would be motivated to rubber-stamp), so this one
  doesn't need the subagent treatment.
- **Where the pipeline repo lives** — a new dedicated repo, or a folder
  inside an existing one? Needs deciding before build-order step 0, since
  that step's only job is pushing it somewhere clonable.
- **Keep or tear down the `pg_net` + `upload-asset` Edge Function test
  infra** — proven working 2026-09-04 (see Stage 8), but stood up as a
  capability test, not committed to as production infrastructure yet.
  Also: whether to delete the test object left in `outreach-assets`
  (`test/capability-check-pgnet-tiny.png`).
