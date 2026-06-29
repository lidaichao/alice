#!/bin/bash
set -euo pipefail
OPT=/opt/aliceV2
export NPM_CONFIG_PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
cd "$OPT"

export HOST=0.0.0.0
export PORT=5000

log() { echo "[al333-p2] $*"; }

log "=== AL-337 PM2 start ==="
pm2 delete baize-hub 2>/dev/null || true
pm2 start src/server.js --name baize-hub --cwd "$OPT" --update-env
pm2 save
sleep 3
pm2 list

log "=== AL-338 health ==="
curl -sf "http://127.0.0.1:5000/health" | head -c 500
echo
