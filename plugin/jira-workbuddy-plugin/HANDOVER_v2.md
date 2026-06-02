# Jira AI 插件开发工作交接 — 完整状态

> 生成时间：2026-05-26 18:23
> 当前版本：AI Bridge v4 (L1/L2 layered)
> 项目根目录：`H:\workbuddy\jira\`

---

## 一、项目全局概览

### 1.1 项目目标

在 Jira Server 9.12.5（内网 `ctjira1.lmdgame.com:8080`）中嵌入一个 AI 对话助手，用户在任何 Issue 页面右下角打开聊天面板，直接与 DeepSeek 大模型对话。AI 能**自动收集**该 Issue 的 Jira 字段、SVN 代码提交、Notion 策划文档、Google Drive 需求文档，综合分析后给出智能回答。回答可一键贴为 Jira 评论，支持多角色切换（不同 system prompt）。

### 1.2 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| **后端** | Python 3.13.12 + Flask | AI Bridge 核心服务（端口 9099） |
| **MCP** | FastMCP | Jira/SVN 工具注册（8 个工具） |
| **AI** | DeepSeek API (deepseek-chat) | 大模型推理引擎 |
| **前端** | HTML/CSS/JS（公告横幅注入） | Jira 内嵌聊天面板 |
| **插件框架** | Jira Server Plugin (Java, spring-scanner) | 目标：正式插件化部署 |
| **构建** | Maven 3.9.9 + JDK 11 | 仅插件编译（尚未成功编译） |
| **代理** | Clash Verge (端口 7897) | Google Drive 访问 |

### 1.3 数据源

| 数据源 | 地址 | 认证方式 | 状态 |
|--------|------|---------|------|
| Jira Server 9.12.5 | `http://ctjira1.lmdgame.com:8080` | PAT Token (永久) | ✅ 稳定 |
| SVN (via FishEye) | `http://192.168.8.34:8060` / `https://192.168.8.162/svn/...` | 用户名/密码 | ✅ 稳定 |
| Notion | `api.notion.com` | API Key (ntn_...) | ✅ 稳定 |
| Google Drive | `www.googleapis.com` | API Key (AIza...) + Clash 代理 | ✅ 稳定 |
| DeepSeek | `api.deepseek.com` | API Key (sk-...) | ✅ 直连 |
| 企业微信 | MCP Bridge (端口 9090) | Token + AES Key | ⚠️ 未完成 |

---

## 二、文件清单与职责

```
H:/workbuddy/jira/
├── HANDOVER.md                           — 前任 AI 的交接文档                   [只读参考]
│
├── wecom-jira-bridge/                    — 🔥 核心服务（当前开发主战场）
│   ├── ai_bridge.py            (528行)  — Flask AI 桥接 v4 L1/L2 分层检索      [完成度: 95%] ✅ 生产可用
│   ├── jira_api.py             (251行)  — Jira REST API 封装 + SVN/FishEye      [完成度: 90%] ✅ 稳定
│   ├── jira_mcp_server.py      (382行)  — 8 个 MCP 工具注册 (FastMCP)          [完成度: 85%] ✅ 稳定
│   ├── server.py               (332行)  — 企业微信消息回调服务器                [完成度: 30%] ⚠️ 未完成
│   ├── wecom_crypto.py         (191行)  — 企业微信消息加密/解密                 [完成度: 80%] ⚠️ 未联调
│   ├── .env                              — 环境变量（含密钥）                    [配置]
│   ├── GROOVY_SCRIPT.md                  — Jira 插件 Groovy 集成脚本             [已废弃] 
│   ├── jira_chat_banner.html             — 公告横幅注入版聊天面板 (旧版)         [已废弃]
│   ├── jira_chat_tampermonkey.user.js    — Tampermonkey 版注入脚本               [已废弃]
│   ├── ai_bridge_v2.py         (162行)   — v2 文件队列版（尝试失败）             [已废弃]
│   └── test_l1l2.py            (33行)    — L1/L2 自测脚本                       [工具]
│
├── jira-workbuddy-plugin/                — 正式 Jira 插件工程（Java）
│   ├── pom.xml                           — Maven 构建配置 (spring-scanner)       [开发中]
│   ├── prototype.html                    — 配置页原型 (已对齐)                   [原型]
│   ├── test_suite.html         (827行)   — 🔥 本地全功能验证套件                 [完成度: 90%] ✅ 可用
│   ├── 产品优化需求文档.md                — 14 条优化需求清单                     [文档]
│   └── src/main/
│       ├── resources/
│       │   ├── atlassian-plugin.xml      — 插件描述 (web-panel + REST)           [开发中]
│       │   ├── templates/admin.vm        — 配置页 Velocity 模板                  [开发中]
│       │   ├── templates/chat-panel.vm   — 聊天面板模板                         [开发中]
│       │   ├── css/chat.css              — 聊天面板样式                         [开发中]
│       │   └── js/chat.js                — 聊天面板脚本                         [开发中]
│       └── java/com/lmd/workbuddy/
│           ├── AdminServlet.java         — 配置页后端 (读 PluginSettings)        [开发中]
│           ├── ChatEndpoint.java         — REST /rest/wb/chat                   [开发中]
│           └── ConfigService.java        — PluginSettings 读写封装              [开发中]
```

**状态图例**：✅ 稳定可运行 | 🔥 当前开发重点 | ⚠️ 未完成 | [已废弃] 不再使用

---

## 三、已完成功能清单

| 功能 | 入口 | 已测试 | 备注 |
|------|------|--------|------|
| Jira PAT 连接测试 | `jira.test_connection()` | ✅ | |
| 列出所有项目 | `jira_list_projects()` | ✅ | 足球小将 (CT) |
| JQL 自定义搜索 | `jira_search(jql)` | ✅ | 支持中文状态名 |
| 我的未完成 Issue | `jira_my_open_issues()` | ✅ | |
| 本周未完成 Issue | `jira_this_week_issues()` | ✅ | |
| 单 Issue 详情 | `jira_get_issue(key)` | ✅ | |
| Issue 关联 SVN 提交 | `jira_get_commits(key)` | ✅ | 通过 FishEye REST API |
| 完整 SVN Diff | `jira_get_svn_diff(key, revision)` | ✅ | |
| Jira 聊天面板注入 | `jira_chat_banner.html` → Jira 公告横幅 | ✅ | 已在生产 Jira 使用 |
| AI 对话 (DeepSeek) | `POST /v1/chat/completions` | ✅ | |
| 角色提示词系统 | `test_suite.html` 角色配置 | ✅ | 支持提示词+知识库开关 |
| 快捷提问按钮 | 4 个预设问题 | ✅ | 提交摘要/风险分析/需求对照/进度评估 |
| 对话历史持久化 | localStorage | ✅ | 刷新不丢失 |
| AI 回复贴为评论 | `POST /proxy/jira/comment` | ✅ | 格式：*🤔 提问* / *🤖 AI 答复* |
| Notion 文档检索 | L1 标题 + L2 内容 | ✅ | JIRA-key 匹配 + 关键词搜索 |
| GDrive 文件检索 | L1 文件名 + L2 表格内容 | ✅ | 关键词匹配 + Sheets A1:G30 |
| L1/L2 分层检索 | `collect_context()` | ✅ | 4 线程并行 L1 + 启发式决策 |
| 上下文缓存 | `_CONTEXT_CACHE` (5min TTL) | ✅ | 同 Issue 二次查询提速 1.6x |
| 配置保存/加载 | localStorage + 格式校验 | ✅ | |
| 代理配置 | IP + 端口 → 自动拼接 | ✅ | 仅 GDrive 走代理 |
| DeepSeek 模型列表拉取 | `GET /proxy/ai/models` | ✅ | 动态获取不硬编码 |
| Notion 数据库自动检测 | `GET /proxy/notion/search` | ✅ | 填 Key 自动搜索 |

---

## 四、进行中 / 未完成功能

| 功能 | 当前进度 | 阻塞原因 | 剩余工作 |
|------|---------|---------|---------|
| **正式 Jira 插件编译** | pom.xml+Java 源码已完成 | 无法访问 Atlassian Maven 仓库（本机无 VPN 到外网） | 需在 Jira 服务器上编译 `mvn package` |
| **企业微信集成** | server.py 已写回调框架 | 未联调测试 | 需企业微信后台配置回调 URL |
| **SSE 流式输出** | 未开始 | DeepSeek 支持 stream=true | 改造 `/v1/chat/completions` → SSE |
| **Jira Issue 评论读取** | 未开始 | | 调 `GET /issue/{key}/comment` |
| **版本/冲刺查询** | 未开始 | | 需 Jira Agile API |
| **多 Issue 对比** | 未开始 | | 多 Key 并行查询 |
| **配置表变更识别** | 未开始 | | 标记 Excel/JSON/CSV 文件改动 |
| **插件部署服务化** | 未开始 | | systemd/Windows Service |

---

## 五、关键代码段 / 核心逻辑说明

### 5.1 Jira API 认证 (`jira_api.py`)

```python
class JiraClient:
    def __init__(self, base_url, email="", password="", session_cookie=None, pat_token=None):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/rest/api/2"
        self.session = requests.Session()
        
        # 优先级: PAT > Session Cookie > Basic Auth
        if pat_token:
            self.session.headers["Authorization"] = f"Bearer {pat_token}"
        elif session_cookie:
            self.session.cookies.set("JSESSIONID", session_cookie.strip('"'))
        elif email and password:
            self.session.auth = (email, password)
        
        self.session.headers["Content-Type"] = "application/json"
```

**说明**：PAT 永久有效，优先级最高。Cookie 48h 过期已废弃不用。

### 5.2 L1/L2 分层检索 (`ai_bridge.py:collect_context()`)

```python
# ═══ L1: 并行轻量拉取 (4线程) ═══
with ThreadPoolExecutor(max_workers=4) as ex:
    jobs = {
        ex.submit(_jira_l1):   "jira",     # 标题+状态+描述(300字)
        ex.submit(_svn_l1):    "svn",      # 提交前600字
        ex.submit(_notion_l1): "notion",   # 文档标题列表
        ex.submit(_gdrive_l1): "gdrive",   # 文件名列表
    }
    for f in as_completed(jobs):
        parts.append(f.result())

# ═══ 决策: L2 是否需要？ (<1ms, 无 LLM 调用) ═══
need_svn    = svn_len > 600 and not is_light
need_notion = notion_count > 0 and not is_light and has_doc_keywords(q)
need_gdrive = gdrive_count > 0 and not is_light and has_doc_keywords(q)
# Deep → 全部补 L2；Light → 全跳；存疑 → 保守补 L2

# ═══ L2: 精准补给 ═══
if need_svn:    # 补全提交详情 (2500字)
if need_notion: # 读页面段落内容
if need_gdrive: # 读 GSheets A1:G30
```

**决策规则**（纯启发式，不调 LLM）：
- `is_light` = 用户用了 "简单/摘要/概括/概况" 等词 → L1 only
- `is_deep`  = 用户用了 "详细/全面/审查/深度" 等词 → L1+L2 全量
- `has_doc_keywords` = 用户提到 "需求/文档/内容/设计/策划" → 补 Notion/GDrive
- **保守兜底**：不确定时走深不走浅

### 5.3 DeepSeek 调用 (`ai_bridge.py:chat_completions()`)

```python
system_content = frontend_system  # 保留角色提示词
system_content += f"\n\n## 上下文数据\n{jira_context}"

deepseek_messages = [
    {"role": "system", "content": system_content},
    {"role": "user", "content": user_message}
]

r = http.post(
    "https://api.deepseek.com/v1/chat/completions",
    headers={"Authorization": f"Bearer {config['deepseek_key']}", "Content-Type": "application/json"},
    json={"model": "deepseek-chat", "messages": deepseek_messages, "max_tokens": 2000, "temperature": 0.7},
    timeout=60
)
reply = r.json()["choices"][0]["message"]["content"]
```

**说明**：角色提示词不做覆盖，前端传什么就用什么。上下文以注释形式追加到 system prompt 尾部。

### 5.4 SVN 提交查询 (`jira_mcp_server.py:jira_get_commits()`)

```python
@mcp.tool()
def jira_get_commits(issue_key: str) -> str:
    # 1. 从 Jira 获取 dev-status (含 FishEye 提交列表)
    r = jira.session.get(f"{jira.api_url}/issue/{issue_key}?fields=summary")
    # 2. 调 FishEye REST API: /rest-service-fe/revision-info-v1/issue/{key}
    fisheye_url = f"{os.getenv('FISHEYE_URL','http://192.168.8.34:8060')}/rest-service-fe/revision-info-v1/issue/{issue_key}"
    # 3. 解析每个 revision → 格式化 Markdown
```

### 5.5 本地验证套件 (`test_suite.html`)

827 行单页应用，左侧配置 + 右侧聊天面板，包含：
- 4 个测试按钮（SVN/Notion/GDrive/AI）
- 角色管理系统（创建/编辑/删除）
- 4 个快捷提问按钮
- 对话历史 localStorage
- 终止按钮（AbortController）
- Markdown 渲染 + 复制按钮

---

## 六、配置与环境变量

### 6.1 环境变量清单 (`.env`)

```bash
# === Jira ===
JIRA_BASE_URL=http://ctjira1.lmdgame.com:8080
JIRA_PAT=NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG

# === DeepSeek ===
DEEPSEEK_API_KEY=sk-9879e6d86abf41c18d9148d2d7124d4d

# === 企业微信 (未使用) ===
WECOM_TOKEN=nQGqqnwApNgrQ3bbIoRAp
WECOM_ENCODING_AES_KEY=OFvKlEXx5WOt4vAoYCM1ww0lG72nY1Ni5mVfbh6rxBU
WECOM_CORP_ID=ww8f190d9dbd657ef1
```

### 6.2 外部依赖

```bash
pip install flask requests python-dotenv fastmcp
```

### 6.3 Python 环境

```
Python 3.13.12 (managed)
路径: C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe
项目无独立 venv，直接使用系统 Python
```

### 6.4 硬编码在代码中的密钥（需插件化时迁移到配置页）

| 密钥 | 位置 | 值 |
|------|------|-----|
| Notion API Key | `ai_bridge.py` 内 | `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` |
| Notion DB ID | `ai_bridge.py` 内 | `36662e00-69d9-80d9-9956-000b049aca23` |
| Google API Key | `ai_bridge.py` 内 | `AIzaSyAEDfaeKL4uBrIGEgBHmmG_Hc4TFbMUsUY` |
| GDrive 文件夹1 | `ai_bridge.py` 内 | `1b7JJwDTGRV6EmVUieBOjnFcTXFtbCHiI` |
| GDrive 文件夹2 | `ai_bridge.py` 内 | `1DvBObfmRBd5707Lq_GBADOvfFEazJgrh` |
| Clash 代理 | `ai_bridge.py` 内 | `http://localhost:7897` |
| SVN 账号 | `test_suite.html` 默认值 | `lidaichao / 123456` |

---

## 七、已知问题 / 踩过的坑

1. **Jira API 字段可能为 None**
   - `priority` / `assignee` / `status` 可能为 None → 已加 `if x else` 保护
   - `jira_search()` 的 `result` 可能为 None → 已加 `if not result` 检查

2. **Atlassian Maven 仓库无法访问**
   - 本机无 VPN → 无法 `mvn package`
   - 解决方案：在 Jira 服务器上编译（Jira 自带 Maven + 依赖缓存）

3. **Notion URL 格式不统一**
   - 支持 `wiki-xxx` 和 `xxxxxxxx-xxxx-...-xxxx` 两种格式
   - 自动提取 32 位 hex

4. **Google Drive 直连超时**
   - 必须走 Clash Verge 代理 (端口 7897)
   - 仅 GDrive 走代理，Jira/Notion/DeepSeek 直连

5. **Browser `event` 在 async 函数中丢失**
   - `onclick` 中的 `event` 在 async 函数中为 undefined
   - 已改为显式传 `this` + `document.getElementById()`

6. **SVN 提交记录可能跨 Jira Issue 共享**
   - 同一个 SVN revision 关联了多个 Jira Issue
   - Commit 数据会重复出现（暂未去重）

7. **测试套件复制按钮历史问题**
   - `innerHTML +=` 会销毁事件监听 → 改为 `appendChild(createElement)`
   - 已稳定

8. **Quick Actions 位置变更**
   - 最初放在聊天最上方（不直观）→ 移到输入框上方（微信/QQ 风格）

---

## 八、下一步开发计划

### P0 必须完成
1. **正式 Jira 插件编译部署** — 在 Jira 服务器上 `mvn package`，替代公告横幅方案
2. **配置文件外部化** — 所有硬编码密钥迁移到插件配置页

### P1 应该完成
3. **SSE 流式输出** — 改造 DeepSeek 调用为 `stream=true`
4. **对话写回 Jira 评论** — 已有 `/proxy/jira/comment`，需在正式插件中联调
5. **SVN Diff 喂给 AI** — `collect_context` 加入实际代码变更内容

### P2 锦上添花
6. **对话追问上下文** — 前端传最近 2 轮对话
7. **Issue 类型自动映射角色** — 客户端→程序专家，策划→策划分析
8. **读取 Jira 评论** — 补全上下文

---

## 九、快速启动手册

```bash
# 1. 进入项目目录
cd H:/workbuddy/jira/wecom-jira-bridge

# 2. 确认 Python 环境
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe --version
# → Python 3.13.12

# 3. 安装依赖（首次）
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe -m pip install flask requests python-dotenv fastmcp

# 4. 启动 AI Bridge
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe ai_bridge.py
# → 监听 http://localhost:9099

# 5. 验证可用
curl http://localhost:9099/health
# → {"engine":"deepseek-chat","service":"ai-bridge-v4","status":"ok"}

# 6. 打开验证套件
# 浏览器访问: http://localhost:9099/test

# 7. Jira 端使用（依赖已部署的公告横幅）
# 打开任意 Issue 页面，右下角 AI 按钮
```

---

## 十、运行日志 / 测试用例

### 最后一次 L1/L2 自测结果 (18:19)

```
[T1-LIGHT]  5.2s |  19 chars — "简单说下这个任务是什么" → "这是一个开发客户端战斗跑测工具的任务。"
[T2-CACHE]  3.2s |  34 chars — 同一 Issue 缓存命中，1.6x 加速
[T3-DEEP]   8.0s | 1032 chars — "详细分析代码变更涉及哪些模块..." → Markdown 表格+风险分析
[T4-NOTION] 7.8s |  85 chars — CT-10833 "需求文档核心内容" → "设计并实现球员共鸣系统"
```

### 测试命令

```bash
cd H:/workbuddy/jira/wecom-jira-bridge
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe test_l1l2.py
```

### 当前运行状态

```bash
curl -s http://localhost:9099/health | python -m json.tool
# {
#   "engine": "deepseek-chat",
#   "service": "ai-bridge-v4",
#   "status": "ok"
# }
```

---

**文档结束。** 以上 10 章完整覆盖项目当前状态，可据此接替开发。
