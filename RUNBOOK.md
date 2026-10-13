# Batch run

The brief for the daily **Claude Code routine** ("Memora outreach posts", claude.ai/code/routines) that makes Memora's single-image and slideshow posts and queues them as drafts for Armaan's review. Every run starts a **fresh cloud session with no memory of how any of this was built**, so this file is the whole story: read it in full before doing anything. (Reels are a separate routine with their own brief, `reels/REELS-RUNBOOK.md`; nothing here applies to them.)

## Where you are

A Claude Code cloud session on Anthropic's infrastructure, started by the routine's schedule. Nothing here touches Armaan's Mac. What you can reach, and how:

- **Repositories (already cloned on their default branches by the routine; never clone them yourself):**
  `memora-outreach-bot` (this pipeline: templates, `pipeline/`, `topics.json`, `claude-knowledge/`) and
  `memora-outreach-render-previews` (private; the render worker pushes a copy of every finished render there, which is how you see it in Stage 5). Find both and give them fixed names before anything else:
  ```bash
  for d in "$PWD" "$PWD"/.. ~ /home/*; do for r in "$d"/*/; do u=$(git -C "$r" remote get-url origin 2>/dev/null) || continue
    case "$u" in *memora-outreach-bot*) ln -sfn "${r%/}" ~/ob;; *memora-outreach-render-previews*) ln -sfn "${r%/}" ~/previews;; esac; done; done
  ls -l ~/ob ~/previews && cd ~/ob
  ```
  If `~/ob` is missing, stop and report "the routine's repository list is missing memora-outreach-bot". If only `~/previews` is missing, carry on and use Stage 5's fallback.
  Run every command below from `~/ob`. Your working files (`history_raw.json`, `content.json`, ...) live there as untracked files; nothing is ever committed.
- **Supabase: only through the Supabase connector** (`execute_sql`, `get_project`). Project `memora-outreach` (id `dtyiuknezuzqohdxicbg`), the isolated outreach project, never memora-web's (the connector can see both; never touch the other one). The session's shell has no route to `*.supabase.co` or the render worker's `*.workers.dev` URL, and doesn't need one.
- **GitHub: git only, through the session's GitHub proxy**, for the two attached repositories.

Rendering does not happen in this session: Stage 4 queues it to `memora-render-worker` (a Cloudflare Worker) through a database row and polls for the result.

**Before Stage 0, check the project is awake:** `get_project` for `dtyiuknezuzqohdxicbg`. Free projects pause after about a week idle. If its status isn't `ACTIVE_HEALTHY`, stop and report "memora-outreach is paused: restore it in the Supabase dashboard, then run the routine again." Never restore it yourself.

## Hard rules

- **Format must be exactly `single_image`, `slideshow`, or `reel`** on the `outreach_drafts` insert — an actual `CHECK` constraint on the real table, underscore not hyphen. `feature` is also `NOT NULL`; for slideshows without a natural feature tie-in, `pipeline/publish.py` defaults it to the sentinel `"general"` (see that script's comment) — don't leave it blank.
- **Never mention or imply a user count or scale number** in any post, in any form. Memora is pre-launch — content should read as authentic and early, never as an established brand.
- **No countdown/urgency elements, no fabricated testimonials or stats.** The audience skews to minors; see `claude-knowledge/outreach-bot-brief.md` for the full compliance rationale.
- **Slideshows only draw topics from `topics.json`.** Stage 2 does not get to invent a topic — the allowlist exists specifically to keep curriculum content out of territory where boards (IB/AP/GCSE/HSC/...) disagree.
- **Single-image cards only use the 9 layouts under `post-templates/single-image-card/layouts/`**, assigned by `pipeline/assign.py` — never let Stage 2 invent a new layout or bypass the rotation.
- **Posting nothing beats posting something wrong.** If a stage fails after the repair loop's 3 attempts, or something looks wrong that isn't covered below, stop and report rather than improvising or shipping anyway — same discipline as memora-growth.
- **A batch's failures are independent.** One post failing (render error, repair-loop exhaustion, verification failure) must not take down the rest of the batch. Mechanically: every subagent call in Stage 3 and Stage 8 is spun up fresh, per post, per stage — never one subagent handling more than one post's fact-check or verification in the same call. An error or bad tool call inside one post's subagent has no way to reach another post's, because they share no context at all. Run the posts in the batch one at a time in the orchestrator's own loop (not as parallel subagents) — Stage 1's duplicate-avoidance depends on each post seeing the ones already queued earlier in the same batch, which only works if they're assigned in order.
- **Content is about Memora's actual learning features, never about the platform's mechanics.** Every post has to be grounded in something a student actually does inside the product: Agent, Flashcards, Autopilot, Quizzes, adaptive decks/quizzes, or Mora (the `FEATURES` list in `pipeline/assign.py`), or a `topics.json` slideshow topic. Sign-up flow, the dashboard, billing/credits, account settings, curriculum-picker mechanics, or the tech stack are not post topics — those describe how the platform works, not what a student learns, and they read as SaaS marketing rather than the peer-to-peer voice `claude-knowledge/brand-voice.md` calls for.
- **Content is written for free-tier users, not as an upgrade pitch.** Don't reference credit amounts, monthly Agent-use caps, or any capability gated to Plus/Pro (see the pricing table in `claude-knowledge/memora-overview.md`) as if it's generally available, and don't frame a post around upgrading. Every feature mentioned is one a free-tier student can already use — write for the person on the free plan, not the one being sold a plan. Don't mention "limits" on the free tier at all, even neutrally or in passing — no "before you run out of credits," no "free plan has a cap," nothing that frames the free tier as restricted.
- **Exactly 5 hashtags per post, every time: 4 tied to the post's content/audience (a mix, not four of the same flavor -- e.g. one subject-specific, one study-culture, one broader-audience tag) plus exactly one literal `#memora`.** Never more, never fewer -- 5 is Instagram's own hard cap as of its December 2025 policy change, not just a style choice (Meta's own stated reasoning: a few specific tags outperform a long generic list; hashtags help search/discoverability, not algorithmic reach). Favor moderately specific, real-search-volume tags over hyper-niche invented ones -- specific enough that it's obvious what the post is about, common enough that people actually browse or search it (`#equilibrium` over an invented `#lechatelierprinciple`; `#apbio` over `#apbiologystudent2026`). `#memora` is non-negotiable on every post.

## Steps

Run once per post in the batch (`--count` from the invocation; batch size/cadence isn't fixed here — run whatever count and format split you were actually asked for).

### Stage 0 — Load inputs

- `topics.json` (the allowlist).
- Recent history, plus every slideshow topic ever used -- two queries:
  ```sql
  select id, format, feature, topic, archetype, layout, headline, caption, status, created_at
  from outreach_drafts
  order by created_at desc
  limit 20;
  ```
  ```sql
  select topic, max(created_at) as last_used
  from outreach_drafts
  where topic is not null
  group by topic;
  ```
  Save the first result as `history_raw.json` and the second as `topic_usage.json` (each as the plain JSON array of row objects), then:
  ```bash
  python3 pipeline/history.py history_raw.json --topic-usage topic_usage.json > history_shaped.json
  ```
  Don't skip the second query. The 20-row window only remembers the last handful of slideshows, so without `--topic-usage` Stage 1 starts re-picking topics after about eight decks no matter how long `topics.json` is. Re-run both queries and this reload before assigning each subsequent post in the batch, not just once at the start — otherwise post 2 can't see post 1's freshly-queued row and the duplicate-avoidance in Stage 1 loses its teeth partway through a multi-post batch.
- `claude-knowledge/brand-voice.md`, `claude-knowledge/memora-overview.md`, and `claude-knowledge/outreach-bot-brief.md` for voice and product facts.

### Stage 1 — Plan the batch (deterministic)

```bash
python3 pipeline/assign.py --format <single_image|slideshow> --topics topics.json --history history_shaped.json
```

Gives you the assignment object (feature+layout, or topic+archetype) for this post. Do not override this pick — it's the cheapest and most reliable duplicate-avoidance layer specifically because it's deterministic.

### Stage 2 — Write the content (you, Claude)

Before writing anything, use the Read tool to look at a rendered example of the assignment's actual layout/format — not just its JSON shape. For single-image cards, `post-templates/single-image-card/output/<layout>/` already has at least one full-size rendered JPEG example per layout (view any one of them if there's more than one). For slideshows, `post-templates/slideshow/output/lechatelier-principle-contact-sheet.png` shows a full worked deck. `content-example.json` only gives you the field shape to fill in — it doesn't show the actual space budget, visual weight, or composition of what you're writing into, and copy that fits the schema can still read cramped, padded, or tonally mismatched once rendered. This is a look, not a redesign: the layout itself stays fixed by Stage 1's assignment and the template's own CSS — the image is only there to calibrate how much you write and how it should land, never to invent new markup, add fields, or bypass the schema.

Given the assignment, the voice docs, `history_shaped.json`'s `recent_by_feature` (or the relevant slice for the topic), and what you just saw rendered, write `content.json` matching the target layout/format's `content-example.json` shape. Don't repeat the angle of anything in the last ~10-15 posts for that feature/topic.

**autopilot-plan** shows one plausible student week, not real data: 1-2 exams (`exams`), exactly 7 `week` days with minutes
(0 = a rest day; mark the exam days with `exam` + `exam_color` matching that exam's chip, and exactly one `today`), 2-3
`session_items` (kind `flashcards` or `quiz`, a real topic for those exams, a short count like "8 due" / "5 new"), and a
`readiness` line whose numbers add up (`secure + practised + not_started` = the total in its label). Keep the topics real and
level-appropriate (they're fact-checked like any subject claim), and don't write the week as if it were a real user's results.

**adaptive-rebuild** shows one rebuild: the `results` dots (`correct` of `total`, 6-12 items), one `rebuild_note` sentence in the
app's own plain voice, and at most **4 change cards in total** across `retired`, `reworded` and `added` (each 0-2; at least one
retired or added). Retired items are ones answered right every time; reworded ones keep the same meaning, said more clearly; new
ones target exactly what the note says was missed. Use "deck"/"cards" or "quiz"/"questions" consistently with `eyebrow` and
`material_label`. Never say rebuilding is free (it costs credits); the cards and questions are subject claims and get fact-checked.

**comparison** is two full-width bands stacked one above the other: `old_title` / `old_items` (the old way) on top, `new_title` / `new_items` (with Memora) below. 2-4 items per band, ideally the same number in both, each short enough to sit on one line (about 45 characters or fewer). Every `new_items` line is a product claim and gets checked against `memora-overview.md` like any other.

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

Required for every post, both formats. The rendered image only exists in Supabase Storage, which the session's shell can't reach, so `memora-render-worker` also pushes a copy of each render to the private `memora-outreach-render-previews` repository at `preview/<render_requests id>/<n>.jpg` (see that repo's `src/index.js`, `pushPreview`). The routine attaches that repository, so:

1. Once `render_requests.status` is `done`, update the clone:
   ```bash
   git -C ~/previews pull --ff-only --quiet
   ls ~/previews/preview/<render_requests id>/
   ```
   The worker pushes the preview just after it marks the row done; if the folder isn't there yet, `sleep 10` and pull again (up to 6 times).
2. `Read` each `~/previews/preview/<render_requests id>/<n>.jpg` in order (`1` for a single-image card, `1..slide_count` for a slideshow; walk every slide). Check for orphaned words, cramped or empty composition, text that collides or overflows, whether the cover earns a swipe (slideshows) and whether the deck reads as a coherent sequence. Output: pass, or a specific list of fixes.

**Fallback, only if `~/previews` is missing** (the repository isn't attached): read the token with
`select decrypted_secret from vault.decrypted_secrets where name = 'github_preview_token';` and fetch just this render's folder:
```bash
rm -rf ~/preview_fetch && mkdir ~/preview_fetch && cd ~/preview_fetch
AUTH=$(printf 'x-access-token:%s' '<token>' | base64 | tr -d '\n')
git -c http.extraHeader="Authorization: Basic ${AUTH}" clone --no-checkout --depth 1 --filter=blob:none \
    https://github.com/Armaan-Mahajan/memora-outreach-render-previews.git .
git sparse-checkout set --no-cone "preview/<render_requests id>"
git checkout
unset AUTH; cd ~/ob
```
Use **Basic** auth with the token as the password (a `Bearer` header gets a 401), never write the token into a file or git config, read the images from `~/preview_fetch/preview/<id>/`, then `rm -rf ~/preview_fetch`.

If the preview never arrives or can't be fetched, that's still a Stage 5 failure: don't queue a post you couldn't look at. The worker's preview push is best-effort, so report it and let Stage 6 or the stop-and-report path handle it.

### Stage 6 — Repair loop

If Stage 4 or 5 failed, edit `content.json` and re-run 4-5. **Cap at 3 attempts.** Each retry is a **new** `render_requests` row, not an update to the old one — the trigger only fires on `INSERT`, so there's no "re-render the same row" path, and it keeps the table's own history honest about how many attempts a post actually took. On exhaustion, stop and report this post as failed — do not ship a broken render, do not keep looping, and do not let it block the rest of the batch.

### Stage 7 — Duplicate backstop (deterministic)

```bash
python3 pipeline/checks.py content.json history_shaped.json [--layout <layout>]
```

Pass `--layout` for single_image posts (the same value Stage 4's `render_requests` row uses; omit for slideshows). `flow-outline`, `autopilot-plan` and `adaptive-rebuild` get a higher similarity bar (0.8 vs. the default 0.6) -- each only ever describes one feature, so its headline/subhead necessarily converge on similar phrasing post to post even when the outline_items are completely different. Every other layout keeps the default 0.6.

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

Run the printed `sql` via `execute_sql` once, then re-query the row back by its returned `id` to confirm it actually exists with `status = 'pending'` and the expected `asset_urls` — don't just trust the INSERT's own "returning id" as proof it landed. That's the draft queued as `status='pending'` for Armaan's dashboard review. Nothing posts to Instagram: there is no posting automation yet, so approving a draft in the dashboard only changes its status.

One fresh subagent per post here too, same reasoning as Stage 3.

### Stage 9 — Report

Your final message is the report Armaan reads, so make it scannable:

1. One line per post: `post <n>`: format, feature or topic, layout, headline, and **queued**, **queued with flags** (what Stage 3 / Stage 7 flagged) or **failed** (the stage and the reason). Then the batch total (e.g. "4 of 5 queued") and any repair attempts.
2. Then, if at least one draft was queued, how to review them, as **copyable commands in their own fenced `bash` blocks** (exactly these, so he can paste them into his Mac's terminal):

   Start the review dashboard:
   ```bash
   cd /Users/armaanmahajan/Documents/Projects/Memora/outreach-dashboard && npm run dev
   ```
   Then open it (in a second terminal tab, or paste the address into a browser):
   ```bash
   open http://localhost:3000
   ```
   Follow them with one line each: approve or reject each draft on the **Pending** tab; if port 3000 is already in use (for example by the demo app), Next.js picks the next free port and prints the address to open; stop the server with Ctrl+C when done. And say plainly: **approving doesn't post anything yet**, since there's no posting automation; it only marks the draft approved (rejected drafts are kept so their angles aren't reused).
3. If nothing was queued, skip the commands and say what stopped the batch.

Don't attach the report or the images as files: the drafts are in the dashboard.

## Hard limits

- **Database:** only the SQL this RUNBOOK names: the `get_project` check, Stage 0's two `select`s, Stage 4's insert (exactly as `publish.py render-request-sql` prints it) and its status poll, Stage 8's `storage.objects` size check and insert (exactly as `publish.py insert-sql` prints it) and its read-back, and Stage 5's fallback Vault read. Never hand-write an insert. No `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` or other DDL, no RLS or policy changes, nothing on any other table, nothing on any other Supabase project.
- **Vault:** read only `github_preview_token`, and only for Stage 5's fallback. Never print, echo or log a secret.
- **Repositories:** never edit, commit or push anything. Your only git commands are Stage 5's `pull` in `~/previews` (or its fallback clone in `~/preview_fetch`) and the lookup at the top of this file.
- **Shell:** the repository lookup and `ls`; `python3 pipeline/history.py|assign.py|checks.py|publish.py` with the arguments shown here (never `python3 -c` or any other script); `sleep`; `cd`, `mkdir`; `rm -rf` on `~/preview_fetch` only; and the fallback's `printf | base64 | tr` with `unset AUTH`. Write JSON files with the file tools. No `curl`, `wget`, `ssh`, `chmod`, `sudo` or package installs.
- **Subagents:** one fresh subagent per post per stage (Stages 3 and 8), never one subagent for two posts.
- **Failures:** one bad post fails alone and the batch carries on; a systemic failure (Supabase unreachable, every render failing, the worker not responding) stops the batch and gets reported.
- **Posting:** drafts only. Never post to Instagram or anywhere else, and never change a draft's status.
