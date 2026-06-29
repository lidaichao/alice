# AL-343 八步⑧ E1–E4 首跑验收证据

**日期**: 2026-06-29  
**Hub**: `192.168.72.31:5000`  
**Epic**: AL-301  
**经办**: 杰尼龟

## 验收项

| 步骤 | 检查项 | 结果 | 证据 |
|------|--------|------|------|
| E1 | `curl :5000/health` → `baize-local-hub` | ✅ | `health.json` |
| E2 | Electron 连接 `.31:5000` 登录窗口 | ✅ | `03-login-page.png` |
| E3 | 注册 + 登录成功 | ✅ | `04-after-login.png` · `register.json` |
| E4 | `/chat/stream` 流式 Cursor 回复 | ✅ | `05-chat-streaming.png` |
| E5 | docker 无 alice · PM2 online | ✅ | `server-status.txt` |
| P1 | Jira NL 查询 AL-301 子任务 | ✅ | `jira-query.json`（35 条明细） |

## 关键输出

### Health
```json
{"ok":true,"service":"baize-local-hub","phase":"1"}
```

### Jira 查询
- 问题：AL-301 下有哪些未完成的子任务
- 回复：35 条未完成，按 6 个父任务分组
- Provider：cursor
