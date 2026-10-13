#!/usr/bin/env bash
# Memora planned Reels. The planner (the scheduled Claude session) writes one plan per reel under $WORK/plans/<slug>/ and
# calls these phases one at a time (REELS-RUNBOOK.md has the whole procedure):
#
#   bash reels/plan.sh validate <slug>   check a plan: content, recording script, voice, Remotion code (offline, seconds)
#   bash reels/plan.sh prepare           build the demo app, then per reel: install its content, reset the demo account, record, voice
#   bash reels/plan.sh record <slug>     re-record + re-voice one reel (after its capture.json or content changed)
#   bash reels/plan.sh voice <slug>      regenerate one reel's voiceover (after only its script or voice changed)
#   bash reels/plan.sh check <slug>      fit voice to the recording, type-check, render preview stills → $WORK/check/<slug>/
#   bash reels/plan.sh finish            render every reel whose check passed, loudness pass, verify → $WORK/out/
#
# A plan is: plan.json (type, topic, timeline, voiceover, camera beats), capture.json (recording script), optional
# content/*.json (what the app "generates"), Reel.tsx (+ any .tsx it imports): the reel's own Remotion code, built from the kit.
#
# Progress: $WORK/status.json and $WORK/run.log. Temporary failures (network, timeouts, rate limits, a crashed browser) get
# bounded retries, all recorded in $WORK/retries.txt and summary.json. A `prepare` failure before recording starts gets ONE
# whole-phase restart after RETRY_WAIT_RUN s (default 900). One reel failing to record or check is dropped (and reported);
# the others carry on. Bad credentials stop everything at once. It never improvises.
#
# Env: DEMO_PASSWORD, ELEVENLABS_API_KEY, MEMORA_WEB_TOKEN (prepare / record / voice) · WORK (default ~/reels-run)
#      MEMORA_WEB (reuse a clone) · RETRY_FAST (tests: 1 s pauses) · CAPTURE_TIMEOUT (default 1800 s per recording)
set -Eeuo pipefail

PHASE="${1:-}"; ARG="${2:-}"
case "$PHASE" in validate|voice|check|record) [ -n "$ARG" ] || { echo "usage: plan.sh $PHASE <slug>"; exit 2; };; prepare|finish) ;;
  *) echo "usage: plan.sh validate <slug> | prepare | record <slug> | voice <slug> | check <slug> | finish"; exit 2;; esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HOME/reels-run}"; PLANS="$WORK/plans"; RM="$HERE/remotion"
mkdir -p "$WORK/out" "$WORK/check" "$WORK/vo"
export RUN_ATTEMPT="${RUN_ATTEMPT:-1}"; RETRY_WAIT_RUN="${RETRY_WAIT_RUN:-900}"
LOG="$WORK/run.log"; export RETRY_LOG="$WORK/retries.txt"; touch "$LOG" "$RETRY_LOG"
if [ "$PHASE" = prepare ] && [ "$RUN_ATTEMPT" = 1 ]; then : > "$LOG"; : > "$RETRY_LOG"; rm -f "$WORK"/dropped-*.txt; fi
echo "### $(date -u +%H:%M:%S) plan.sh $PHASE $ARG (attempt $RUN_ATTEMPT)" >> "$LOG"
STAGE="$PHASE"; PIDS=(); PERMANENT=""
export HW="$(cat "$WORK/hardware.txt" 2>/dev/null || true)"
MW="${MEMORA_WEB:-$WORK/memora-web}"

# status.json belongs to the long phases (prepare / record / finish), the ones you poll; the quick ones (validate, voice,
# check) write status-<phase>.json so running them alongside a long phase never overwrites its status
case "$PHASE" in prepare|record|finish) STATUS_FILE="$WORK/status.json";; *) STATUS_FILE="$WORK/status-$PHASE.json";; esac
status() { python3 - "$STATUS_FILE" "$PHASE" "$STAGE" "$1" "${2:-}" <<'EOF'
import json, sys, time
p, phase, stage, state, msg = sys.argv[1:6]
json.dump({"phase": phase, "stage": stage, "state": state, "message": msg, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(p, "w"), indent=1)
EOF
}
stage() { STAGE="$1"; echo "=== [$(date -u +%H:%M:%S)] $1" | tee -a "$LOG"; status running "$1"; }
note() { echo "$1" >> "$RETRY_LOG"; echo "  retry: $1" | tee -a "$LOG"; }
pause() { sleep "$( [ -n "${RETRY_FAST:-}" ] && echo 1 || echo "$1")"; }
# kill each server's whole process tree: npx forks next, which forks next-server
killtree() { local c; for c in $(pgrep -P "$1" 2>/dev/null || true); do killtree "$c"; done; kill "$1" 2>/dev/null || true; }
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && killtree "$p"; done
  if [ "$PHASE" = prepare ] || [ "$PHASE" = record ]; then
    pkill -f "[n]ext start -p 3001" 2>/dev/null || true; pkill -f "[n]ext-server" 2>/dev/null || true; pkill -f "[n]ode vproxy.cjs" 2>/dev/null || true; fi; }
fail() {
  if [ "$PHASE" = prepare ]; then case "$STAGE" in memora-web|servers)
    if [ "$RUN_ATTEMPT" = 1 ] && [ -z "$PERMANENT" ]; then
      note "prepare: stage '$STAGE' failed ($1), restarting the phase in ${RETRY_WAIT_RUN}s (attempt 2 of 2)"
      status running "waiting ${RETRY_WAIT_RUN}s before retrying prepare ('$STAGE' failed: $1)"
      cleanup; trap - EXIT ERR; pause "$RETRY_WAIT_RUN"
      exec env RUN_ATTEMPT=2 MEMORA_WEB_TOKEN="${_MWT:-}" bash "$HERE/plan.sh" prepare
    fi;; esac; fi
  status failed "$1"; echo "FAILED at '$STAGE': $1" | tee -a "$LOG"; exit 1; }
# only the main shell reports: with errtrace a failing command inside $(…) would otherwise run this in the subshell and
# mark a healthy run "failed" (that was the stray "FAILED at … (line 48)" from pgrep finding no children)
trap '[ "$BASH_SUBSHELL" = 0 ] && { status failed "command failed (line $LINENO) — see run.log"; echo "FAILED at $STAGE (line $LINENO)" >> "$LOG"; }' ERR
trap cleanup EXIT
# retry <tries> <pause_s> <label> <command…>: temporary failures only. A command returning 2 means "not temporary": stop.
ATTEMPT=1
retry() { local n=$1 p=$2 label=$3 i rc; shift 3
  for ((i = 1; i <= n; i++)); do
    ATTEMPT=$i
    if "$@"; then [ "$i" -gt 1 ] && note "$label: succeeded on attempt $i of $n"; return 0; else rc=$?; fi
    [ "$rc" = 2 ] && { PERMANENT=1; return 1; }
    if [ "$i" -lt "$n" ]; then echo "  $label failed (attempt $i of $n), retrying in ${p}s" | tee -a "$LOG"; pause "$p"; fi
  done
  note "$label: failed after $n attempts"; return 1; }
AUTH_ERR='Authentication failed|could not read Username|returned error: 40[13]|Invalid login credentials|invalid_grant'
drop() { echo "$2" > "$WORK/dropped-$1.txt"; echo "  DROPPED $1: $2" | tee -a "$LOG"; note "reel $1 dropped: $2"; }

slugs() { for d in "$PLANS"/*/; do [ -f "$d/plan.json" ] && basename "$d"; done | sort; }
# numpy + Pillow (contact sheets, sound effects): install them for the python3 this script uses if the image lacks them
py_deps() { python3 -c "import numpy, PIL" 2>/dev/null && return 0
  echo "  installing numpy + Pillow for $(python3 --version 2>&1)" | tee -a "$LOG"
  python3 -m pip install -q --break-system-packages numpy Pillow >>"$LOG" 2>&1 || python3 -m pip install -q --user numpy Pillow >>"$LOG" 2>&1
  python3 -c "import numpy, PIL" 2>/dev/null; }
npm_ci() { (cd "$1" && npm ci --no-audit --no-fund >>"$LOG" 2>&1); }
CORES=$(nproc 2>/dev/null || echo 1); RENDER_CONC=$(( CORES >= 2 ? 2 : 1 ))
CHROME_SHELL=$(ls -d /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell 2>/dev/null | head -1 || true)

# ── validate <slug>: everything checkable before recording (offline, seconds) ───────────────────────────────────────
validate_plan() { local s=$1 d="$PLANS/$1"
  [ -f "$d/plan.json" ] || { echo "no plan at $d/plan.json"; return 1; }
  python3 "$HERE/plan/validate_plan.py" "$d" "$HERE/config.json" || return 1
  python3 "$HERE/plan/validate_content.py" "$d" || return 1
  python3 "$HERE/plan/validate_capture.py" "$d" || return 1
  python3 "$RM/tools/lint_reel.py" "$d" || return 1
  # today's assignment and the no-repeat check (REELS-RUNBOOK.md stage 3); skipped only when there is no assignment file
  if [ -f "$WORK/assignment.json" ]; then python3 "$HERE/plan/history.py" check-plan "$d" "$WORK/assignment.json" || return 1; fi; }
if [ "$PHASE" = validate ]; then
  stage "validate:$ARG"
  if out=$(validate_plan "$ARG" 2>&1); then echo "$out" | tee -a "$LOG"; status done "plan $ARG is valid"; exit 0
  else echo "$out" | tee -a "$LOG"; status failed "plan $ARG is invalid — see the output"; exit 1; fi
fi

# ── voice: ElevenLabs (eleven_v4) in the plan's roster voice ─────────────────────────────────────────────────────────
voice_one() { local s=$1
  python3 - "$PLANS/$s/plan.json" "$WORK/vo/$s.json" "$s" "$HERE/config.json" <<'EOF' || return 1
import json, sys
plan, out, slug, cfg = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], json.load(open(sys.argv[4]))
v = plan['vo']; roster = {x['name']: x for x in cfg['voices']}; voice = roster[v['voice']]
json.dump({'name': slug, 'voice_name': voice['name'], 'voice_id': voice['id'], 'models': [cfg.get('voice_model', 'eleven_v4')],
           'voice_settings': voice.get('settings', {'stability': 0.45, 'similarity_boost': 0.8, 'style': 0.35, 'use_speaker_boost': True}),
           'lines': [{'text': l['text']} for l in v['lines']]}, open(out, 'w'), indent=1)
EOF
  rm -rf "$HERE/voice/out/vo/$s"; (cd "$HERE/voice" && node tts.mjs "$WORK/vo/$s.json" >>"$LOG" 2>&1); }
if [ "$PHASE" = voice ]; then
  stage "voice:$ARG"; [ -n "${ELEVENLABS_API_KEY:-}" ] || fail "ELEVENLABS_API_KEY not set"
  voice_one "$ARG" || fail "ElevenLabs TTS failed for $ARG"
  rm -f "$WORK/check/$ARG/ok"; status done "voiceover regenerated for $ARG — run check again"; exit 0
fi

# ── check <slug>: resolve against the real recording, type-check, preview stills ────────────────────────────────────
remotion_ready() {
  [ -d "$RM/node_modules" ] || retry 3 20 "npm ci (remotion)" npm_ci "$RM" || return 1
  [ -f "$RM/public/audio/bed.wav" ] || (cd "$RM" && python3 tools/synth_audio.py >>"$LOG" 2>&1); }
register_ok() { local list=() x; for x in $(slugs); do [ -f "$RM/src/reels/$x/resolved.json" ] && list+=("$x"); done
  python3 "$RM/tools/register_reels.py" "${list[@]}" >>"$LOG"; }
if [ "$PHASE" = check ]; then
  py_deps || { echo "python3 numpy/Pillow missing and could not be installed" | tee -a "$LOG"; status failed "numpy/Pillow missing"; exit 1; }
  s="$ARG"; C="$WORK/check/$s"; rm -rf "$C"; mkdir -p "$C"; stage "check:$s"
  chk() { echo "$1" > "$C/error.txt"; echo "$1" | tee -a "$LOG"; status failed "check $s failed — see $C/error.txt"; exit 1; }
  [ -f "$HERE/capture/out/$s/clip.mp4" ] || chk "no recording for $s (record it: plan.sh record $s)"
  o=$(python3 "$HERE/capture/check_capture.py" "$HERE/capture/out/$s" 2>&1) || chk "RECORDING UNREADABLE OR WRONG — re-record it (plan.sh record $s):
$o"
  [ -f "$HERE/voice/out/vo/$s/manifest.json" ] || chk "no voiceover for $s (plan.sh voice $s)"
  o=$(validate_plan "$s" 2>&1) || chk "$o"
  o=$(cd "$RM" && python3 tools/resolve_plan.py "$PLANS/$s" "$HERE/capture/out/$s" "$HERE/voice/out/vo/$s" 2>&1) || chk "$o"
  echo "$o" | tee -a "$LOG" > "$C/timeline.txt"
  remotion_ready || chk "could not install Remotion"
  register_ok
  o=$(cd "$RM" && npx tsc -p . 2>&1) || chk "TYPE ERRORS:
$(echo "$o" | head -40)"
  o=$(cd "$RM" && timeout 900 node tools/stills.mjs "$s" "$C" "$CHROME_SHELL" 2>&1) || chk "PREVIEW RENDER FAILED:
$(echo "$o" | grep -vE '^\s+at ' | tail -25)"
  echo "$o" >> "$LOG"
  python3 - "$C" <<'EOF'
import glob, os, sys
from PIL import Image
d = sys.argv[1]; ims = sorted(glob.glob(os.path.join(d, 'seg-*.jpg')), key=os.path.getmtime)
th = [Image.open(p).resize((270, 480)) for p in ims]; cols = min(5, len(th)); rows = (len(th) + cols - 1) // cols
S = Image.new('RGB', (270 * cols, 480 * rows))
for i, im in enumerate(th): S.paste(im, ((i % cols) * 270, (i // cols) * 480))
S.save(os.path.join(d, 'sheet.jpg'), quality=85)
EOF
  touch "$C/ok"; status done "check $s passed — look at $C/sheet.jpg and seg-*.jpg before finishing"; echo "CHECK OK $s" | tee -a "$LOG"; exit 0
fi

# ── finish: render every checked reel, loudness, verify ──────────────────────────────────────────────────────────────
if [ "$PHASE" = finish ]; then
  py_deps || fail "python3 numpy/Pillow missing and could not be installed"
  stage finish-setup; remotion_ready || fail "could not install Remotion"
  OKS=(); for s in $(slugs); do
    if [ -f "$WORK/check/$s/ok" ]; then OKS+=("$s"); elif [ ! -f "$WORK/dropped-$s.txt" ]; then drop "$s" "its check never passed"; fi; done
  [ "${#OKS[@]}" -gt 0 ] || fail "no reel passed its check"
  register_ok
  render() { rm -f "$WORK/render-$1.mp4"; (cd "$RM" && npx remotion render src/index.ts "$1" "$WORK/render-$1.mp4" --concurrency="$RENDER_CONC" --log=error --crf=14 --x264-preset=slow \
      --browser-executable="$CHROME_SHELL" >>"$LOG" 2>&1) && [ -s "$WORK/render-$1.mp4" ]; }
  for s in "${OKS[@]}"; do
    stage "render:$s"
    if ! retry 2 15 "render $s" render "$s"; then drop "$s" "render failed"; continue; fi
    ffmpeg -y -loglevel error -i "$WORK/render-$s.mp4" -c:v copy -af loudnorm=I=-15:TP=-1.5:LRA=11 -ar 48000 -c:a aac -b:a 192k "$WORK/out/$s.mp4" \
      || { drop "$s" "loudness pass failed"; continue; }
    rm -f "$WORK/render-$s.mp4"
  done
  stage verify
  if ! python3 - "$PLANS" "$WORK" <<'EOF' | tee -a "$LOG"; then fail "output check failed — see summary.json"; fi
import glob, json, os, subprocess, sys
from PIL import Image
plans, work = sys.argv[1:3]
probe = lambda f, q: subprocess.run(["ffprobe", "-v", "error"] + q + ["-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip()
rows, dropped = [], {}
for d in sorted(glob.glob(os.path.join(plans, '*', 'plan.json'))):
    p = json.load(open(d)); s = p['slug']; f = os.path.join(work, 'out', f'{s}.mp4')
    dp = os.path.join(work, f'dropped-{s}.txt')
    if os.path.exists(dp): dropped[s] = open(dp).read().strip(); continue
    if not os.path.exists(f): dropped[s] = 'no output file'; continue
    dur = float(probe(f, ["-show_entries", "format=duration"]) or 0)
    wh = ",".join(x for x in probe(f, ["-select_streams", "v:0", "-show_entries", "stream=width,height"]).replace("\n", ",").split(",") if x.strip())
    aud = probe(f, ["-select_streams", "a:0", "-show_entries", "stream=codec_name"])
    lo, hi = p.get('seconds', [15, 60]); ok = lo - 0.5 <= dur <= hi + 0.5 and wh == "1080,1920" and aud == "aac"
    rows.append({"reel": s, "file": f"{s}.mp4", "type": p.get('feature'), "voice": p.get('vo', {}).get('voice'), "topic": (p.get('topic') or {}).get('topic'),
                 "format": p.get('format'), "seconds": round(dur, 1), "target": [lo, hi], "size": wh, "audio": aud, "ok": ok})
    print(f"  {'OK ' if ok else 'BAD'} {s}.mp4: {dur:.1f}s (target {lo}-{hi}), {wh}, audio={aud}")
    tmp = os.path.join(work, 'tmpsheet'); os.makedirs(tmp, exist_ok=True)
    for i in range(8): subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(dur * (i + 0.5) / 8), "-i", f, "-frames:v", "1", "-vf", "scale=270:-1", f"{tmp}/{i}.jpg"])
    ims = [Image.open(f"{tmp}/{i}.jpg") for i in range(8)]; W, H = ims[0].size; S = Image.new("RGB", (W * 4, H * 2))
    for i, im in enumerate(ims): S.paste(im, ((i % 4) * W, (i // 4) * H))
    S.save(os.path.join(work, 'out', f'{s}-sheet.jpg'), quality=85)
# the files Armaan gets: "<ISO date>-reel <n>.mp4", numbered in slug order (plan slugs r1-…, r2-…, r3-… set that order)
import shutil
date = os.environ.get("REEL_DATE") or subprocess.run(["date", "+%F"], capture_output=True, text=True, env={**os.environ, "TZ": "Asia/Kolkata"}).stdout.strip()
dl = os.path.join(work, 'out', 'deliver'); shutil.rmtree(dl, ignore_errors=True); os.makedirs(dl)
import re
for k, r in enumerate([r for r in rows if r['ok']], 1):
    m = re.match(r'r(\d+)-', r['reel']); k = int(m.group(1)) if m else k      # reel number = the plan's r<n>- (the assignment's)
    name = f"{date}-reel {k}.mp4"; shutil.copy(os.path.join(work, 'out', r['file']), os.path.join(dl, name)); r['delivered_as'] = name
    print(f"  → out/deliver/{name}  ({r['reel']})")
rl = os.environ.get("RETRY_LOG"); retries = [l.strip() for l in open(rl)] if rl and os.path.exists(rl) else []
json.dump({"date": date, "hardware": os.environ.get("HW", ""), "run_attempt": int(os.environ.get("RUN_ATTEMPT", "1")), "retries": retries,
           "reels": rows, "dropped": dropped}, open(os.path.join(work, 'out', 'summary.json'), 'w'), indent=1)
sys.exit(1 if any(not r['ok'] for r in rows) or not rows else 0)
EOF
  STAGE=done; status done "reels rendered: $WORK/out"; echo "DONE → $WORK/out" | tee -a "$LOG"; exit 0
fi

# ── prepare / record: the demo app, servers, then per reel: content → reset → record → check recording → voice ─────
servers_up() {
  retry 3 20 "npm ci (capture)" npm_ci "$HERE/capture" || fail "npm ci failed in capture/"
  cleanup; sleep 1      # nothing left over from an earlier attempt may still hold :3000 / :3001
  for port in 3000 3001; do curl -s -o /dev/null "http://localhost:$port" && fail "port $port is still in use by an earlier server"; done
  (cd "$MW" && exec npx next start -p 3001 >>"$WORK/next.log" 2>&1) & PIDS+=($!)
  (cd "$HERE/capture" && exec node vproxy.cjs >>"$WORK/vproxy.log" 2>&1) & PIDS+=($!)
  local ok=""; for _ in $(seq 1 60); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/auth/login || true)" = 200 ] && { ok=1; break; }; sleep 2; done
  [ -n "$ok" ] || fail "app did not come up on :3000 within 120 s"; }
seed() { local out; out=$(mktemp)
  (cd "$MW" && set -a && . ./.env.local && set +a && npm run seed:demo >"$out" 2>&1); local rc=$?
  cat "$out" >> "$LOG"; grep -qE "$AUTH_ERR" "$out" && rc=2; rm -f "$out"; return $rc; }
# the app's "generation" reads demo-content/*.json on every request: swap in this reel's content, then reset the account
install() { git -C "$MW" checkout --quiet -- demo-content && python3 "$HERE/plan/install_content.py" "$PLANS/$1" "$MW" >>"$LOG" && seed; }
capture() { [ "$ATTEMPT" -gt 1 ] && { install "$1" || return 1; }
  rm -rf "$HERE/capture/out/$1"
  (cd "$HERE/capture" && timeout "${CAPTURE_TIMEOUT:-1800}" node runner.mjs "$PLANS/$1/capture.json" >>"$LOG" 2>&1) && [ -s "$HERE/capture/out/$1/clip.mp4" ]; }
record_one() { local s=$1   # returns 1 (and drops the reel) on failure; stops the run only on bad credentials
  stage "content:$s"
  if ! retry 2 30 "content + reset ($s)" install "$s"; then
    [ -n "$PERMANENT" ] && fail "seed:demo login refused: is DEMO_PASSWORD (Vault demo_password) correct?"
    drop "$s" "could not install its content / reset the demo account"; return 1; fi
  stage "capture:$s"
  if ! retry 2 15 "recording $s" capture "$s"; then drop "$s" "recording failed (see run.log for the step that timed out)"; return 1; fi
  if ! python3 "$HERE/capture/check_capture.py" "$HERE/capture/out/$s" | tee -a "$LOG"; then drop "$s" "recording looks wrong (see run.log)"; return 1; fi
  stage "voice:$s"
  if ! voice_one "$s"; then drop "$s" "ElevenLabs TTS failed"; return 1; fi
  rm -f "$WORK/check/$s/ok" "$WORK/dropped-$s.txt"; return 0; }

if [ "$PHASE" = record ]; then
  [ -d "$MW/.next" ] || fail "no built demo app at $MW (run prepare first)"
  { [ -n "${DEMO_PASSWORD:-}" ] && [ -n "${ELEVENLABS_API_KEY:-}" ]; } || fail "DEMO_PASSWORD and ELEVENLABS_API_KEY must be set"
  o=$(validate_plan "$ARG" 2>&1) || { echo "$o" | tee -a "$LOG"; fail "plan $ARG is invalid — fix it first"; }
  stage servers; servers_up
  if ! record_one "$ARG"; then git -C "$MW" checkout --quiet -- demo-content; fail "could not record $ARG: $(cat "$WORK/dropped-$ARG.txt" 2>/dev/null)"; fi
  git -C "$MW" checkout --quiet -- demo-content
  STAGE=recorded; status done "re-recorded and voiced $ARG; next: plan.sh check $ARG"; echo "RECORDED $ARG" | tee -a "$LOG"; exit 0
fi

stage preflight
for c in node npm npx git ffmpeg ffprobe python3 curl; do command -v "$c" >/dev/null || fail "missing command: $c"; done
retry 2 10 "pip install numpy/Pillow" py_deps || fail "python3 numpy/Pillow missing and could not be installed"
[ -n "${DEMO_PASSWORD:-}" ] || fail "DEMO_PASSWORD not set"
[ -n "${ELEVENLABS_API_KEY:-}" ] || fail "ELEVENLABS_API_KEY not set"
[ -n "$CHROME_SHELL" ] || fail "no Chromium headless shell under /opt/pw-browsers"
CPU_MODEL=$(lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -1); MEM_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo 2>/dev/null)
export HW="${CORES} core(s), ${CPU_MODEL:-unknown CPU}, ${MEM_GB:-?} GB RAM"; echo "$HW" > "$WORK/hardware.txt"
echo "hardware: $HW → render concurrency $RENDER_CONC" | tee -a "$LOG"
SLUGS=$(slugs); [ -n "$SLUGS" ] || fail "no plans in $PLANS"
for s in $SLUGS; do o=$(validate_plan "$s" 2>&1) || { echo "$o" >> "$LOG"; drop "$s" "plan invalid: $(echo "$o" | grep -m1 -E '^\s+-' | sed 's/^ *- //')"; }; done
echo "reels: $SLUGS" | tee -a "$LOG"

stage memora-web
MW_REPO=$(python3 -c "import json; print(json.load(open('$HERE/config.json'))['memora_web']['repo'])")
BRANCH=$(python3 -c "import json; print(json.load(open('$HERE/config.json'))['memora_web']['branch'])")
if [ -n "${MEMORA_WEB_TOKEN:-}" ]; then        # auth for this stage's git calls only
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
         GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$MEMORA_WEB_TOKEN" | base64 | tr -d '\n')"
fi
mw_get() { local out; out=$(mktemp)
  if [ -d "$MW/.git" ]; then git -C "$MW" fetch --quiet origin "$BRANCH" >"$out" 2>&1 && git -C "$MW" checkout --quiet -B "$BRANCH" "origin/$BRANCH" >>"$out" 2>&1
  else case "$MW" in "$WORK"/*) rm -rf "$MW";; esac; git clone --quiet --depth 1 --branch "$BRANCH" "$MW_REPO" "$MW" >"$out" 2>&1; fi
  local rc=$?; cat "$out" >> "$LOG"; grep -qE "$AUTH_ERR" "$out" && rc=2; rm -f "$out"; return $rc; }
retry 3 20 "memora-web clone" mw_get \
  || fail "could not get memora-web ($BRANCH) — $( [ -n "$PERMANENT" ] && echo 'GitHub refused the token: is MEMORA_WEB_TOKEN set, unexpired, and scoped to memora-web (Contents: read)?' || echo 'network problem, see run.log')"
_MWT="${MEMORA_WEB_TOKEN:-}"     # kept unexported (no child process sees it) only for the one phase restart
unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0 MEMORA_WEB_TOKEN
echo "memora-web at $(git -C "$MW" rev-parse --short HEAD)" | tee -a "$LOG"
grep -q '"seed:demo"' "$MW/package.json" || fail "memora-web's package.json has no seed:demo script — the demo branch lost it (check package.json after merging prod)"
grep -q "process.env.DEMO_PASSWORD" "$MW/scripts/seed-demo-content.ts" || fail "memora-web's seed script still hard-codes the password"
python3 - "$MW/.env.local" "$HERE/config.json" <<'EOF'
import json, sys
env = json.load(open(sys.argv[2]))["public_env"]; open(sys.argv[1], "w").write("".join(f'{k}="{v}"\n' for k, v in env.items()))
EOF
retry 3 20 "npm ci (memora-web)" npm_ci "$MW" || fail "npm ci failed in memora-web"
(cd "$MW" && npx next build >>"$LOG" 2>&1) || fail "next build failed"

stage servers; servers_up
RECORDED=0
for s in $SLUGS; do
  [ -f "$WORK/dropped-$s.txt" ] && continue
  record_one "$s" && RECORDED=$((RECORDED + 1))
done
git -C "$MW" checkout --quiet -- demo-content
[ "$RECORDED" -gt 0 ] || fail "no reel could be recorded"
STAGE=prepared; status done "recorded and voiced $RECORDED reel(s); next: plan.sh check <slug> for each"
echo "PREPARED $RECORDED reel(s)" | tee -a "$LOG"
