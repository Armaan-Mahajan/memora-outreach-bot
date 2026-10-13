# Reels RUNBOOK — the daily reels routine

This is the complete brief for the daily Claude Code routine (claude.ai/code/routines) that produces Memora's Instagram Reels. Read it in full, then read
`reels/APP-MAP.md` and `reels/KIT.md`, before doing anything.

**You are the planner.** Each reel is planned by you, at run time: what to show, in what order, what the voice says, how the edit
looks. `reels/plan.sh` does the mechanical work (recording the real demo app, voice, checking, rendering) and refuses anything
outside the rules. There are no templates: two reels of the same type should not look like the same reel with the words swapped.

Creative freedom stops at facts and safety. Every claim must be true of the product and visible in the reel. If something goes
wrong that this runbook doesn't cover, stop and report. Posting nothing is better than posting something wrong.

## What a run produces
**3 reels** (unless the routine's prompt says otherwise), delivered as `<ISO date>-reel 1.mp4` …
`<ISO date>-reel 3.mp4` (date in IST) in this session's chat for Armaan to review (stage 9). Nothing goes to the outreach dashboard, Supabase storage or
Instagram: Armaan posts reels himself. Later in the same session he says which reels are approved, and you write their
captions (see "After review").

## Which reels today — and never repeating a posted one
Every reel sent for review is recorded in the `outreach_reels` table (memora-outreach Supabase) with its type, topic, hook and
voiceover, and Armaan's verdict (approved = posted, or rejected). Today's reels come from that history, not from guesswork:
- **`reels/plan/history.py assign`** picks today's 3 types (the ones sent least recently, so all six come round every two
  days) and, for agent / quiz / flashcards reels, the topic: never one posted in the last 90 days (as a reel or as a single-image
  or slideshow post), never one sent for review in the last 14 days, least recently used first, levels alternating, no two
  reels on the same subject. **Use its assignment as given** — it's the cheapest, most reliable layer against repeats.
- Its `recent_by_type` lists the last reels of each of today's types (hook, format, topic, verdict). Read them before planning:
  today's reel must take a **different angle**, not reword an old one. This matters most for autopilot / overview / adaptive
  reels, which show the same demo screens every time.
- **`plan.sh validate`** then refuses a plan whose hook matches an earlier reel's, or whose voiceover shares most of its words
  with an earlier reel of the same type (posted reels count for a year, unposted ones for 30 days), or that doesn't match the
  assignment (type, topic slug, reel number).
- **Slugs** start with the assigned reel number: `r1-…`, `r2-…`, `r3-…` (that's also the delivered file's number).

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
| `adaptive` | An adaptive deck (or quiz) run: fast-forward through answering — **at most 4 s on screen** (record it with `speed: fast` x 10-12 and give its footage segment `"max": 4`), with a `RunProgress` bar at the top counting the answers, and only one short voice line over it, the student speaking ("let me just fast-forward through these"). Then the results screen, then the rebuild showing how the deck adapts (retired / reworded / new). | `/autopilot`, `/flashcards/decks`, `/quizzes` or `/dashboard` |

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

### 1. Find the code
The routine attaches three repositories, each already cloned on its default branch: `memora-outreach-bot` (this pipeline),
`memora-web` (the app; `plan.sh` switches it to the `demo-recording-mode-v2` branch itself) and `memora-reels` (private, the
fallback delivery place if this session can't send files into the chat). Find their folders and give them fixed names:
```bash
for d in "$PWD" "$PWD"/.. ~ /home/*; do for r in "$d"/*/; do u=$(git -C "$r" remote get-url origin 2>/dev/null) || continue
  case "$u" in *memora-outreach-bot*) ln -sfn "${r%/}" ~/ob;; *memora-web*) ln -sfn "${r%/}" ~/mw;; *memora-reels*) ln -sfn "${r%/}" ~/reels-out;; esac; done; done
ls -l ~/ob ~/mw ~/reels-out
```
If `memora-outreach-bot` or `memora-web` is missing, stop and report which (the routine's repository list needs fixing);
`memora-reels` is only needed for stage 9's fallback. Never clone anything yourself.

### 2. Secrets
```sql
select name, decrypted_secret from vault.decrypted_secrets where name in ('demo_password', 'elevenlabs_api_key');
```
Write `~/.reels-secrets.env` (`DEMO_PASSWORD=…`, `ELEVENLABS_API_KEY=…`) with the file-writing tool, then `chmod 600`.
(memora-web needs no token: the routine's GitHub access covers the attached repository.) **Never** print, echo, log or repeat these values anywhere. Delete the file at the end of the run (stage 9) or on failure.

### 3. Plan the reels
1. Get today's assignment (`mkdir -p ~/reels-run/history` first). Run these two queries with the Supabase connector (`execute_sql` on `dtyiuknezuzqohdxicbg`) and save
   each result, as the plain JSON array of rows, with the file-writing tool:
   ```sql
   select run_date, reel_no, slug, reel_type, topic, topic_subject, topic_level, hook, format_summary, vo_text, status, caption, created_at
   from outreach_reels order by created_at desc limit 400;
   ```
   → `~/reels-run/history/reels.json`
   ```sql
   select topic, headline, caption, created_at from outreach_drafts where created_at > now() - interval '120 days' order by created_at desc;
   ```
   → `~/reels-run/history/drafts.json`. Then:
   ```bash
   python3 ~/ob/reels/plan/history.py assign --reels ~/reels-run/history/reels.json --drafts ~/reels-run/history/drafts.json \
     --topics ~/ob/topics.json --date $(TZ=Asia/Kolkata date +%F) > ~/reels-run/assignment.json
   ```
   It prints today's reels. If it reports a PROBLEM (no eligible topic left), stop and report it.
2. Read `recent_by_type` in `assignment.json`. Within the assigned type and topic, the angle, structure and look are yours:
   plan it fresh, different from those reels and from any example. Set `plan.topic.slug` to the assigned topic's slug.
3. Write each plan in `~/reels-run/plans/<slug>/` following KIT.md. Read the working scripts in `reels/capture/reels/*.json` and
   APP-MAP.md before writing any `capture.json`; use only selectors APP-MAP.md lists or a working script uses.
4. For content you wrote (`content/*.json`, voice lines, on-screen copy), get a fact-check: spawn one subagent per run with the
   plans' text and ask it to flag anything factually wrong for the stated level. Fix what it flags.
5. `bash ~/ob/reels/plan.sh validate <slug>` for each (it includes the no-repeat check against `assignment.json`). Fix until
   every plan passes; a repeat means a new angle, not a light rewording.

### 4. Record (background)
```bash
cd ~ && (set -a; . ~/.reels-secrets.env; set +a; MEMORA_WEB=$(readlink -f ~/mw) WORK=~/reels-run setsid nohup bash ~/ob/reels/plan.sh prepare > ~/reels-console.log 2>&1 < /dev/null &)
```
Then every 8 minutes: `sleep 480; cat ~/reels-run/status.json` (only `prepare` / `record` / `finish` write it; a `"failed"` there is real). It builds the app (≈10 min), then per reel: content → reset →
record → voice. Recording runs roughly 10–13× slower than the clip. `"state": "done"` → stage 5. `"failed"` → stage 8.
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
| The recording is wrong (wrong page, missed step), or `check` says RECORDING UNREADABLE | edit `capture.json` (+ `content/`) → `plan.sh record <slug>` (needs the secrets env, run it in the background like stage 4) → `check` |
After 3 failed attempts, drop the reel: write the reason to `~/reels-run/dropped-<slug>.txt`.

### 8. Finish
`bash ~/ob/reels/plan.sh finish` (renders every checked reel, loudness, verify; ≈5 min per reel — run it in the background like
stage 4 if more than 3 reels). Then read each `~/reels-run/out/<slug>-sheet.jpg` once more and `out/summary.json`.

### 9. Deliver
`rm -f ~/.reels-secrets.env`. `finish` copies every passing reel to `~/reels-run/out/deliver/` as `<ISO date>-reel <n>.mp4`.
Put them **in this chat**, where Armaan reviews them:
1. Look for a tool that sends files to the user (`SendUserFile`; if your tool list only names it as deferred, load it with
   ToolSearch first). It only sends files from folders the chat can open (`~` is `/root`, which it can't): first copy the three
   files, names unchanged, into your scratchpad directory (the one your system prompt names), then send those copies in **one**
   call (`status: proactive`, `display: render`). They appear in this session's chat and on Armaan's phone. That's the delivery;
   skip step 2.
2. Only if no such tool exists in this session: push them to the private `memora-reels` repository instead and put the branch link
   (`https://github.com/Armaan-Mahajan/memora-reels/tree/claude/reels-<date>/<date>`) at the top of your report:
   ```bash
   D=$(TZ=Asia/Kolkata date +%F); cd ~/reels-out && git checkout -b "claude/reels-$D" && mkdir -p "$D" && cp ~/reels-run/out/deliver/*.mp4 "$D"/ \
     && git add "$D" && git commit -m "Reels for $D" && git push -u origin "claude/reels-$D"
   ```
Then record what you sent (this is what keeps tomorrow from repeating today):
```bash
python3 ~/ob/reels/plan/reel_sql.py sent ~/reels-run/plans ~/reels-run/out/summary.json > ~/reels-run/history/sent.sql
```
Run that SQL exactly as printed with `execute_sql` (never hand-write it). It returns one row per reel with status `sent`.
Report: one line per reel — `reel <n>`: type, topic, voice, length, OK or FLAGGED (what you saw); dropped reels with reasons;
total run time; the `hardware` line from summary.json; every retry (yours + summary.json `retries`, with `run_attempt` if 2), or
"no retries". End with: "Tell me which reels are approved and I'll write their captions."

**No fallback reels.** If `prepare` fails outright, report the failure and stop. (`run.sh`, the old fixed pipeline, would only
re-send the same four reels every day, so it is not a daily fallback.)

## After review: captions
Armaan replies in this session with the approved reels (e.g. "1 and 3"). For each approved reel, write its Instagram caption
in the **same style as the single-image posts** — read the caption rules in the repo's root `RUNBOOK.md` (the hashtag rule under
"Hard rules" and the caption paragraph under the content stage), `claude-knowledge/brand-voice.md`, and the real examples'
`caption` / `hashtags` in `post-templates/single-image-card/layouts/*/content-*.json`:
- 2-4 short paragraphs; a sharp peer talking to another student, not marketing copy; a couple of emoji where a real study
  account would use them; end with "Link in bio."
- Exactly 5 hashtags: 4 tied to the reel's content and audience (a mix: one subject-specific, one study-culture, one broader)
  plus `#memora`.
- About what this reel actually shows (its plan.json, voiceover and on-screen copy) — never a feature, number or claim the reel
  doesn't support. Same content rules as the reels: no user counts, no urgency, minor-safe.
Before replying, check each caption against earlier ones: write it to `~/reels-run/history/caption-<n>.txt` and run
`python3 ~/ob/reels/plan/history.py check-caption ~/reels-run/history/caption-<n>.txt ~/reels-run/assignment.json`. If it's
flagged, rewrite it until it isn't (a different opening line and angle, not synonyms).
Reply with one block per approved reel, headed with its file name, the caption ready to paste and the hashtags on the last line.
Then record the verdict: write `~/reels-run/history/verdict.json` —
`{"approved": [{"reel_no": 1, "caption": "…", "hashtags": ["#…", "#…", "#…", "#…", "#memora"]}], "rejected": [2, 3]}` (every reel
sent today is either approved or rejected) — run `python3 ~/ob/reels/plan/reel_sql.py verdict <date> ~/reels-run/history/verdict.json`
and run its SQL with `execute_sql`. If Armaan later changes a caption or his mind, write the new verdict and run it again.
(If the session was restored after being idle and `~/reels-run` is gone, redo stage 1's lookup, re-run stage 3's two queries and
`assign` with today's date to rebuild `assignment.json`, and write the files again.)
If the reels went out by branch (stage 9 step 2), also commit the same blocks as `<date>/captions.md` on that branch and push
it (if the session was restored after being idle and `~/reels-out` is gone, redo stage 1's lookup and
`git checkout claude/reels-<date>` first).
Nothing gets posted: Armaan uploads the reels and captions himself; the only thing stored is the `outreach_reels` record. If he asks for changes, revise and reply again.

## Hard limits
- Never edit, commit or push `memora-outreach-bot` or `memora-web` (`plan.sh` changes memora-web's working copy for recording;
  that's expected and never committed). The only push allowed is stage 9's fallback `claude/reels-<date>` branch of `memora-reels`
  (and its `captions.md`), and only when no file-sending tool exists. Your own files live in `~/reels-run/`.
- Database: only stage 0's `get_project`, stage 2's single Vault `select`, stage 3's two history `select`s, and the SQL that
  `reel_sql.py` prints (stage 9's insert, the verdict's updates). No other SQL, ever: no DDL, no DELETE, nothing on any other table.
- Vault: read only `demo_password` and `elevenlabs_api_key`. Never print secrets.
- No posting anywhere: not Instagram, the outreach dashboard (`outreach_drafts` is read-only to you), or Supabase storage.
- Shell: stage 1's lookup and links; `bash ~/ob/reels/plan.sh <phase> …`; `python3 ~/ob/reels/plan/history.py …` and
  `python3 ~/ob/reels/plan/reel_sql.py …`; stage 9's git commands in `~/reels-out`; `sleep`,
  `cat`, `tail`, `ls`, `mkdir`, `readlink`; `chmod 600` / `rm -f` on the secrets file. No curl, wget, package installs, or
  running the pipeline's inner scripts directly. Write plan files with the file tools.
- The recording drives only the local demo app (`validate_capture.py` enforces it). Never point anything at the live site.
