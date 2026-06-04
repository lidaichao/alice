# MEMORY.md - 长期记忆

## 用户偏好

- **Diff 展示**：只给核心摘要（提交人、时间、变更文件清单、增删行数），不要完整 diff 内容
- **JIRA 查询优先**：提到工作任务相关内容，第一时间考虑 JIRA 数据库

## 项目信息

### JIRA 集成
- JIRA 服务器：http://ctjira1.lmdgame.com:8080（内网）
- 认证方式：PAT（永久 token）
- 项目：足球小将 (CT)
- MCP Server 代码：H:\workbuddy\jira\wecom-jira-bridge\
- 关键注意：用户名用英文账号名（如 pengjiajun），状态名是中文

### SVN 代码仓库
- SVN 地址：https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3
- 账号：lidaichao
- FishEye：http://192.168.8.34:8060（仓库名 CT-V3）

### 已修复的 bug
- jira_api.py：priority/assignee 可能为 None 导致抛异常（2026-05-26）
- jira_mcp_server.py：jira_search 中 result 可能为 None（2026-05-26）

### 知识库集成（2026-05-26）
- **Notion**：已连接，API token 存于 ~/.config/notion/api_key
  - 主数据库："策划文档V4"（含 JIRA-key 列，可关联 Jira 任务）
  - 技能：~/.workbuddy/skills/notion/
- **Google Drive**：已连接，API Key AIzaSyAEDfaeKL4uBrIGEgBHmmG_Hc4TFbMUsUY
  - 文件夹1 (1b7JJwDT...)：策划/需求文档（球员系统、战斗框架、关卡、技能、跑测工具等）
  - 文件夹2 (1DvBObfm...)：系统文档（半场切换系统需求等）
  - 技能：~/.workbuddy/skills/google-drive/（Maton方式，未使用；直接用 REST API）
- **关联方式**：Jira Issue → Notion JIRA-key 列 → Google Drive 需求文档

---

## 前端架构演进（2026-06-04 杰尼龟接任）

### 状态机重构（换心手术）
- **双 Store 合并**：废弃 `useSessionStore`（idb-keyval），统一使用 `useChatStore`（Dexie AliceChatDB）
  - 涉及文件：`App.tsx`、`Sidebar.tsx`、`Header.tsx`
  - 发送链路：手写 `doSendMessage` → `chatSlice.sendMessage`（含 agent systemPrompt、图片、confirm_card、citations 全链路）
  - AI 气泡渲染：纯文本 `whitespace-pre-wrap` → `MarkdownRenderer`（代码高亮、表格、Mermaid、引用胶囊）
  - 新挂载：`ConfirmCard`（Jira 操作确认卡片）已接入消息流末尾
- **致命 bug 修复**：`chatSlice.ts` L295 `logger.error` → `console.error`（logger 未 import 导致静默吞异常）
- **视觉整容**：
  - 行内 `code` 严格区分 inline/block，玫瑰色系防止膨胀为代码块
  - `.blinking-cursor` 黑色方块 → 蓝色 `border-left` 竖线闪烁
  - 表格：外框圆角、th 浅灰背景、td 充足内边距

### SSE 工具感知 — 极客化加载卡片（2026-06-04）
- `MarkdownRenderer` 新增 `plugin` prop，`App.tsx` 传递 `m.plugin`
- 新增 `PluginToolCard` 组件：
  - 后端 SSE 推送 `custom_type: 'plugin_state'` → `chatSlice` 写入 `message.plugin`
  - Running 状态：蓝色呼吸灯进度条 + `Loader2 animate-spin` + "🔍 正在穿透检索：{工具中文名}..."
  - Done 状态：绿色完成标记 + "✓ {工具名} 完成"
  - 内置 15+ 工具名中英文映射表（`TOOL_LABELS`）
  - 空内容 + tool running：气泡内直接显示 `PluginToolCard`，不裸显"正在思考..."
- 约束：纯前端改动，**零后端/零 Python 修改**

### 杰尼龟 SOP（2026-06-04）
- 动刀前检查关联测试（E2E / MCP 全量 / SVN Diff）
- 完成后给出 git commit 命令块
- 重大修改后直接更新本 `MEMORY.md` 文件

### 交互体验增强 — 平滑滚动 + 键盘人体工学（2026-06-04 下午）
- `App.tsx`：
  - 滚动锚点重构：`scrollToBottom()` 包裹 `requestAnimationFrame`，解决流式输出中 DOM 未落位时跳底失败
  - `isComposing` 防护：中文输入法拼音态回车不再误触发发送
  - `Shift+Enter`：显式保留 textarea 原生换行
  - 发送后自动聚焦：`inputRef.current?.focus()`，允许高频连击提问
  - 用户手动上滚时暂停自动跟底（`userScrolledUp` 状态，阈值 80px）

### 滚动机制微创手术 — 瞬间闪现 + 平滑跟底（2026-06-04 傍晚）
- `scrollToBottom(isInstant?)`：接受可选参数，`true` 时用 `behavior: 'auto'` 瞬间闪现，否则平滑动画
- `isInitialMount` ref：首次加载消息列表时走瞬间闪现，避免从顶部漫长的 `smooth` 滑行
- 新增 `useEffect([activeSessionId])`：切换左侧会话时强制 `scrollToBottom(true)` 瞬间闪现到底部
- 流式输出保持平滑跟底（`behavior: 'smooth'`）
- 体验对比：刷新页面/切会话 → 瞬间到消息末尾（≈0ms）；流式输出 → 平滑跟底（≈300ms）

### 周报 + Admin 模型（2026-06-04 计划落地）
- **多项目截止时间字段**：`prompt_manager.resolve_deadline_field` — 配置 `JIRA_DEADLINE_FIELD_BY_PROJECT` > `PROJECT_SCHEMA_MAP` > `/field` 发现（End date / 结束时间）> `duedate`
- **周报 VIP**：`parse_date_range_from_text` + `build_weekly_report_jql`；表格含动态截止列；prompt 强制写明字段+JQL+区间
- **Admin**：`DEEPSEEK_MODEL` 下拉 + 刷新 `/v1/admin/models`；Jira 卡片 JSON 映射截止时间字段

### 已知技术债
- **`归档/research/Claw/test_all_mcp_tools.py`**：Jira PAT token (`NDAxMTQxMjkzNTgxOuZ...`) 和 SVN 密码 (`123456`) 在脚本第 9-12 行硬编码为明文字符串，需迁移到环境变量或 `.env` 文件（优先级 P1，涉及凭据安全）
- **`backend/ai_bridge.py`**：3000+ 行单体文件，路由/VIP 直通车/ReAct 循环/工具执行器混在同一文件，建议拆分为独立模块（优先级 P2）
- **`backend/jira_api.py` L64, L103**：cookie domain `ctjira1.lmdgame.com` 硬编码，换 Jira 实例需修改 2 处
- **E2E ReAct 步数超标**：`max_steps=5` 当前默认值，LLM 会反复查询同一任务，建议调整为 `max_steps=3`（`ai_bridge.py` generate_stream 内 `max_steps = frontend_cfg.get("max_steps", 5)`）

### 测试武器库速查
| 脚本 | 用途 | 何时跑 |
|------|------|--------|
| `python test/e2e_v2.py` | Alice 端到端 3 题回归 | 改 `ai_bridge.py`/`intent_router.py` |
| `python 归档/research/Claw/test_all_mcp_tools.py` | MCP 8 工具全量压测 | 改 `jira_mcp_server.py`/`jira_api.py` |
| `python 归档/research/Claw/test_jira_diff.py` | SVN Diff 验证 | 改 SVN diff 相关 |
| `python 归档/research/Claw/net_diag.py` | 6 节点网络存活 | 环境出问题时 |
