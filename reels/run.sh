#!/usr/bin/env bash
# Memora Reels pipeline — one unattended run, start to finish, no agent decisions inside.
#
#   DEMO_PASSWORD=… ELEVENLABS_API_KEY=… bash reels/run.sh
#
# Stages: preflight → memora-web (clone/build) → servers → seed → capture ×4 → voice ×4 → assemble → render ×4 → verify
# Output: $WORK/out/*.mp4 + $WORK/out/summary.json.  Progress: $WORK/status.json (stage, state, message) and $WORK/run.log.
# Temporary failures (network, timeouts, rate limits, a crashed browser) get a bounded number of retries, and every retry is
# recorded in $WORK/retries.txt and summary.json. A failure before recording starts (memora-web / servers / seed) also gets
# ONE whole-run restart after RETRY_WAIT_RUN seconds (default 900). Everything else (bad credentials, a voiceover that
# doesn't fit, a failed output check) stops the run at once and leaves status.json = {"state":"failed",…}. It never improvises.
#
# Optional env:
#   WORK        where everything is built (default ~/reels-run). Must be outside the outreach-bot clone.
#   MEMORA_WEB_TOKEN  read-only GitHub token for the private memora-web repo (scheduled runs: from the Vault).
#               Sent as a one-off HTTP Basic header via GIT_CONFIG_* env vars, never written to .git/config or disk.
#   MEMORA_WEB  path to an existing memora-web clone to reuse (it is fetched and switched to the demo branch).
#   ONLY        space-separated reel names to run a subset, e.g. ONLY="quiz-full".
#   RETRY_FAST  testing only: any value shortens every retry pause to 1 s.
#   CAPTURE_TIMEOUT  seconds one reel recording may take before it counts as stuck (default 1200).
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HOME/reels-run}"
mkdir -p "$WORK/out"
export RUN_ATTEMPT="${RUN_ATTEMPT:-1}"; RETRY_WAIT_RUN="${RETRY_WAIT_RUN:-900}"
LOG="$WORK/run.log"; export RETRY_LOG="$WORK/retries.txt"
if [ "$RUN_ATTEMPT" = 1 ]; then : > "$LOG"; : > "$RETRY_LOG"; else echo "=== whole-run attempt $RUN_ATTEMPT" >> "$LOG"; fi
STAGE="start"
PIDS=()
PERMANENT=""          # set when a failure is clearly not temporary (bad credentials): no retries, no restart

status() { python3 - "$WORK/status.json" "$STAGE" "$1" "${2:-}" <<'EOF'
import json, sys, time
p, stage, state, msg = sys.argv[1:5]
json.dump({"stage": stage, "state": state, "message": msg, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(p, "w"), indent=1)
EOF
}
stage() { STAGE="$1"; echo "=== [$(date -u +%H:%M:%S)] $1" | tee -a "$LOG"; status running "$1"; }
note() { echo "$1" >> "$RETRY_LOG"; echo "  retry: $1" | tee -a "$LOG"; }
pause() { sleep "$( [ -n "${RETRY_FAST:-}" ] && echo 1 || echo "$1")"; }
fail() {
  # one whole-run restart for a failure before recording starts, unless it's clearly not temporary
  case "$STAGE" in memora-web|servers|seed)
    if [ "$RUN_ATTEMPT" = 1 ] && [ -z "$PERMANENT" ]; then
      note "whole run: stage '$STAGE' failed ($1), restarting from the top in ${RETRY_WAIT_RUN}s (attempt 2 of 2)"
      status running "waiting ${RETRY_WAIT_RUN}s before retrying the whole run ('$STAGE' failed: $1)"
      cleanup; trap - EXIT ERR; pause "$RETRY_WAIT_RUN"
      exec env RUN_ATTEMPT=2 MEMORA_WEB_TOKEN="${_MWT:-}" bash "$HERE/run.sh"
    fi;; esac
  status failed "$1"; echo "FAILED at stage '$STAGE': $1" | tee -a "$LOG"; exit 1; }
# retry <tries> <pause_s> <label> <command…>: for temporary failures only. A command returning 2 means "not temporary": stop retrying.
ATTEMPT=1
retry() { local n=$1 p=$2 label=$3 i rc; shift 3
  for ((i = 1; i <= n; i++)); do
    ATTEMPT=$i
    if "$@"; then [ "$i" -gt 1 ] && note "$label: succeeded on attempt $i of $n"; return 0; else rc=$?; fi
    [ "$rc" = 2 ] && { PERMANENT=1; return 1; }
    if [ "$i" -lt "$n" ]; then echo "  $label failed (attempt $i of $n), retrying in ${p}s" | tee -a "$LOG"; pause "$p"; fi
  done
  note "$label: failed after $n attempts"; return 1; }
# git/seed output that means bad credentials, not a flaky network
AUTH_ERR='Authentication failed|could not read Username|returned error: 40[13]|Invalid login credentials|invalid_grant'
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done
  pkill -f "[n]ext start -p 3001" 2>/dev/null || true; pkill -f "[n]ode vproxy.cjs" 2>/dev/null || true; }
trap 'status failed "command failed (line $LINENO) — see run.log"; echo "FAILED at stage $STAGE (line $LINENO)" >> "$LOG"' ERR
trap cleanup EXIT

cfg() { python3 -c "import json,sys; c=json.load(open('$HERE/config.json')); print(eval(sys.argv[1], {'c': c}))" "$1"; }
REELS=$(python3 -c "
import json, os; c = json.load(open('$HERE/config.json')); only = os.environ.get('ONLY', '').split()
print(' '.join(r['name'] for r in c['reels'] if not only or r['name'] in only))")
rcfg() { python3 -c "import json; print(next(r for r in json.load(open('$HERE/config.json'))['reels'] if r['name'] == '$1')['$2'])"; }

# ── 1. preflight ───────────────────────────────────────────────────────────────
stage preflight
for c in node npm npx git ffmpeg ffprobe python3 curl; do command -v "$c" >/dev/null || fail "missing command: $c"; done
python3 -c "import numpy" 2>/dev/null || fail "python3 numpy missing (needed for the sound effects)"
[ -n "${DEMO_PASSWORD:-}" ] || fail "DEMO_PASSWORD not set"
[ -n "${ELEVENLABS_API_KEY:-}" ] || fail "ELEVENLABS_API_KEY not set"
CHROME_SHELL=$(ls -d /opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell 2>/dev/null | head -1 || true)
[ -n "$CHROME_SHELL" ] || fail "no Chromium headless shell under /opt/pw-browsers"
[ -n "$REELS" ] || fail "no reels selected (check ONLY)"
CORES=$(nproc 2>/dev/null || echo 1); RENDER_CONC=$(( CORES >= 2 ? 2 : 1 ))   # scheduled containers can have 1 core; Remotion refuses more workers than cores
CPU_MODEL=$(lscpu 2>/dev/null | sed -n 's/^Model name:[[:space:]]*//p' | head -1); MEM_GB=$(awk '/MemTotal/ {printf "%.1f", $2/1048576}' /proc/meminfo 2>/dev/null)
export HW="${CORES} core(s), ${CPU_MODEL:-unknown CPU}, ${MEM_GB:-?} GB RAM"      # logged every run so we learn what scheduled containers get
echo "hardware: $HW → render concurrency $RENDER_CONC" | tee -a "$LOG"
echo "reels: $REELS" | tee -a "$LOG"

# ── 2. memora-web (demo branch) ────────────────────────────────────────────────
stage memora-web
BRANCH=$(cfg "c['memora_web']['branch']")
MW="${MEMORA_WEB:-$WORK/memora-web}"
if [ -n "${MEMORA_WEB_TOKEN:-}" ]; then        # auth for this stage's git calls only
  export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
         GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$MEMORA_WEB_TOKEN" | base64 | tr -d '\n')"
fi
MW_REPO=$(cfg "c['memora_web']['repo']")
mw_get() { local out; out=$(mktemp)
  if [ -d "$MW/.git" ]; then git -C "$MW" fetch --quiet origin "$BRANCH" >"$out" 2>&1 && git -C "$MW" checkout --quiet -B "$BRANCH" "origin/$BRANCH" >>"$out" 2>&1
  else case "$MW" in "$WORK"/*) rm -rf "$MW";; esac; git clone --quiet --depth 1 --branch "$BRANCH" "$MW_REPO" "$MW" >"$out" 2>&1; fi
  local rc=$?; cat "$out" >> "$LOG"; grep -qE "$AUTH_ERR" "$out" && rc=2; rm -f "$out"; return $rc; }
retry 3 20 "memora-web clone" mw_get \
  || fail "could not get memora-web ($BRANCH) — $( [ -n "$PERMANENT" ] && echo 'GitHub refused the token: is MEMORA_WEB_TOKEN set, unexpired, and scoped to memora-web (Contents: read)?' || echo 'network problem, see run.log')"
_MWT="${MEMORA_WEB_TOKEN:-}"     # kept unexported (no child process sees it) only for the one whole-run restart
unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0 MEMORA_WEB_TOKEN
echo "memora-web at $(git -C "$MW" rev-parse --short HEAD)" | tee -a "$LOG"
grep -q "process.env.DEMO_PASSWORD" "$MW/scripts/seed-demo-content.ts" \
  || fail "memora-web's seed script still hard-codes the password — push the demo-recording-mode change first"
python3 - "$MW/.env.local" <<EOF
import json, sys
env = json.load(open("$HERE/config.json"))["public_env"]
open(sys.argv[1], "w").write("".join(f'{k}="{v}"\n' for k, v in env.items()))
EOF
npm_ci() { (cd "$1" && npm ci --no-audit --no-fund >>"$LOG" 2>&1); }
retry 3 20 "npm ci (memora-web)" npm_ci "$MW" || fail "npm ci failed in memora-web"
(cd "$MW" && npx next build >>"$LOG" 2>&1) || fail "next build failed"

# ── 3. servers: next on :3001, time-dilation proxy on :3000 ────────────────────
stage servers
retry 3 20 "npm ci (capture)" npm_ci "$HERE/capture" || fail "npm ci failed in capture/"
(cd "$MW" && exec npx next start -p 3001 >>"$WORK/next.log" 2>&1) & PIDS+=($!)
(cd "$HERE/capture" && exec node vproxy.cjs >>"$WORK/vproxy.log" 2>&1) & PIDS+=($!)
ok=""
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/auth/login || true)" = 200 ] && { ok=1; break; }
  sleep 2
done
[ -n "$ok" ] || fail "app did not come up on :3000 within 120 s"

# ── 4. reset the demo account to its baseline ──────────────────────────────────
stage seed
seed() { local out; out=$(mktemp)
  (cd "$MW" && set -a && . ./.env.local && set +a && npm run -s seed:demo >"$out" 2>&1); local rc=$?
  cat "$out" >> "$LOG"; grep -qE "$AUTH_ERR" "$out" && rc=2; rm -f "$out"; return $rc; }
retry 2 30 "seed" seed \
  || fail "seed:demo failed — $( [ -n "$PERMANENT" ] && echo 'login refused: is DEMO_PASSWORD (Vault demo_password) correct?' || echo 'see run.log')"

# ── 5. capture ─────────────────────────────────────────────────────────────────
for r in $REELS; do
  stage "capture:$r"
  # a retry re-seeds first, so the half-finished attempt's course/quiz/deck doesn't show up in the next try's library
  capture() { [ "$ATTEMPT" -gt 1 ] && { seed || return 1; }
    rm -rf "$HERE/capture/out/$1"
    (cd "$HERE/capture" && timeout "${CAPTURE_TIMEOUT:-1200}" node runner.mjs "$HERE/$(rcfg "$1" capture)" >>"$LOG" 2>&1) && [ -s "$HERE/capture/out/$1/clip.mp4" ]; }
  retry 2 15 "recording $r" capture "$r" || fail "recording failed"
  clip="$HERE/capture/out/$r/clip.mp4"
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$clip"); echo "  $r: ${d}s" | tee -a "$LOG"
done

# ── 6. voiceover (ElevenLabs) ──────────────────────────────────────────────────
for r in $REELS; do
  stage "voice:$r"
  (cd "$HERE/voice" && node tts.mjs "$HERE/$(rcfg "$r" vo)" >>"$LOG" 2>&1) || fail "ElevenLabs TTS failed"
done

# ── 7. assemble: footage + events + placed voiceover into the Remotion project ─
stage assemble
RM="$HERE/remotion"
retry 3 20 "npm ci (remotion)" npm_ci "$RM" || fail "npm ci failed in remotion/"
(cd "$RM" && python3 tools/synth_audio.py >>"$LOG" 2>&1) || fail "synth_audio.py failed"
for r in $REELS; do
  f=$(rcfg "$r" footage); vo_name=$(python3 -c "import json; print(json.load(open('$HERE/$(rcfg "$r" vo)'))['name'])")
  mkdir -p "$RM/public/footage/$f" "$RM/src/footage/$f"
  cp "$HERE/capture/out/$r/clip.mp4" "$RM/public/footage/$f/clip.mp4"
  cp "$HERE/capture/out/$r/events.json" "$RM/src/footage/$f/events.json"
  echo "  $r voiceover:" | tee -a "$LOG"
  if ! python3 "$RM/tools/place_vo.py" "$HERE/voice/out/vo/$vo_name" "$f" "$RM/src/footage/$f/events.json" "$HERE/$(rcfg "$r" vo)" 2>&1 | tee -a "$LOG"; then
    fail "voiceover does not fit $r"; fi
done

# ── 8. render + loudness ───────────────────────────────────────────────────────
for r in $REELS; do
  stage "render:$r"
  comp=$(rcfg "$r" composition); out="$WORK/out/$(rcfg "$r" output)"
  render() { rm -f "$WORK/render-$1.mp4"; (cd "$RM" && npx remotion render src/index.ts "$comp" "$WORK/render-$1.mp4" --concurrency="$RENDER_CONC" --log=error \
      --browser-executable="$CHROME_SHELL" >>"$LOG" 2>&1) && [ -s "$WORK/render-$1.mp4" ]; }
  retry 2 15 "render $r" render "$r" || fail "remotion render failed"
  ffmpeg -y -loglevel error -i "$WORK/render-$r.mp4" -c:v copy -af loudnorm=I=-15:TP=-1.5:LRA=11 -ar 48000 -c:a aac -b:a 192k "$out" \
    || fail "loudness pass failed"
  rm -f "$WORK/render-$r.mp4"
done

# ── 9. verify ──────────────────────────────────────────────────────────────────
stage verify
if ! python3 - "$HERE/config.json" "$WORK/out" "$REELS" <<'EOF' | tee -a "$LOG"; then fail "output check failed — see summary.json"; fi
import json, subprocess, sys
cfg, out, names = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3].split()
probe = lambda f, q: subprocess.run(["ffprobe", "-v", "error"] + q + ["-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip()
rows, bad = [], []
for r in (r for r in cfg["reels"] if r["name"] in names):
    f = f"{out}/{r['output']}"
    d = float(probe(f, ["-show_entries", "format=duration"]) or 0)
    # ffprobe's csv output can carry a trailing separator ("1080,1920,"): compare the numbers, not the raw string
    wh = ",".join(x for x in probe(f, ["-select_streams", "v:0", "-show_entries", "stream=width,height"]).replace("\n", ",").split(",") if x.strip())
    aud = probe(f, ["-select_streams", "a:0", "-show_entries", "stream=codec_name"])
    lo, hi = r["seconds"]; ok = lo - 0.5 <= d <= hi + 0.5 and wh == "1080,1920" and aud == "aac"
    rows.append({"reel": r["name"], "file": r["output"], "seconds": round(d, 1), "target": [lo, hi], "size": wh, "audio": aud, "ok": ok})
    print(f"  {'OK ' if ok else 'BAD'} {r['output']}: {d:.1f}s (target {lo}-{hi}), {wh}, audio={aud}")
    if not ok: bad.append(r["name"])
import os
rl = os.environ.get("RETRY_LOG"); retries = [l.strip() for l in open(rl)] if rl and os.path.exists(rl) else []
json.dump({"hardware": os.environ.get("HW", "unknown"), "run_attempt": int(os.environ.get("RUN_ATTEMPT", "1")),
           "retries": retries, "reels": rows}, open(f"{out}/summary.json", "w"), indent=1)
sys.exit(1 if bad else 0)
EOF
# contact sheets (8 evenly spaced frames per reel) for the run's own visual check
for r in $REELS; do
  f="$WORK/out/$(rcfg "$r" output)"; d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
  for i in 1 2 3 4 5 6 7 8; do
    ffmpeg -y -loglevel error -ss "$(python3 -c "print($d * ($i - 0.5) / 8)")" -i "$f" -frames:v 1 -vf scale=270:-1 "$WORK/sheet-$r-$i.jpg"
  done
  python3 - "$WORK" "$r" "$WORK/out/$r-sheet.jpg" <<'EOF'
import sys
from PIL import Image
w, r, out = sys.argv[1:4]; ims = [Image.open(f"{w}/sheet-{r}-{i}.jpg") for i in range(1, 9)]
W, H = ims[0].size; S = Image.new("RGB", (W * 4, H * 2))
for i, im in enumerate(ims): S.paste(im, ((i % 4) * W, (i // 4) * H))
S.save(out, quality=85)
EOF
  rm -f "$WORK"/sheet-"$r"-*.jpg
done
STAGE=done; status done "all reels rendered: $WORK/out"
echo "DONE → $WORK/out" | tee -a "$LOG"
