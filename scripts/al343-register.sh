#!/bin/bash
set -e
TS=$(date +%s)
EV=/h/workbuddy/aliceV2/docs/evidence/al343
mkdir -p "$EV"

curl -sf -X POST http://192.168.72.31:5000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"al343_${TS}\",\"password\":\"Test1234!\",\"displayName\":\"AL343 E2E\"}" \
  | tee "$EV/register.json"

echo
echo "username=al343_${TS}"
