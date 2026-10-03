#!/usr/bin/env bash
# Memora Reels pipeline — one unattended run, start to finish, no agent decisions inside.
#
#   DEMO_PASSWORD=… ELEVENLABS_API_KEY=… bash reels/run.sh
#
# Stages: preflight → memora-web (clone/build) → servers → seed → capture ×4 → voice ×4 → assemble → render ×4 → verify
# Output: $WORK/out/*.mp4 + $WORK/out/summary.json.  Progress: $WORK/status.json (stage, state, message) and $WORK/run.log.
# Any failure stops the whole run and leaves status.json = {"state":"failed","stage":…,"message":…}. It never retries or improvises.
#
# Optional env:
#   WORK        where everything is built (default ~/reels-run). Must be outside the outreach-bot clone.
#   MEMORA_WEB  path to an existing memora-web clone to reuse (it is fetched and switched to the demo branch).
#   ONLY        space-separated reel names to run a subset, e.g. ONLY="quiz-full".
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HOME/reels-run}"
mkdir -p "$WORK/out"
LOG="$WORK/run.log"; : > "$LOG"
STAGE="start"
PIDS=()

status() { python3 - "$WORK/status.json" "$STAGE" "$1" "${2:-}" <<'EOF'
import json, sys, time
p, stage, state, msg = sys.argv[1:5]
json.dump({"stage": stage, "state": state, "message": msg, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(p, "w"), indent=1)
EOF
}
stage() { STAGE="$1"; echo "=== [$(date -u +%H:%M:%S)] $1" | tee -a "$LOG"; status running "$1"; }
fail() { status failed "$1"; echo "FAILED at stage '$STAGE': $1" | tee -a "$LOG"; exit 1; }
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
echo "reels: $REELS" | tee -a "$LOG"

# ── 2. memora-web (demo branch) ────────────────────────────────────────────────
stage memora-web
BRANCH=$(cfg "c['memora_web']['branch']")
MW="${MEMORA_WEB:-$WORK/memora-web}"
if [ -d "$MW/.git" ]; then
  git -C "$MW" fetch --quiet origin "$BRANCH" >>"$LOG" 2>&1
  git -C "$MW" checkout --quiet -B "$BRANCH" "origin/$BRANCH" >>"$LOG" 2>&1
else
  git clone --quiet --branch "$BRANCH" "$(cfg "c['memora_web']['repo']")" "$MW" >>"$LOG" 2>&1 || fail "could not clone memora-web ($BRANCH)"
fi
echo "memora-web at $(git -C "$MW" rev-parse --short HEAD)" | tee -a "$LOG"
grep -q "process.env.DEMO_PASSWORD" "$MW/scripts/seed-demo-content.ts" \
  || fail "memora-web's seed script still hard-codes the password — push the demo-recording-mode change first"
python3 - "$MW/.env.local" <<EOF
import json, sys
env = json.load(open("$HERE/config.json"))["public_env"]
open(sys.argv[1], "w").write("".join(f'{k}="{v}"\n' for k, v in env.items()))
EOF
(cd "$MW" && npm ci --no-audit --no-fund >>"$LOG" 2>&1) || fail "npm ci failed in memora-web"
(cd "$MW" && npx next build >>"$LOG" 2>&1) || fail "next build failed"

# ── 3. servers: next on :3001, time-dilation proxy on :3000 ────────────────────
stage servers
(cd "$HERE/capture" && npm ci --no-audit --no-fund >>"$LOG" 2>&1) || fail "npm ci failed in capture/"
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
(cd "$MW" && set -a && . ./.env.local && set +a && npm run -s seed:demo >>"$LOG" 2>&1) || fail "seed:demo failed (wrong DEMO_PASSWORD?)"

# ── 5. capture ─────────────────────────────────────────────────────────────────
for r in $REELS; do
  stage "capture:$r"
  (cd "$HERE/capture" && timeout 1200 node runner.mjs "$HERE/$(rcfg "$r" capture)" >>"$LOG" 2>&1) || fail "recording failed"
  clip="$HERE/capture/out/$r/clip.mp4"
  [ -s "$clip" ] || fail "no clip produced"
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
(cd "$RM" && npm ci --no-audit --no-fund >>"$LOG" 2>&1) || fail "npm ci failed in remotion/"
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
  (cd "$RM" && npx remotion render src/index.ts "$comp" "$WORK/render-$r.mp4" --concurrency=2 --log=error \
      --browser-executable="$CHROME_SHELL" >>"$LOG" 2>&1) || fail "remotion render failed"
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
    wh = probe(f, ["-select_streams", "v:0", "-show_entries", "stream=width,height"])
    aud = probe(f, ["-select_streams", "a:0", "-show_entries", "stream=codec_name"])
    lo, hi = r["seconds"]; ok = lo - 0.5 <= d <= hi + 0.5 and wh == "1080,1920" and aud == "aac"
    rows.append({"reel": r["name"], "file": r["output"], "seconds": round(d, 1), "target": [lo, hi], "size": wh, "audio": aud, "ok": ok})
    print(f"  {'OK ' if ok else 'BAD'} {r['output']}: {d:.1f}s (target {lo}-{hi}), {wh}, audio={aud}")
    if not ok: bad.append(r["name"])
json.dump({"reels": rows}, open(f"{out}/summary.json", "w"), indent=1)
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
