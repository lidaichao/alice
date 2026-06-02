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
