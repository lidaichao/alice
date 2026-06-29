#!/bin/bash
set -euo pipefail
EV="${1:-docs/evidence/al333}"
BASE="${2:-http://192.168.72.31:5000}"
USER="al333smoke$(date +%s)"
PASS='SmokeTest!333'
mkdir -p "$EV"

log() { echo "$*" | tee -a "$EV/smoke.log"; }

log "=== health external ==="
curl -sf "$BASE/health" | tee "$EV/health-external.json"
echo

log "=== register ==="
REG=$(curl -sf -X POST "$BASE/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\",\"displayName\":\"AL333 Smoke\"}")
echo "$REG" | tee "$EV/register.json"
TOKEN=$(echo "$REG" | node -e "const d=JSON.parse(require('fs').readFileSync(0,'utf8')); process.stdout.write((d.data&&d.data.token)||'');")
log "token_len=${#TOKEN}"

log "=== auth/me ==="
curl -sf "$BASE/auth/me" -H "Authorization: Bearer $TOKEN" | tee "$EV/me.json"
echo

log "=== chat (non-stream) ==="
CHAT=$(curl -sf -m 120 -X POST "$BASE/chat" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"text":"Reply with exactly: BAIZE_OK"}')
echo "$CHAT" | tee "$EV/chat.json"
echo
log "smoke_done"
