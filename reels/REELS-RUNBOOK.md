# Reels RUNBOOK — one scheduled cloud run

This is the complete brief for a scheduled cloud session that produces Memora's Instagram Reels. Read it in full, then read
`reels/APP-MAP.md` and `reels/KIT.md`, before doing anything.

**You are the planner.** Each reel is planned by you, at run time: what to show, in what order, what the voice says, how the edit
looks. `reels/plan.sh` does the mechanical work (recording the real demo app, voice, checking, rendering) and refuses anything
outside the rules. There are no templates: two reels of the same type should not look like the same reel with the words swapped.

Creative freedom stops at facts and safety. Every claim must be true of the product and visible in the reel. If something goes
wrong that this runbook doesn't cover, stop and report. Posting nothing is better than posting something wrong.

## What a run produces
**N reels** (default **3**; the scheduled prompt may set another number and mix), delivered as MP4s in this session's chat for
Armaan to review. Nothing goes to the outreach dashboard, Supabase storage or Instagram.

## Reel types
Each has requirements; everything else is yours to decide. Vary format, pacing, scene design, hook and angle between reels and
between runs.

| Type (`feature`) | Must show | Start URL |
|---|---|---|
| `agent` | Memora Agent turning one prompt into a whole structured course (outline → build → reading it). The standout, "only on Memora" feature. A reel may focus on the build or on one lesson. | `/agent` |
| `quiz` | Generating a quiz from a prompt and taking part of it (answering, explanations). | `/quizzes` |
| `flashcards` | Generating a deck from a prompt and studying it. | `/flashcards` |
| `autopilot` | Memora Autopilot: exams in, a daily plan out. Pick your own angle each time: the exam board and readiness, a study session, what "secure" means, study-time controls… Plan it fresh; never reuse a previous run's sequence. | `/autopilot` or `/dashboard` |
| `overview` | The landing page and the dashboard. Example flow (not mandatory): scroll the lander to its final panel while interacting with its elements (week chart, flip card) and explaining each section, click "Go to Dashboard", explore, end on one feature worth a closer look. Vary which sections get airtime and what you end on. | `/` or `/dashboard` |
| `adaptive` | An adaptive deck (or quiz) run: fast-forward through answering — the voice speaks as the student doing it ("let me just fast-forward through these…") — then the results screen, then the rebuild showing how the deck adapts (retired / reworded / new). | `/autopilot`, `/flashcards/decks`, `/quizzes` or `/dashboard` |

Topics: `agent`, `quiz` and `flashcards` reels take their topic from `topics.json` (below) and bring matching `content/`.
`autopilot`, `overview` and `adaptive` show seeded content (Forces and Motion, Photosynthesis); their voice talks about what's on screen.

## Voices
ElevenLabs, model `eleven_v4`, from the roster in `reels/config.json`. One voice per reel, rotating: reel *i* (in slug order)
gets roster entry `(day_of_year + i) mod 4`. Write lines that suit the voice: Justin Case is calm and explanatory; Belle B and
Lucan Rock are excited; Lyan is somewhere between.

## Content rules (non-negotiable)
Audience is 13–18. Sharp peer talking to another student, not SaaS copy. No user or scale counts, no manufactured urgency or
streak guilt, no claims that aren't visible in the reel or true of the product, no curriculum names inside generated content.
Memora is in beta: confident, never implying more scale or polish than exists. Each reel ends on the-memora.com.

## Retrying temporary failures
- **Your two Supabase calls** (stage 0 `get_project`, stage 2 Vault `select`): on a *connection* problem (timeout, "connection
  terminated", reset/refused, "fetch failed", 5xx), `sleep 60` and retry, then `sleep 180` and retry once more. Any other error
  stops the run: permission errors, refusals, a paused project, fewer than three secrets.
- **Inside `plan.sh`**: clone, installs, demo reset, recordings, TTS and renders retry themselves a bounded number of times;
  `prepare` restarts itself once after 15 minutes if it fails before recording. Bad credentials are never retried.
- **Your repairs** (stage 7) are bounded: at most **3** fix attempts per reel. Then drop it.

## Stages

### 0. Check the Supabase project is awake
Supabase MCP `get_project` for `dtyiuknezuzqohdxicbg` (memora-outreach). If not `ACTIVE_HEALTHY`, stop and report
"memora-outreach is paused — restore it in the Supabase dashboard, then re-run." Never restore it yourself.

### 1. Get the code
```bash
git clone --depth 1 https://github.com/Armaan-Mahajan/memora-outreach-bot.git ~/ob
```
memora-web is private: `plan.sh prepare` clones it with the read-only token. Never clone it yourself or try other credentials.

### 2. Secrets
```sql
select name, decrypted_secret from vault.decrypted_secrets where name in ('demo_password', 'elevenlabs_api_key', 'memora_web_read_token');
```
Write `~/.reels-secrets.env` (`DEMO_PASSWORD=…`, `ELEVENLABS_API_KEY=…`, `MEMORA_WEB_TOKEN=…`) with the file-writing tool, then
`chmod 600`. **Never** print, echo, log or repeat these values anywhere. Delete the file at the end of the run (stage 9) or on failure.

### 3. Plan the reels
1. Decide the N reels and their types (the scheduled prompt's mix, else 3 with at least two different types).
2. For topic-led reels pick topics from `topics.json` → `topics`: alternate `level` `upper` / `younger` (`both` fits either), skip
   `archetype: technique`, prefer subjects not used by the other reels tonight.
3. Write each plan in `~/reels-run/plans/<slug>/` following KIT.md. Read the working scripts in `reels/capture/reels/*.json` and
   APP-MAP.md before writing any `capture.json`; use only selectors APP-MAP.md lists or a working script uses.
4. For content you wrote (`content/*.json`, voice lines, on-screen copy), get a fact-check: spawn one subagent per run with the
   plans' text and ask it to flag anything factually wrong for the stated level. Fix what it flags.
5. `bash ~/ob/reels/plan.sh validate <slug>` for each. Fix until every plan passes.

### 4. Record (background)
```bash
cd ~ && (set -a; . ~/.reels-secrets.env; set +a; WORK=~/reels-run nohup bash ~/ob/reels/plan.sh prepare > ~/reels-console.log 2>&1 &)
```
Then every 8 minutes: `sleep 480; cat ~/reels-run/status.json`. It builds the app (≈10 min), then per reel: content → reset →
record → voice. Recording runs roughly 8–10× slower than the clip. `"state": "done"` → stage 5. `"failed"` → stage 8.
No change for 40 minutes → treat as failed ("stalled at <stage>").

### 5. Check each reel
For each slug that wasn't dropped (`ls ~/reels-run/dropped-*.txt` lists dropped ones with reasons):
`bash ~/ob/reels/plan.sh check <slug>`. It fits the voice to the real recording, type-checks, and renders stills to
`~/reels-run/check/<slug>/`. On failure read `error.txt`.

### 6. Look
Read `check/<slug>/sheet.jpg` (and individual `seg-*.jpg` where needed). Flag: an error page, login screen, blank or white window,
404, a stuck spinner, wrong content, text outside the safe area or overlapping, captions missing where the voice speaks, a scene
that says something the footage doesn't show.

### 7. Repair (≤ 3 attempts per reel)
| Problem | Fix, then |
|---|---|
| Reel code / scene design / timeline / voice timing | edit `Reel.tsx` / `plan.json` → `check` |
| Voice script or voice changed | edit `plan.json` → `plan.sh voice <slug>` → `check` |
| The recording is wrong (wrong page, missed step) | edit `capture.json` (+ `content/`) → `plan.sh record <slug>` (needs the secrets env, run it in the background like stage 4) → `check` |
After 3 failed attempts, drop the reel: write the reason to `~/reels-run/dropped-<slug>.txt`.

### 8. Finish
`bash ~/ob/reels/plan.sh finish` (renders every checked reel, loudness, verify; ≈5 min per reel — run it in the background like
stage 4 if more than 3 reels). Then read each `~/reels-run/out/<slug>-sheet.jpg` once more and `out/summary.json`.

### 9. Deliver
`rm -f ~/.reels-secrets.env`. Send all finished MP4s with `SendUserFile` in one call (`status: proactive`, `display: render`).
Report: one line per reel — type, topic, voice, length, OK or FLAGGED (what you saw); dropped reels with reasons; total run time;
the `hardware` line from summary.json; every retry (yours + summary.json `retries`, with `run_attempt` if 2), or "no retries".

**Fallback.** If `prepare` fails outright (stage 4 → failed after its own restart), the fixed four-reel pipeline is the backup:
`WORK=~/reels-fixed nohup bash ~/ob/reels/run.sh` started like stage 4 (with the secrets env), waited on the same way, its MP4s
delivered from `~/reels-fixed/out/`. Say clearly in the report that the planned run failed and why. Use the fallback once, never
more.

## Hard limits
- Never edit, commit or push any repository. Your files live only in `~/reels-run/` (plans, checks).
- Database: only stage 0's `get_project` and stage 2's single Vault `select`. No other SQL, ever.
- Vault: read only `demo_password`, `elevenlabs_api_key`, `memora_web_read_token`. Never print secrets.
- No posting anywhere: not Instagram, the outreach dashboard, or Supabase storage.
- Shell: `git clone` of outreach-bot; `bash ~/ob/reels/plan.sh <phase> …` (and `run.sh` only as the fallback); `sleep`, `cat`,
  `tail`, `ls`, `mkdir`; `chmod 600` / `rm -f` on the secrets file. No curl, wget, package installs, or running the pipeline's
  inner scripts directly. Write plan files with the file tools.
- The recording drives only the local demo app (`validate_capture.py` enforces it). Never point anything at the live site.
