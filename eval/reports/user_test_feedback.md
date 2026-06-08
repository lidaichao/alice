# 用户内测反馈（不阻塞发版）

> 当前策略：**不发布 rollout**，先热修 GDrive 检索。

## GDrive 表格失败用例（请填写）

| 字段 | 内容 |
|------|------|
| 用户原话 | |
| 表格文件名 | |
| file_id（可选） | |
| 期望 Alice 引用的内容 | |
| 实际 Alice 回答摘要 | |
| 日期 | |

填写后同步到 `backend/eval/datasets/gdrive_sheet_cases.yaml` 的 `gsheet-001`，并将 `skip: false`。

## 优先级

- P0：完全无法读到表格 / 编造内容
- P1：读到了但答非所问
- P2：体验问题

## 已暂停

- Wave 0 打包全员分发
- M3.4 控制台内审批（待 P0 清单）
