# Reels RUNBOOK — one scheduled cloud run

This is the complete brief for a scheduled cloud session that produces Memora's Instagram Reels. Read it in full before doing anything.

The run is **deterministic**. `reels/run.sh` does all the work: it records the demo app, generates the voiceover, renders and checks the output. Your job is to start it, wait, look at what it made, and deliver it. You make no creative decisions in this run, and you never fix things by improvising. If something goes wrong, stop and report.

## What a run produces

These four reels, defined in `reels/config.json`, are delivered as MP4s in this session's chat for Armaan to review:

| Reel | File | Target length |
|---|---|---|
| Agent: course | `memora-reel-agent-course.mp4` | 30–45 s |
| Agent: lesson walkthrough | `memora-reel-agent-lesson.mp4` | 45–60 s |
| Quiz | `memora-reel-quiz.mp4` | 20–30 s |
| Flashcards | `memora-reel-flashcards.mp4` | 20–30 s |

Nothing goes to the outreach dashboard, to Supabase storage, or to Instagram. Armaan reviews the reels in chat and picks which ones move on.

## Stages

### 0. Check the Supabase project is awake
Use the Supabase MCP `get_project` for `dtyiuknezuzqohdxicbg` (memora-outreach). If its status is anything other than `ACTIVE_HEALTHY`, stop and report: "memora-outreach is paused — restore it in the Supabase dashboard, then re-run." Do **not** restore it yourself.

### 1. Get the code
```bash
git clone --depth 1 https://github.com/Armaan-Mahajan/memora-outreach-bot.git ~/ob
```
memora-web is private. If the session already has it at `/home/claude/memora-web`, reuse it with `MEMORA_WEB=/home/claude/memora-web`; `run.sh` fetches and switches it to `demo-recording-mode` itself. Otherwise leave `MEMORA_WEB` unset and `run.sh` clones it.

### 2. Secrets
Read both secrets with the Supabase MCP `execute_sql` on `dtyiuknezuzqohdxicbg`:
```sql
select name, decrypted_secret from vault.decrypted_secrets where name in ('demo_password', 'elevenlabs_api_key');
```
Write them to `~/.reels-secrets.env` as `DEMO_PASSWORD=…` and `ELEVENLABS_API_KEY=…`, one per line, using the file-writing tool. Then run `chmod 600 ~/.reels-secrets.env`.

**Never** print, echo, cat, log or repeat either value: not in a message, a command, a file inside a repo, or your final report. If the Vault read is refused or returns fewer than two rows, stop and report that. Do not look for the secrets anywhere else.

### 3. Start the run in the background
`run.sh` takes about 90 minutes, which is longer than a single shell call can wait. Start it detached, then delete the secrets file once the run has picked the secrets up:
```bash
cd ~ && (set -a; . ~/.reels-secrets.env; set +a; WORK=~/reels-run MEMORA_WEB=/home/claude/memora-web nohup bash ~/ob/reels/run.sh > ~/reels-console.log 2>&1 &)
sleep 20 && rm -f ~/.reels-secrets.env && cat ~/reels-run/status.json
```
Drop `MEMORA_WEB=…` if `/home/claude/memora-web` doesn't exist.

### 4. Wait
Every 8 minutes, run `sleep 480; cat ~/reels-run/status.json`. That's one check per shell call, and nothing else in between.
- `"state": "running"`: keep waiting. The stage names show progress: preflight → memora-web → servers → seed → capture:<reel> ×4 → voice:<reel> ×4 → assemble → render:<reel> ×4 → verify.
- `"state": "failed"`: go to stage 6.
- `"state": "done"`: go to stage 5.
- If the status hasn't changed for **40 minutes**, treat the run as failed with the message "stalled at <stage>".

Do not read `run.log` while the run is going well. It's long, and reading it wastes the run's budget.

### 5. Look, then deliver
1. Read each `~/reels-run/out/<reel>-sheet.jpg`. Each is a contact sheet of 8 frames from that reel. Flag a reel if any frame shows:
   - an error page, a login screen, or a blank or white app window
   - a 404, or a stuck loading spinner covering most of the window
   - text from the wrong reel
   - captions that are missing where a voice line should be playing

   This is a check, not a fix. Never re-render or re-record.
2. Read `~/reels-run/out/summary.json`. It holds each reel's length, size and audio check.
3. Send the four MP4s with `SendUserFile` in a single call, `status: proactive`, `display: render`.
4. Finish with a short report: one line per reel with its length and OK or FLAGGED (plus what you saw if flagged), and the total run time. Don't send the contact sheets unless a reel was flagged.

### 6. On failure
Report:
- the `stage` and `message` from `status.json`
- the last 30 lines of `~/reels-run/run.log` (`tail -n 30 ~/reels-run/run.log`)
- the last 15 lines of `~/reels-run/next.log` if the stage was `servers`, `seed` or `capture:*`

Send any reels that did finish rendering (`~/reels-run/out/*.mp4`), saying which ones are missing. **Do not re-run, patch scripts, or work around the failure.**

## Hard limits
- Never edit, commit or push any repository. The clones are read-only working copies.
- Database: the only SQL you run yourself is stage 0's `get_project` and stage 2's single Vault `select`. Nothing else, ever: no INSERT, UPDATE, DELETE or DDL. (`run.sh` resets the disposable demo account in memora-web's project through the app's own seed script; that's expected.)
- Vault: read only `demo_password` and `elevenlabs_api_key`.
- Never print secrets (see stage 2). Delete `~/.reels-secrets.env` as soon as `run.sh` has started.
- No posting anywhere: not Instagram, not the outreach dashboard, not Supabase storage.
- Shell commands are limited to:
  - `git clone` of the outreach-bot repo
  - `bash ~/ob/reels/run.sh`, started the way stage 3 shows
  - `sleep`, `cat`, `tail`, `ls`, and `chmod 600` on the secrets file
  - `rm -f ~/.reels-secrets.env`

  No curl, no wget, no package installs, no `python3 -c`, and no running the pipeline's scripts individually.
- If anything happens that this runbook doesn't cover, stop and report it. Posting nothing is better than posting something wrong.
