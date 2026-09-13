# Batch run

The brief for the scheduled task. Every firing starts a **fresh, empty cloud container with no memory of how any of this was built**, so this file is the whole story — read it in full before doing anything. This file is meant to be self-contained -- everything needed to run a batch end to end is here.

## Where you are

**A Cowork scheduled task running entirely in the cloud container — no device binding, and nothing here touches Armaan's Mac.** This isn't assumed, it's been checked (confirmed 2026-09-04): Playwright/Chromium is pre-installed, real outbound network reaches npm/PyPI/GitHub, and the Supabase MCP connector works — **but is proxied outside this container's own restricted shell egress**, the same way memora-growth's MCP connectors are proxied outside ITS shell's zero-network local Mac environment. Concretely: **the plain shell cannot reach `*.supabase.co` directly** (confirmed by the capability test's own failed raw upload attempt, and reconfirmed 2026-09-05 against Make.com's webhook host too — this is a general outbound allowlist, not a Supabase-specific block) — every Supabase read, write, and file upload in this run goes through `execute_sql` (an MCP tool call), never through `curl`/`requests`/a raw HTTP client in the shell.

**First step of every run, before anything else:**

```bash
git clone <REPO_URL> outreach-bot && cd outreach-bot
```

`<REPO_URL>` — filled into the scheduled task's own prompt, not here, so this file doesn't go stale if the URL ever changes. A fresh container has nothing on disk otherwise: no templates, no `topics.json`, no `pipeline/` scripts.

Supabase project: `memora-outreach` (id `dtyiuknezuzqohdxicbg`, `https://dtyiuknezuzqohdxicbg.supabase.co`). This is the isolated dashboard project, not memora-web's — never point anything at memora-web's project.

Rendering itself does not happen in this container at all — it's queued to `memora-render-worker` (a separate Cloudflare Worker; see that repo's SETUP.md) and polled for. That Worker's own `*.workers.dev` URL is **also** unreachable directly from this container's shell, confirmed the same way as the `*.supabase.co` block above (2026-09-11) — so is `raw.githubusercontent.com` and `cdn.jsdelivr.net`, for what it's worth. `api.github.com` is the one arbitrary host that same proxy does let through, which is the only reason Stage 5 below is possible at all — see that stage for why.

## Hard rules

- **Format must be exactly `single_image`, `slideshow`, or `reel`** on the `outreach_drafts` insert — an actual `CHECK` constraint on the real table, underscore not hyphen. `feature` is also `NOT NULL`; for slideshows without a natural feature tie-in, `pipeline/publish.py` defaults it to the sentinel `"general"` (see that script's comment) — don't leave it blank.
- **Never mention or imply a user count or scale number** in any post, in any form. Memora is pre-launch — content should read as authentic and early, never as an established brand.
- **No countdown/urgency elements, no fabricated testimonials or stats.** The audience skews to minors; see `claude-knowledge/outreach-bot-brief.md` for the full compliance rationale.
- **Slideshows only draw topics from `topics.json`.** Stage 2 does not get to invent a topic — the allowlist exists specifically to keep curriculum content out of territory where boards (IB/AP/GCSE/HSC/...) disagree.
- **Single-image cards only use the 7 layouts under `post-templates/single-image-card/layouts/`**, assigned by `pipeline/assign.py` — never let Stage 2 invent a new layout or bypass the rotation.
- **Posting nothing beats posting something wrong.** If a stage fails after the repair loop's 3 attempts, or something looks wrong that isn't covered below, stop and report rather than improvising or shipping anyway — same discipline as memora-growth.
- **A batch's failures are independent.** One post failing (render error, repair-loop exhaustion, verification failure) must not take down the rest of the batch. Mechanically: every subagent call in Stage 3 and Stage 8 is spun up fresh, per post, per stage — never one subagent handling more than one post's fact-check or verification in the same call. An error or bad tool call inside one post's subagent has no way to reach another post's, because they share no context at all. Run the posts in the batch one at a time in the orchestrator's own loop (not as parallel subagents) — Stage 1's duplicate-avoidance depends on each post seeing the ones already queued earlier in the same batch, which only works if they're assigned in order.
- **Content is about Memora's actual learning features, never about the platform's mechanics.** Every post has to be grounded in something a student actually does inside the product: Agent, Flashcards, Quizzes, or Mora (the `FEATURES` list in `pipeline/assign.py`), or a `topics.json` slideshow topic. Sign-up flow, the dashboard, billing/credits, account settings, curriculum-picker mechanics, or the tech stack are not post topics — those describe how the platform works, not what a student learns, and they read as SaaS marketing rather than the peer-to-peer voice `claude-knowledge/brand-voice.md` calls for.
- **Content is written for free-tier users, not as an upgrade pitch.** Don't reference credit amounts, monthly Agent-use caps, or any capability gated to Plus/Pro (see the pricing table in `claude-knowledge/memora-overview.md`) as if it's generally available, and don't frame a post around upgrading. Every feature mentioned is one a free-tier student can already use — write for the person on the free plan, not the one being sold a plan. Don't mention "limits" on the free tier at all, even neutrally or in passing — no "before you run out of credits," no "free plan has a cap," nothing that frames the free tier as restricted.
- **Exactly 5 hashtags per post, every time: 4 tied to the post's content/audience (a mix, not four of the same flavor -- e.g. one subject-specific, one study-culture, one broader-audience tag) plus exactly one literal `#memora`.** Never more, never fewer -- 5 is Instagram's own hard cap as of its December 2025 policy change, not just a style choice (Meta's own stated reasoning: a few specific tags outperform a long generic list; hashtags help search/discoverability, not algorithmic reach). Favor moderately specific, real-search-volume tags over hyper-niche invented ones -- specific enough that it's obvious what the post is about, common enough that people actually browse or search it (`#equilibrium` over an invented `#lechatelierprinciple`; `#apbio` over `#apbiologystudent2026`). `#memora` is non-negotiable on every post.

## Steps

Run once per post in the batch (`--count` from the invocation; batch size/cadence isn't fixed here — run whatever count and format split you were actually asked for).

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
  Re-run this reload before assigning each subsequent post in the batch, not just once at the start — otherwise post 2 can't see post 1's freshly-queued row and the duplicate-avoidance in Stage 1 loses its teeth partway through a multi-post batch.
- `claude-knowledge/brand-voice.md`, `claude-knowledge/memora-overview.md`, and `claude-knowledge/outreach-bot-brief.md` for voice and product facts.

### Stage 1 — Plan the batch (deterministic)

```bash
python3 pipeline/assign.py --format <single_image|slideshow> --topics topics.json --history history_shaped.json
```

Gives you the assignment object (feature+layout, or topic+archetype) for this post. Do not override this pick — it's the cheapest and most reliable duplicate-avoidance layer specifically because it's deterministic.

### Stage 2 — Write the content (you, Claude)

Before writing anything, use the Read tool to look at a rendered example of the assignment's actual layout/format — not just its JSON shape. For single-image cards, `post-templates/single-image-card/output/<layout>/` already has at least one full-size rendered JPEG example per layout (view any one of them if there's more than one). For slideshows, `post-templates/slideshow/output/lechatelier-principle-contact-sheet.png` shows a full worked deck. `content-example.json` only gives you the field shape to fill in — it doesn't show the actual space budget, visual weight, or composition of what you're writing into, and copy that fits the schema can still read cramped, padded, or tonally mismatched once rendered. This is a look, not a redesign: the layout itself stays fixed by Stage 1's assignment and the template's own CSS — the image is only there to calibrate how much you write and how it should land, never to invent new markup, add fields, or bypass the schema.

Given the assignment, the voice docs, `history_shaped.json`'s `recent_by_feature` (or the relevant slice for the topic), and what you just saw rendered, write `content.json` matching the target layout/format's `content-example.json` shape. Don't repeat the angle of anything in the last ~10-15 posts for that feature/topic.

**stat-hero's `stat_unit` has a hard 3-line cap.** Unlike the headline, it has no auto-shrink at render time -- if it comes out past 3 lines the Worker throws and the render fails outright, not a style nit. Keep it well under 40 characters if you can; actual wrapping depends on word shapes as much as raw character count (a few short common words wrap far more forgivingly than one long compound one), so when in doubt, write it shorter than you think you need to.

**Slideshows' closing (`type: "closer"`) slide must be freshly written every time, tied to the specific topic just covered -- never reuse `content-example.json`'s closer text as-is.** Its `heading` and `text` should read like the last beat of *this* topic's story (a callback to what the deck just covered, a one-line takeaway, a reason it mattered) -- if the exact same words would fit unedited onto a completely different topic's deck, rewrite them. `cta` can stay a simple "Link in bio"; it's the `heading`/`text` that need to change post to post.

**Every post needs `caption` and `hashtags` written into `content.json`, regardless of layout or format.** `pipeline/publish.py` only pulls these from `content.json` -- it has no other source -- so skipping them means the draft queues with an empty caption and no tags while Stage 4/5 still report success, and there's no fixing it after the fact (no UPDATE allowed). Every layout's `content-example.json` now includes a real caption/hashtags example to work from. Captions also carry more weight now that hashtags are capped at 5 (see Hard rules) -- write them longer than a one-line teaser, 2-4 short paragraphs is normal, matching the length of those examples -- and use emoji naturally where an actual study-account caption would (a couple per caption is plenty, not one after every sentence).

### Stage 3 — Verify the claims (Sonnet subagent)

For anything with a factual claim (mainly slideshows, and `flow-outline`'s hardcoded-adjacent copy), spin up a **fresh Agent tool call on Sonnet** (`model: "sonnet"`) — zero memory of Stage 2 — and hand it the content without "this is our content" framing. Tell it explicitly, as part of that framing, to split the check into two different tracks:

- **Claims about Memora itself** (what a feature does, how it behaves) -- verify these only against `claude-knowledge/memora-overview.md`, `claude-knowledge/outreach-bot-brief.md`, and the `FEATURES` list in `pipeline/assign.py`. Don't web-search "Memora" for this -- the site is small and pre-launch, so a search either turns up nothing or surfaces an unrelated same-named result, neither of which is a real check. If a product claim isn't backed by those docs, flag it as unverifiable rather than trying to confirm it externally.
- **Claims about the subject matter itself** (the actual academic fact being taught or referenced) -- these should get a real web search plus reasoning, the same as any factual claim about the world. This is the harder and more valuable half of the check, and it already works well -- keep doing it properly.

Ask it to find what's wrong and say what it actually checked, not just return a bare verdict. This is a tool call inside this same run, not a separate scheduled task. Confirmed working 2026-09-04.

One fresh subagent per post — never reuse one across posts, and never hand a single subagent more than one post's content (see the batch-independence hard rule above).

Anything below confident goes into a `notes` string, carried through to Stage 8.

### Stage 4 — Render and upload (queued)

Rendering runs entirely inside `memora-render-worker` now, not in this container — insert one row per post and let its trigger hand the work off. Build the SQL the same way Stage 8 does, via `pipeline/publish.py` -- never hand-assemble this insert's jsonb literal yourself. A caption or headline with an apostrophe (`you're`, `isn't`) or a quote breaks a hand-written single-quoted string in exactly the way `sql_string()`/`sql_jsonb()` already handle correctly, and there's no reason to re-solve that problem inline for every post:

```bash
python3 pipeline/publish.py render-request-sql --kind <single_image|slideshow> --layout <layout, single_image only, else omit> --content content.json
```

Prints `{"sql": "insert into render_requests (...) returning id;"}`. Run that SQL via `execute_sql`.

The insert fires a Database trigger that calls the Worker over `pg_net`, async — Postgres doesn't wait for its HTTP response, so this row's own `status` column is the real source of truth, not the trigger firing. The Worker renders, uploads the finished JPEG(s) straight to Supabase Storage, and writes the result back onto this same row itself: `status`, `public_urls`, and `sizes` (each image's byte count, index-matched to `public_urls` — needed by Stage 8). This absorbs what used to be two separate stages — a local render, then a whole chunked-upload stage through a subagent — into one queued operation, because the Worker does both atomically and uploads with its own credentials.

Poll for completion:

```sql
select status, public_urls, sizes, error from render_requests where id = '<id>';
```

Loop with a short pause between checks (this container has no scheduler of its own) until `status` is `done` or `failed`. A freshly-redeployed Worker can take a few minutes for `pg_net` to establish its first connection to it — if the very first render of a run seems slow, that's DNS propagation on the Worker's side, not a broken poll. `status = 'failed'` means `error` explains what went wrong on the row — that's Stage 6's repair loop, not a run-ending failure.

### Stage 5 — Look at it (you, Claude, vision)

Required for every post, both formats — same requirement as always, just a different route to the actual pixels. The rendered image only exists in Supabase Storage now (there's no local file on this container's own disk to `Read`), and this container's egress proxy blocks `*.supabase.co` and `*.workers.dev` outright (confirmed 2026-09-11 — see "Where you are" above), so neither Storage's public URL nor the Worker itself is directly reachable from here. `memora-render-worker` also pushes a copy of each rendered image to a small private GitHub repo for exactly this reason (see that repo's `src/index.js`, `pushPreview`).

Fetch that copy over git, not the REST Contents API — `api.github.com`'s Contents/tarball endpoints are gated by a session-level repo allowlist this container can't satisfy (confirmed 2026-09-12: same 403 regardless of whether the target repo is public or private), but plain git-over-HTTPS against `github.com` is not. A partial, sparse clone keeps this fast and bounded even as the previews repo accumulates every image it's ever received:

1. Get the preview token — used only as a header value in step 2, never written into this run's own output or into any git config on disk:
   ```sql
   select decrypted_secret from vault.decrypted_secrets where name = 'github_preview_token';
   ```
2. Once per render (not once per image): fetch just this render's own folder, nothing else in the repo's history —
   ```bash
   rm -rf preview_fetch && mkdir preview_fetch && cd preview_fetch
   AUTH=$(printf 'x-access-token:%s' '<token from step 1>' | base64 | tr -d '\n')
   git -c http.extraHeader="Authorization: Basic ${AUTH}" \
       clone --no-checkout --depth 1 --filter=blob:none \
       https://github.com/Armaan-Mahajan/memora-outreach-render-previews.git .
   git sparse-checkout set --no-cone "preview/<render_requests id>"
   git checkout
   cd ..
   unset AUTH
   ```
   Use **Basic** auth, not Bearer -- GitHub's git-over-HTTPS smart protocol wants a PAT as an HTTP Basic password (username can be any non-empty string; `x-access-token` is the GitHub-documented convention). A raw `Authorization: Bearer <token>` header gets a 401 (confirmed 2026-09-12, first live run) -- go straight to Basic, don't rediscover this by trial and error each time. `-c http.extraHeader=...` is scoped to that one command -- it's never written into `.git/config`, and `unset AUTH` clears the encoded credential from the shell's environment once the clone finishes. `--filter=blob:none` plus the sparse-checkout means only this render's own images are ever downloaded, not the whole repo's accumulated history.
3. `Read` each `preview_fetch/preview/<render_requests id>/<n>.jpg` in order (`1` for a single-image card, `1..slide_count` for a slideshow). There's no single contact-sheet image to lean on anymore now that rendering happens in the Worker — for slideshows, walk every slide individually. Check for orphaned words, cramped/empty composition, whether the cover earns a swipe (slideshows), whether the deck reads as a coherent sequence. Output: pass, or a specific list of fixes.
4. `rm -rf preview_fetch` once you're done looking — don't let clones pile up across posts in the same run.

If the clone itself fails — an expired token, an auth error, or `pushPreview` silently not landing a copy (it's deliberately best-effort on the Worker's side, so a GitHub hiccup there never fails an otherwise-good render) — that's still a Stage 5 failure: don't ship a post you couldn't actually look at. Report it and let Stage 6 or the stop-and-report path handle it.

### Stage 6 — Repair loop

If Stage 4 or 5 failed, edit `content.json` and re-run 4-5. **Cap at 3 attempts.** Each retry is a **new** `render_requests` row, not an update to the old one — the trigger only fires on `INSERT`, so there's no "re-render the same row" path, and it keeps the table's own history honest about how many attempts a post actually took. On exhaustion, stop and report this post as failed — do not ship a broken render, do not keep looping, and do not let it block the rest of the batch.

### Stage 7 — Duplicate backstop (deterministic)

```bash
python3 pipeline/checks.py content.json history_shaped.json [--layout <layout>]
```

Pass `--layout` for single_image posts (the same value Stage 4's `render_requests` row uses; omit for slideshows). `flow-outline` gets a higher similarity bar (0.8 vs. the default 0.6) -- it only ever describes one feature (Agent), so its headline/subhead necessarily converge on similar phrasing post to post even when the outline_items are completely different. Every other layout keeps the default 0.6.

**Flags, never blocks.** If `flagged` is true, carry its `note` into Stage 8's `notes` column rather than discarding the post.

### Stage 8 — Verify, then queue the draft

The old chunked-upload path is gone, and so is the specific corruption risk it existed to catch — `memora-render-worker` uploads directly to Storage with its own credentials, no chunking, no relay. What's still worth a cheap check before trusting Stage 4's `status = 'done'`: spin up a **fresh Sonnet subagent** per post (a numbers comparison, not a judgment call — kept as its own subagent for the "don't trust your own report" independence Stage 3 already relies on), and for every image have it run:

```sql
select (metadata->>'size')::int as stored_bytes
from storage.objects
where bucket_id = 'outreach-assets' and name = '<path, derived from the matching public_url>';
```

Compare `stored_bytes` against the matching entry in that row's own `sizes` array (index-matched to `public_urls` — the Worker measured this itself right before uploading). **They must match exactly.** A mismatch means the object is truncated or corrupted even though the Worker's own upload call reported success — treat it as a failed upload for this post and do not continue to the insert below. This is the "posting nothing beats posting something wrong" rule, applied to the one failure mode that can slip past a successful-looking upload.

Once every image for this post is confirmed (this stage) and Stage 5 has already passed, have that same subagent run:

```bash
python3 pipeline/publish.py insert-sql \
  --format <format> --archetype <archetype> \
  [--feature <feature>] [--topic <topic slug>] [--layout <layout>] \
  --content content.json \
  --asset-urls <public_url_1 from render_requests.public_urls> [<public_url_2> ...] \
  --notes "<Stage 3 / Stage 7 flags, or omit>"
```

Run the printed `sql` via `execute_sql` once, then re-query the row back by its returned `id` to confirm it actually exists with `status = 'pending'` and the expected `asset_urls` — don't just trust the INSERT's own "returning id" as proof it landed. That's the draft queued as `status='pending'` for Armaan's dashboard review — nothing posts to Instagram itself yet (Make.com automation for posting is a separate, later build, unrelated to any of the above).

One fresh subagent per post here too, same reasoning as Stage 3.

### Stage 9 — Report

Per post: made / flagged / failed, with reasons. Stdout is fine for now — the dashboard is the real review surface, this is just for debugging a run that didn't go as expected.
