# M2 — PRD 写路径点验清单

> 对照 [Alice_Master_PRD_v1.0.md](Alice_Master_PRD_v1.0.md) #14–17 · 灰盒 SOP

| # | 场景 | 步骤 | 预期 | 状态 |
|---|------|------|------|------|
| W1 | 批量创建草稿 | 对话触发 `create_issues_draft` | SSE `draft_card`；F5 后草稿仍在 | ☐ |
| W2 | 草稿提交 | DraftCard 编辑 → 提交 | 生成 `confirm_card`；operation `awaiting_confirmation` | ☐ |
| W3 | 授权写入 | ConfirmCard 放行 | `operation_progress` SSE；Jira 创建成功 | ☐ |
| W4 | 拒绝 | ConfirmCard 拒绝 | 无 Jira 写入；pending 列表清除 | ☐ |
| W5 | 恢复 | 标签失败 → recovery | 「移除标签后重试」可续跑 | ☐ |
| W5b | 恢复 | 缺 projectKey → recovery | 表单补 Key 后可创建 | ☐（单测 `test_recovery_supplement`） |
| W6 | 状态流转 | 「CT-xxx 改成处理中」 | 确认卡含 transition；执行成功 | ☐ |

执行人：________  日期：________  签字：________
