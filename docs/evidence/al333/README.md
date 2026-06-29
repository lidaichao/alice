# AL-333 P6 清场部署证据

**日期**: 2026-06-29  
**服务器**: `192.168.72.31`  
**部署路径**: `/opt/aliceV2`  
**进程**: PM2 `baize-hub`

## 步骤完成情况

| AL | 步骤 | 状态 | 证据 |
|----|------|------|------|
| AL-334 | Node/npm/PM2 环境检查 | ✅ | `deploy-part1.log` |
| AL-335 | docker down + 归档 | ✅ | `deploy-part1.log` |
| AL-336 | 代码部署 `/opt/aliceV2` | ✅ | `deploy-sync.log`（tar+scp，Git SSH 无密钥） |
| AL-337 | PM2 启动 | ✅ | `deploy-part2.log` |
| AL-338 | health 探活 | ✅ | `health-external.json` |
| AL-339 | auth + Cursor chat | ✅ | `register.json`, `me.json`, `chat.json` |

## 关键输出

### Health (外部)
```json
{"ok":true,"service":"baize-local-hub","phase":"1"}
```

### Chat (Cursor provider)
- 请求: `POST /chat` body `{ "text": "Reply with exactly: BAIZE_OK" }`
- 响应: `"reply":"BAIZE_OK"`, `"provider":"cursor"`

## 回滚

```bash
pm2 stop baize-hub
mv /home/alice/alice.archived-2026-06-29 /home/alice/alice
cd /home/alice/alice && docker compose -f docker-compose.prod.yml up -d
```

## 脚本

- `scripts/al333-deploy-part1.sh` — 环境检查、docker down、归档
- `scripts/al333-deploy-sync.sh` — tar 解压、npm ci、jira.yaml 从归档注入
- `scripts/al333-deploy-part2.sh` — PM2 启动 + 本地 health
- `scripts/al333-smoke.sh` — 外部 health / register / me / chat

## 备注

- 生产 `.env` 已 scp 至服务器 `/opt/aliceV2/.env`（**不入 Git**）
- `jira.yaml` 已从 `alice.archived-2026-06-29/.env.prod` 注入 PAT
- 旧 Docker 栈 8 容器已停；归档目录保留
