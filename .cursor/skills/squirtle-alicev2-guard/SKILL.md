---
name: squirtle-alicev2-guard
description: >-
  AliceV2 first-run scope guard. Use before any aliceV2/ commit or when
  Rabbit issues Epic AL-301 orders. Prevents scope creep, premature server
  cutover, and writing V2 code into archive alice/.
---

# AliceV2 首跑守卫

> 产品真源：`pm-Carroll/AliceV2_开发计划_总纲_v1.0.md` · Epic **AL-301**

## 波次 A 建仓 · 第 0 步（AL-307 · 先于写业务代码）

收到兔子波次 A 令后，**先**完成 Cursor 活仓切换，再复制 Baize：

```text
1. 创建 H:\workbuddy\aliceV2\
2. 复制 alice/.cursor/ → aliceV2/.cursor/（rules + skills 全量）
3. 此后 rules/skills **以 aliceV2/.cursor/ 为唯一活副本**；alice/.cursor/ 仅归档参照
4. 提示协调者：Cursor 工作区切到 H:\workbuddy\aliceV2（或用 move_agent_to_root）
5. 再执行 Baize 复制 @ b989830 → npm install / test / start / desktop
```

**铁律**：波次 A 之后所有代码、commit、战报默认在 `aliceV2/`；**禁止**在 `alice/` 继续当活仓开发。

## 提交前必查

| # | 检查项 | 违反后果 |
|---|--------|---------|
| 1 | 代码只在 `H:\workbuddy\aliceV2\` | 战报判黄 |
| 2 | **未**在 `alice/` 写 V2 功能 | 战报判黄 |
| 3 | 首跑 **未**接 DeepSeek / Cursor SDK | scope creep |
| 4 | 首跑 **未**改白泽品牌/UI | 改造 2 |
| 5 | 首跑 **未**自部署 147 / `docker compose down` | 越权 |
| 6 | 147 清场 **未**在安装包+公告+试装(②③④)前 | 八步违规 |
| 7 | Git **未** force push main | B1 违规 |
| 8 | 配置来自 `*.example.yaml` + `.env`，**未**提交密钥 yaml | 安全 |

## 验收口径（首跑）

| 项 | 标准 |
|----|------|
| 本地 | `npm test` + `npm start` + `npm run desktop` |
| 服务器 | `curl http://192.168.72.147:5000/health` → 200 |
| 客户端 | Electron 连 147:5000 · 登录 · Claude 流式 |
| **废弃** | `/chat/` · Admin `:8080` · Flask pytest 矩阵 |

## 首跑没有（别测、别修、别承诺）

Dify · n8n · Web Chat · Vue Admin · Alice RBAC · DeepSeek · `electron-updater` 自动更新

## AI 方案

首跑 = **方案 A**（Claude / local_kb）。DeepSeek → **改造 1 P0**。

## 停服八步（知晓顺序，清场由兔子执行）

① 本地全绿 → ② 安装包 → ③ 公告 → ④ 试装 → ⑤ 备份 → ⑥ 停 Docker → ⑦ 部署 `/opt/aliceV2` → ⑧ E1–E8 验收
