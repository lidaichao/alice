# Alice Jira AI — 灰度测试白皮书 (Graybox SOP)

> 版本：v1.3 | 日期：2026-06-08 | 作者：可达鸭 (Psyduck)

**相关文档**：[三期蓝图计划（开发校准）](alice三期蓝图计划.md) · [E4 Hub 凭据迁移](E4_hub_credentials_migration.md) · [技术架构](Alice_Master_Architecture_v1.0.md) · [文档索引](README.md) · [白泽 Baize 架构](Baize_Architecture_v1.0.md)

---

## 一、什么是 Alice？

Alice 是一款面向游戏研发团队的 AI 工作助手。

- 一句话查 Jira 任务、SVN 提交、代码 Diff
- 自动关联 Notion 策划文档做 Code Review
- 反幻觉设计：数据溯源 + 防编造

**当前版本**：v1.0.0-beta（灰度测试）

---

## 二、如何安装

### macOS

1. 从内部 Release 页面下载 `Alice-Jira-AI-v1.0.0-beta-darwin-arm64.dmg`
2. 双击 `.dmg`，将 Alice 拖入 `Applications`
3. **⚠️ 第一次打开时**：系统会提示"未验证的开发者"
   - 打开 **系统设置 → 隐私与安全性**
   - 在底部找到"Alice Jira AI 已被阻止"，点击 **"仍要打开"**
   - 确认后即可正常启动

### Windows

1. 下载 `Alice-Jira-AI-Setup-v1.0.0-beta.exe`
2. 双击安装，选择安装路径
3. 桌面会出现快捷方式 "Alice Jira AI"

---

## 三、配置指南

### 3.1 Hub 独占 Jira（推荐 · E4）

生产环境由 **Hub** 统一持有 Jira 凭据，客户端**不必**填写 PAT。详见 [E4_hub_credentials_migration.md](E4_hub_credentials_migration.md)。

| 角色 | 操作 |
|------|------|
| **运维** | Admin 或 `backend/global_config.json` 配置 `JIRA_URL`、`JIRA_PAT`；启动 Hub 时设 `ALICE_HUB_ONLY_JIRA=1`（`scripts/start_hub.ps1` 已包含） |
| **用户** | 客户端仅配置 **Hub 地址**（默认 `http://127.0.0.1:9099`）与 DeepSeek Key；设置里 **Jira PAT 可留空** |
| **验收** | 空 PAT 下可搜 Jira、可走草稿确认流 — `scripts/e2e_e4_hub_only.py` |

### 3.2 客户端携带 PAT（回滚 / 灰度遗留）

若未启用 `ALICE_HUB_ONLY_JIRA`，仍可在客户端设置中填写 PAT：

1. 登录 Jira → **个人设置** → **Personal Access Tokens** → 创建 Token（只显示一次）
2. Alice 设置 → **Jira 地址** + **PAT** + **DeepSeek Key** → **Test Connection** ✅

### 3.3 管理员：Web 后台

浏览器打开 `http://<服务器>:9099/admin`（需管理员 Bearer Token）。

| 操作 | 说明 |
|------|------|
| 默认对话模型 | 下拉选择后立即生效，写入 `global_config.json` |
| 编辑 API 配置 | 仅修改 DeepSeek API 地址与 Key |
| 周报字段映射 | Jira 区配置 `JIRA_DEADLINE_FIELD_BY_PROJECT`（如 CT → End date） |

刷新页面后模型选择应保持不变；若变回 `deepseek-chat`，请确认后端已更新至含加载守卫的版本。

---

## 四、如何使用

### 常用对话

**闲聊**：`ordinary_chat`（如打招呼、天气闲聊）走**无工具 LLM 闲聊道**（流式自然回复，非固定模板）；一旦句中出现 Jira/任务/文档等作业信号，才进入检索与工具链路。

| 你说 | Alice 回答 |
|------|-----------|
| "CT-10888 最近提交了啥？" | SVN 提交列表（版本/作者/时间） |
| "帮我分析一下 r40538 的 diff" | Code Review + 关联策划文档 |
| "有哪些阵型相关的设计案？" | Notion 文档列表 |
| "写一下本周 CT 项目周报（6/1-6/5）" | Jira 按截止时间字段汇总 + PM 周报 |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Alt + Space` | 显示/隐藏 Alice 窗口 |

### 4.1 批量创建 Jira 任务（草稿箱 · 两步确认）

适用于「帮我草拟 / 批量创建 N 条 Jira 任务」类问法。Alice **不会**未经确认直接写 Jira。

| 步骤 | 你在 UI 上做什么 | 系统行为 |
|------|------------------|----------|
| 1 | 对话结束后出现 **草稿箱** 卡片 | 可 inline 修改标题、项目 Key、问题类型；若有黄色警告请先看 |
| 2 | 点击 **提交草稿** | 生成 **Jira 操作确认** 卡，列出全部待创建条 |
| 3 | 点击 **授权放行** | 调用 Jira API 创建；结果以助手消息显示（含 Issue Key 或失败原因） |
| 取消 | 草稿卡点 **取消** | 作废该草稿，不会创建 Issue |

**注意**：刷新页面后，**待确认的操作卡** 会自动恢复（同一会话）；若只剩一半流程，可重新向 Alice 描述需求生成新草稿。

**前置条件**：Hub 已配置 Jira 凭据（E4 推荐）；或客户端 PAT 有效（§3.2 回滚模式）。

### 4.2 团队规则（服务端记忆）

侧栏底部 **「团队规则（服务端）」** 面板：

- 与聊天里「请记住…」写入的是**同一份**服务端规则（`shallow_memory.json`），下轮对话会自动注入模型。
- 与浏览器内的「五层记忆」**不是**同一套数据；改团队规则请用本面板。
- 支持新增 / 编辑 / 删除；条数过多时仅部分会注入 Prompt（面板会提示约 2000 字上限）。

---

## 五、遇到 Bug 怎么办？🐞

### 5.1 一键反馈

1. 点击 Alice 左下角的 **🐞 反馈** 按钮
2. 在弹窗中描述问题（越详细越好）
3. 点击 **"生成诊断报告"**（自动抓取后端日志 + 客户端环境）
4. 点击 **"📋 复制到剪贴板"** 或 **"💾 下载 .txt"**

### 5.2 提交给 IT 支持

将生成的诊断报告通过以下任一方式提交：

| 方式 | 地址 |
|------|------|
| **Jira** | 在 CT 项目下新建 Bug，粘贴报告内容 |
| **企业微信** | 发送到 "Alice 灰度测试群" |
| **直接联系** | 找李大超 (lidaichao@lmdgame.com) |

### 5.3 常见问题自助

| 问题 | 解决方法 |
|------|----------|
| "无法连接后端" | 重启 Alice 应用 |
| "Jira 连接失败" | 点击 Test Connection 检查 PAT 是否有效 |
| "查询无结果" | 确认 Jira 地址正确、VPN 已连接 |
| Window 窗口卡死 | `Alt+Space` 隐藏再显示 |

---

## 六、灰度测试目标

| 目标 | 验收标准 |
|------|----------|
| 安装成功率 | 95% 以上用户一次安装成功 |
| 核心对话 | 查任务、看提交、分析 Diff 三个场景跑通 |
| Bug 反馈 | 每份反馈含完整诊断日志 |
| 稳定性 | 连续使用 2 小时无崩溃 |

---

## 七、OTA 自动更新

Alice 内置 OTA 更新机制：

- 每次启动自动检查新版本（静默，不打断工作）
- 有更新时后台下载
- **下次重启 Alice 时自动生效**

---

## 八、发版门禁（开发/运维）

每次合并 main 或对外发灰度包前，执行 [alice三期蓝图计划.md](alice三期蓝图计划.md) **§6.1**。

**可复制勾选单**：[`eval/reports/release_checklist_M1.md`](../../eval/reports/release_checklist_M1.md)（复制为 `eval/reports/release_YYYY-MM-DD.md` 并逐项打勾）

| # | 步骤 | 命令 / 动作 | 勾选 |
|---|------|-------------|------|
| 1 | CI 门禁（含意图 + kb 矩阵 + C9 防回归） | `py -3 scripts/ci_gate.py` → `CI_GATE_OK` | [ ] |
| 2 | 集成冒烟（Hub 9099） | `ALICE_RUN_INTEGRATION=1 py -3 scripts/ci_gate.py` | [ ] |
| 3 | Hub-only Jira（E4） | `ALICE_RUN_INTEGRATION=1 ALICE_RUN_E4=1 py -3 scripts/ci_gate.py` | [ ] |
| 4 | GDrive 知识库 e2e（Phase B） | `ALICE_RUN_INTEGRATION=1 ALICE_RUN_GDRIVE_E2E=1 py -3 scripts/ci_gate.py` | [ ] |
| 5 | 协调者基线（可选） | `py -3 backend/run_eval.py coordinator_m1` 不低于 [`coordinator_baseline_M1.md`](../../eval/reports/coordinator_baseline_M1.md) | [ ] |
| 6 | 发版记录 | `eval/reports/release_YYYY-MM-DD.md`（仅自动化结果） | [ ] |
| 7 | （可选）第四节场景 | 产品不要求人工签字时跳过 | — |

---

## 九、联系方式

| 角色 | 联系方式 |
|------|----------|
| 技术负责人 | 李大超 — lidaichao@lmdgame.com |
| 架构师 | 兔子 — 企业微信 "Alice 架构讨论群" |
| Bug 提交 | Jira CT 项目 → 新建 Bug → 粘贴诊断报告 |
