#!/bin/bash
set -e
EV=/h/workbuddy/aliceV2/docs/evidence/al343
TOKEN="gmLA1g5aIVacn9PspYXnC7vI3TTWByvhcgnn_f6EDCE"
BASE=http://192.168.72.31:5000

# Jira natural language query via chat
echo "=== Jira NL query: AL-301 child issues ==="
curl -sf -m 120 -X POST "$BASE/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"text":"AL-301 下有哪些未完成的子任务"}' \
  | tee "$EV/jira-query.json"
echo
