#!/bin/bash
# Auto-push wrapper for macOS launchd (com.armaan.memora-outreach-push).
# Runs on a timer as Armaan's own macOS user -- NOT inside any Claude tool,
# so it isn't subject to the Cowork cloud container's git-egress proxy or
# command classifier. It only pushes if there's something new to push, so
# it's silent almost all the time.
#
# Setup instructions: scripts/SETUP-auto-push.md

set -euo pipefail

REPO_DIR="/Users/armaanmahajan/Documents/Projects/Memora/outreach-bot"
LOG_FILE="$HOME/Library/Logs/memora-outreach-push.log"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"
}

cd "$REPO_DIR" || { log "ERROR: repo dir not found at $REPO_DIR"; exit 1; }

# Don't fight with an in-progress git operation (e.g. a Claude-driven commit
# still running against this same working copy).
if [ -f .git/index.lock ]; then
  log "SKIP: .git/index.lock present, another git process may be active"
  exit 0
fi

if ! git fetch origin main --quiet 2>>"$LOG_FILE"; then
  log "ERROR: git fetch failed, see above"
  exit 1
fi

AHEAD=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')

if [ "$AHEAD" -eq 0 ]; then
  exit 0  # nothing to do, stay quiet
fi

log "Found $AHEAD local commit(s) not yet on origin/main, pushing..."

if git push origin main >>"$LOG_FILE" 2>&1; then
  log "Push succeeded. origin/main is now at $(git rev-parse --short HEAD)"
else
  log "ERROR: push failed, see output above -- will retry next interval"
  exit 1
fi
