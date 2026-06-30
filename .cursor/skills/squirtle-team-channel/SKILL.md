---
name: squirtle-team-channel
description: >-
  When the coordinator says to check TEAM_CHANNEL.md, read the shared
  message board at coordinator-rabbit/TEAM_CHANNEL.md and write battle
  reports or blocker notices using the fixed format. Never read or write
  without explicit coordinator instruction.
---

# 团队频道协议

## 文件位置

`H:\workbuddy\coordinator-rabbit\TEAM_CHANNEL.md`

## 铁律

1. **只有协调者说"杰尼龟去看 TEAM_CHANNEL.md"，才去读。不自动读，不自动写。**
2. ⛔ **绝对禁止在历史消息中间插入** — 新消息只能写在 `<!-- NEW MESSAGES HERE -->` 注释下方。不删旧消息，不编旧消息，不在已有消息之间加内容。违者杰尼龟犯错。

## 读取

从文件**开头往后**找第一条 `@杰尼龟` 或 `@全员` 的消息。不翻全文。

## 写入（严格遵守——错一行都不行）

**位置**：找到文件头部的 `<!-- NEW MESSAGES HERE -->` 注释，在它**正下方**（紧挨着，后跟三个空行）插入新消息。

**操作步骤**：
1. Read TEAM_CHANNEL.md 前 30 行，找到 `<!-- NEW MESSAGES HERE -->`
2. 在该注释下方插入你的消息
3. 新消息后保留 `---` 分隔线，旧消息原样不碰

**格式模板**（逐字照抄，缺一个 `#` 都不行）：

```
## 发言人：杰尼龟
@：兔子
时间：YYYY-MM-DD HH:MM
类型：回复 · {简短描述}

```text
{战报或回复内容}
```
```

- 发言人固定为「杰尼龟」
- `类型` 字段必填，简短描述（如「回复 · XXX 战报」「回复 · 阻塞」）
- 内容必须用 ` ```text ` 代码块包裹（反引号顶格，不缩进）
- **绝对不要**把消息写在历史消息堆里——只能写在 `<!-- NEW MESSAGES HERE -->` 下方

## 发言场景

| 什么时候写 | @谁 | 内容 |
|-----------|------|------|
| 完成开发任务后 | @兔子 | 战报：改动文件 + 测试结果 |
| 收到兔子新指令 | @兔子 | 回复确认或提出问题 |
| 遇到阻塞 | @协调者 | 阻塞原因 |

## Confluence 战报规则

Confluence 战报走 `confluence_channel.py` 模块。以下铁律：

1. **战报内容必须中文** — 标题（h3）、列表项（li）、描述文字全部中文。科技名词（npm/Vite/IPC/SSE/Jira）保留英文，但段落文本不中英混写。
2. **证据路径含仓库前缀** — `aliceV2/docs/evidence/alXXX/文件名`，不可只写 `docs/evidence/...`。
3. **证据先存 aliceV2 再 commit** — 兔子只读 aliceV2 仓库。
4. **提交 hash 标注仓库名** — 如 `e29276d (aliceV2)`。
