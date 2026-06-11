---
name: squirtle-battle-report
description: >-
  When Squirtle completes a development wave and needs to deliver the final
  report, use the three-part format: code changes plus test results, blueprint
  update with version stamp, and sprint board update. Include Jira transition
  confirmation links.
---

# 战报输出规范（三件套）

## 交付格式

```markdown
## 战报：XXX 交付

**commit**: <hash> · 已推送

### 1. 代码 + 测试

| 文件 | 内容 |
|------|------|
| ... | ... |

**pytest**: `X passed, Y failed` ✅
**npm build**: Chat ✅ · Admin-UI ✅

### 2. 蓝图

- `alice三期蓝图计划.md` → vX.Y-rcZ 修订记录追加

### 3. Jira 流转

| 父任务 | 子任务 | 状态 |
|--------|--------|:--:|
| ... | ... | ✅ |

🔗 Jira: [AL-XX](http://ctjira1.lmdgame.com:8080/browse/AL-XX)
```

## Jira 流转标注格式

```
🔗 子任务 AL-XXX 已流转 → 完成
Jira 链接：http://ctjira1.lmdgame.com:8080/browse/AL-XXX
```

## 进度板

更新 `coordinator-rabbit/CURRENT_SPRINT.md`：
- Epic/状态/下一波
- 父任务/子任务完成表
- 改动文件清单
- pytest 结果

## 开发任务闭环

1. 子任务一步流转：`[61]` → 完成
2. 父任务同步流转：同波次所有子任务完成后 → `[61]` 完成
3. Bug 两步流转：待修复 `→[11]` 处理中 `→[21]` 已解决
