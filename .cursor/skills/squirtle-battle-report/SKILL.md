---
name: squirtle-battle-report
description: >-
  Battle report format for AliceV2 (npm + Electron) and v3.2 archive
  (pytest + npm build). V2 is default since Epic AL-301.
---

# 战报输出规范

## AliceV2 战报（默认 · Epic AL-301）

```markdown
## 战报：XXX 交付

**commit**: <hash> · 已推送
**仓库**: H:\workbuddy\aliceV2\

### 1. 代码 + 测试

| 命令 | 结果 |
|------|------|
| npm test | X passed ✅ |
| npm start | Hub 启动 ✅ |
| npm run desktop | 注册/登录/发消息 ✅ |

**探活**（部署后）: curl http://192.168.72.147:5000/health → 200

### 2. 进度板

- `coordinator-rabbit/CURRENT_SPRINT.md` → AL-301 子任务状态

### 3. 证据

- 命令输出摘要
- **Electron 截图**（非 `/chat/` 浏览器截图）

### 4. Jira

🔗 [AL-XXX](http://ctjira1.lmdgame.com:8080/browse/AL-XXX)
```

**V2 首跑不强制**更新 `alice/docs/master/alice三期蓝图计划.md`（v3.2 线冻结）。

## v3.2 归档战报（仅维护旧仓）

```markdown
**pytest**: X passed ✅
**npm build**: Chat ✅ · Admin-UI ✅
**蓝图**: alice三期蓝图计划.md → vX.Y-rcZ
**探活**: curl http://192.168.72.147:5000/health
```

## Jira 流转

- 子任务：`[61]` → 完成
- Bug：待修复 → 处理中 → 已解决
