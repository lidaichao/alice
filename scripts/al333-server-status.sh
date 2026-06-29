#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
echo "=== docker ps (alice) ==="
docker ps -a --filter name=alice 2>/dev/null || docker ps -a | head -5
echo
echo "=== pm2 list ==="
pm2 list
echo
echo "=== archive dir ==="
ls -ld /home/alice/alice.archived-2026-06-29 2>/dev/null || echo missing
