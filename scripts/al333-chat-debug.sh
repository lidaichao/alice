#!/bin/bash
set -x
TOKEN="${1:?token required}"
curl -sv -m 120 -X POST "http://192.168.72.31:5000/chat" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"Reply with exactly: BAIZE_OK"}' 2>&1
