#!/bin/bash
set -euo pipefail
DEPLOY=/home/alice/alice
KEY=$(grep -h '^N8N_API_KEY=' "$DEPLOY/.env.prod" | head -1 | cut -d= -f2- | tr -d '"')
echo '===GLOBAL_CONFIG==='
cat "$DEPLOY/backend/global_config.json"
echo '===ENV_PROD==='
cat "$DEPLOY/.env.prod"
echo '===N8N_WORKFLOWS==='
curl -s -H "X-N8N-API-KEY: $KEY" 'http://127.0.0.1:5678/api/v1/workflows?limit=250'
echo '===DOCKER_VOLUME_LS==='
docker volume ls
echo '===VOLUME_INSPECT_DIFY==='
docker volume inspect alice_dify_pgdata
echo '===VOLUME_INSPECT_N8N==='
docker volume inspect alice_n8n_data
