#!/bin/bash
set -e
export PATH="$HOME/.local/bin:$PATH"
echo "=== docker ps (alice) ==="
docker ps -a --filter name=alice 2>/dev/null || echo "no alice containers"
echo
echo "=== pm2 list ==="
pm2 list --no-color
