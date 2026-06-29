#!/bin/bash
set -euo pipefail
echo "===NODE==="
node -v 2>&1 || echo NODE_MISSING
echo "===NPM==="
npm -v 2>&1 || echo NPM_MISSING
echo "===PM2==="
pm2 -v 2>&1 || echo PM2_MISSING
echo "===DOCKER_PS==="
docker ps --format '{{.Names}}' 2>&1 || true
echo "===GIT==="
git --version 2>&1 || echo GIT_MISSING
echo "===DISK==="
df -h /opt /home/alice 2>&1 || true
