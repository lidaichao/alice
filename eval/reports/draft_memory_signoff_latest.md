# 草稿箱 + 团队记忆 — 收口验收记录

> 生成时间: 2026-06-05  
> 范围: 工作项 1 + 3 自检报告收口

## 自动化

| 项 | 结果 | 说明 |
|----|------|------|
| `test_memory_and_drafts`（模块直跑） | **通过** | `py -3` 内联执行 create/reject/CRUD |
| `scripts/smoke_draft_memory.py` | **需重启后端** | 当前 9099 进程若为旧代码，`/api/memory/entries` 返回 404 |
| `/health` | **通过** | `ai-bridge-v5` status ok |

**操作提示**: 结束占用 9099 的进程后，在 `backend/` 执行 `py -3 ai_bridge.py`，再跑 `py -3 scripts/smoke_draft_memory.py`。

## PRD 手工验收（#14～#17）

| # | 场景 | 代码就绪 | 本机签字 |
|---|------|----------|----------|
| 14 | 批量创建 → 改 summary → 两步确认 → 会话 Key | 是 | 待兔子在 5174+有效 PAT 下点验 |
| 15 | F5 后 ConfirmCard 仍在 | `restorePendingOperations` 已实现 | 待兔子 F5 点验 |
| 16 | 取消草稿后不可再 confirm | `POST /drafts/:id/reject` | 模块单测通过 |
| 17 | 切会话仅本会话 pending | `conversation_id` + pending 过滤 | 待兔子双会话点验 |

## 收口补丁（本轮）

- 草稿卡展示 SSE `warnings`（`chatSlice` + `DraftCard`）
- `confirm` 响应 warnings 合并进 ConfirmCard
- Graybox SOP §4.1 / §4.2
- `scripts/smoke_draft_memory.py`

## 仍属排期外（DEBT）

- recovery 重试 UI、全量协调者评测、Baize Phase4、F5 恢复第一步草稿卡、记忆 API 强鉴权
