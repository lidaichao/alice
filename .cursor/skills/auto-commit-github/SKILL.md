---
name: auto-commit-github
description: >-
  After completing an implementation or fix task with file changes in the repo,
  automatically run git commit and push to GitHub without waiting for the user to
  ask. Use when finishing agent work, closing a feature/fix, or when the user
  sets a standing policy to auto-publish to GitHub.
---

# 任务完成后自动提交 GitHub

## 触发条件（满足即执行，无需用户再说「提交」）

- 本轮对话中**已修改/新增**仓库内源码或文档，且任务目标已达成（或用户表示可以收尾）
- **不触发**：纯问答、只读评审、用户明确说「先别提交 / 不要 push」

## 禁止纳入版本库

- `.env`、`global_config.json`、`**/global_config.json`、密钥、PAT
- `backend/runtime/`、本机运行数据、`node_modules/`、`dist/`
- 用户未要求的 `.cursor/` 本地缓存（**可提交** `.cursor/rules/`、`.cursor/skills/`）

## 执行步骤（必须实际跑命令，不要只给命令让用户自己跑）

1. 并行：`git status`、`git diff`、`git diff --cached`、`git log -3 --oneline`
2. 只 `git add` 与本次任务相关的路径（避免误加 secrets/runtime）
3. 撰写 **1–2 句英文** commit message（说明 why，type: `feat`/`fix`/`refactor`/`docs`）
4. Windows 提交：`git commit -F .git/COMMIT_MSG_TMP`（勿用易失败的 `git commit -m` 若环境有 trailer 问题）
5. **`git push origin` 当前分支**（默认 `master`）；推送失败则汇报错误，不 `--force`
6. 收尾：`git status`，在汇报中给出 **commit hash** 与是否已 push

## 安全协议（与团队一致）

- 禁止 `git config` 修改、`--no-verify`、`push --force`（除非用户明确要求）
- 禁止空提交；无变更则跳过
- push 到 `main`/`master` 若需审批被拦，用 `request_smart_mode_approval` 重试并说明原因

## 与杰尼龟 SOP 的关系

本 Skill 覆盖旧版「仅用户明确要求才 commit」——以**本 Skill + `.cursor/rules/auto-github-commit.mdc`** 为准。
