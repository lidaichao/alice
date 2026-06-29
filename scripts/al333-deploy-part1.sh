#!/bin/bash
# AL-333 P6 deploy — run ON server as alice (via ssh bash -s < this file)
set -euo pipefail

DEPLOY_OLD=/home/alice/alice
ARCHIVE=/home/alice/alice.archived-2026-06-29
OPT=/opt/aliceV2
REPO=git@github.com:lidaichao/alice.git
DATE_TAG=2026-06-29

log() { echo "[al333] $*"; }

log "=== AL-334 env check ==="
node -v
npm -v
export NPM_CONFIG_PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v pm2 >/dev/null 2>&1; then
  log "installing pm2 to ~/.local"
  npm install -g pm2
fi
pm2 -v

log "=== AL-335 stop old stack ==="
if [ -d "$DEPLOY_OLD" ]; then
  cd "$DEPLOY_OLD"
  docker compose -f docker-compose.prod.yml down || docker compose down || true
fi
sleep 2
docker ps --format '{{.Names}}' | grep -E '^alice-' && { log "ERROR: alice containers still running"; exit 1; } || log "no alice containers running"

if [ -d "$DEPLOY_OLD" ] && [ ! -e "$ARCHIVE" ]; then
  mv "$DEPLOY_OLD" "$ARCHIVE"
  log "archived to $ARCHIVE"
elif [ -d "$ARCHIVE" ]; then
  log "archive already exists: $ARCHIVE"
else
  log "WARN: $DEPLOY_OLD not found"
fi

log "=== AL-336 deploy code ==="
echo 'huaban123!' | sudo -S mkdir -p "$OPT"
echo 'huaban123!' | sudo -S chown alice:alice "$OPT"
if [ ! -d "$OPT/.git" ]; then
  git clone "$REPO" "$OPT"
else
  cd "$OPT" && git fetch origin && git checkout master && git pull origin master
fi
cd "$OPT"
git log -1 --oneline

log "=== npm ci ==="
npm ci --omit=dev

log "done through npm ci — waiting for .env from local scp step"
