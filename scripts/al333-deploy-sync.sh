#!/bin/bash
set -euo pipefail
OPT=/opt/aliceV2
ARCHIVE=/home/alice/alice.archived-2026-06-29
export NPM_CONFIG_PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"

log() { echo "[al333-sync] $*"; }

log "extract source"
rm -rf "$OPT"/*
mkdir -p "$OPT"
tar xzf /tmp/aliceV2-src.tgz -C "$OPT"

log "npm ci"
cd "$OPT"
npm ci --omit=dev

log "apply jira token from archived env if present"
if [ -f "$ARCHIVE/.env.prod" ]; then
  PAT=$(grep -h '^ALICE_JIRA_PAT=' "$ARCHIVE/.env.prod" | head -1 | cut -d= -f2- | tr -d '"')
  if [ -n "$PAT" ]; then
    cat > "$OPT/baize/config/jira.yaml" <<EOF
enabled: true
baseURL: "http://ctjira1.lmdgame.com:8080"
deploymentType: server
apiVersion: "2"
authType: bearer
apiToken: "$PAT"
defaults:
  projectKey: "AL"
  issueType: "Task"
EOF
    log "jira.yaml updated from archive"
  fi
fi

log "claude-code disabled"
grep -q '^enabled:' "$OPT/baize/config/claude-code.yaml" && sed -i 's/^enabled:.*/enabled: false/' "$OPT/baize/config/claude-code.yaml" || true

log "sync done"
