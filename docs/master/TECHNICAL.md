# Alice AI Bridge — 技术架构文档

> 版本：v2.1 | 日期：2026-06-04 | 分支：master

**相关文档**：[Master 架构 V2.2](Alice_Master_Architecture_v1.0.md) · [白泽 Baize 架构（上游参考）](Baize_Architecture_v1.0.md) · [桌面端方案](desktop_app_plan.md)

---

## 一、技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 桌面框架 | Electron 28 | 跨平台桌面壳 |
| 后端引擎 | Python Flask + Waitress 10-thread | AI 服务 + 数据检索 (:9099) |
| AI 模型 | DeepSeek V4 Flash (主) / V3 | 对话 + 分析 |
| 前端 | React 19 + TypeScript + Vite | 现代 SPA UI |
| 状态管理 | Zustand | 前端状态 |
| 持久化 | Dexie (IndexedDB) | 会话/配置本地存储 |
| 安全 | IntentRouter + Nuclear V2 + AuditGateway | 自研多层防护 |

---

## 二、系统架构（Alice V2.0 VIP Express）

```
用户请求
  │
  ▼
┌─────────────────────────────────────────────────────┐
│              VIP 预检入口 (generate_stream)           │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │ diff意图     │  │ doc意图      │  weekly意图    │
│  │ (r\d+ +diff) │  │ (notion/wiki) │ (周报/日报)  │
│  │    ↓         │  │    ↓         │    ↓          │
│  │ VIP Diff     │  │ VIP Catalog  │ VIP Weekly   │
│  │ 直通车       │  │ 直通车       │                 │
│  │             │  │             │                 │
│  │ Python层全检索:            │                     │
│  │ 1.SVN diff   │  │ 1.关键词提取 │                │
│  │ 2.动态关键词 │  │ 2.Notion搜索 │                │
│  │ 3.Notion搜索 │  │ 3.格式化输出 │                │
│  │ 4.文档读取   │  │    ↓         │                 │
│  │    ↓         │  │ LLM stream   │                 │
│  │ LLM stream   │  │ (tools=∅)    │                │
│  │ (tools=∅)    │  └──────────────┘                 │
│  └──────────────┘                                   │
│                                                     │
│         其他意图 → ReAct 循环                        │
│         ┌──────────────────────────┐                │
│         │ L0: IntentRouter         │                │
│         │ L1: 工具并发检索         │                │
│         │ L2: 深度检索             │                │
│         │ Nuclear V2 核拦截        │                │
│         │ Final Stream LLM         │                │
│         └──────────────────────────┘                │
└─────────────────────────────────────────────────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    │ Jira    │ SVN/     │ Notion   │ Google
    │ REST    │ FishEye  │ API      │ Drive
    └─────────┴──────────┴──────────┴──────────┘
```

---

## 三、核心模块

### 3.1 ai_bridge.py — 主引擎

| 组件 | 职责 |
|------|------|
| VIP Diff 直通车 | 检测 diff 意图 → Python 全检索 → LLM 纯分析 (绕过 ReAct) |
| VIP Catalog 直通车 | 检测文档意图 → Python 检索 Notion/GDrive → 格式化 → LLM 输出 |
| ReAct 循环 | 通用意图的 5 轮 max 工具调用循环 |
| Nuclear V2 | ReAct 退出后的最终防线：列表查询强制输出表格 |
| Final Stream 安全网 | LLM 输出全过滤时回退到工具数据 |
| VIP 周报直通车 | 周报/日报意图 → 动态 End date 字段 + 日期区间 JQL → 表格 → LLM 写 PM 周报 |
| `parse_user_config` | 默认模型：`user_config.ai_model` > 请求 config > `global_config.DEEPSEEK_MODEL` > 环境变量 |

### 3.2 prompt_manager.py — 周报与截止时间字段

| 组件 | 职责 |
|------|------|
| `resolve_deadline_field` | 项目 → 截止时间字段（配置映射 → schema → `/field` 发现 → `duedate`） |
| `parse_date_range_from_text` | 从用户话术解析日期区间（如 6/1–6/5） |
| `build_weekly_report_jql` | 按动态字段 + 区间生成 JQL |
| `JIRA_DEADLINE_FIELD_BY_PROJECT` | Admin 可配置 JSON 覆盖（如 CT → End date） |

### 3.3 knowledge_retriever.py — 知识检索

| 函数 | 职责 |
|------|------|
| `get_single_commit_diff(revision_id)` | SVN CLI 直拉单次提交 diff，语义裁剪去冗余 |
| `extract_dynamic_keywords(user_text, issue_key)` | DynamicContextResolver：Jira → user_text → issue_key 三级动态提取，零硬编码 |
| `fetch_precise_commits_via_fisheye(issue_key)` | FishEye 双跳精确检索提交列表 |
| `safe_get_commits(issue_key)` | 带 TTL 缓存 + 超时熔断的提交获取 |

### 3.4 intent_router.py — 意图路由

| 意图 | 正则 | 分配工具 |
|------|------|---------|
| `CODE_COMMIT_LIST` | 提交/commit/提交记录 | get_issue_commits + query_jira_metadata |
| `CODE_COMMIT_DIFF` | diff/分析代码/审查 | get_single_commit_diff + search_docs_catalog + read_specific_doc |
| `JIRA_QUERY` | 查/看/状态/谁/负责人 | query_jira_metadata + search_jira_issues |
| `KNOWLEDGE` | 文档/设计案/wiki | search_docs_catalog + read_specific_doc |

### 3.5 tools/registry.yaml — 工具注册表（6 原子工具）

| 工具 | 类型 | 说明 |
|------|------|------|
| `query_jira_metadata` | Jira | 获取任务元数据 |
| `get_issue_commits` | SVN | 获取提交列表（不含 diff） |
| `get_single_commit_diff` | SVN | 获取指定版本 Diff |
| `search_docs_catalog` | 知识库 | Notion/GDrive 目录检索 |
| `read_specific_doc` | 知识库 | 按 ID 读取文档全文 ⚠️ 禁止用于代码文件 |
| `search_jira_issues` | Jira | 关键词搜索任务 |

---

## 四、Admin 管理后台（`backend/admin.html`）

| 能力 | 说明 |
|------|------|
| API 配置 | 「编辑 API 配置」仅改 `DEEPSEEK_URL` / `DEEPSEEK_KEY`，保存后热重载 |
| 默认模型 | 下拉切换即 POST `{ DEEPSEEK_MODEL }`（Cursor 式），全局默认对话模型 |
| 模型列表 | `GET /v1/admin/models` 从上游 `/models` 拉取；已保存但不在列表的 id 仍会显示 |
| 加载守卫 | `hydratingModel` 防止 F5 刷新时 `<select @change>` 误把 `deepseek-chat` 写回磁盘 |
| 读模型 | 后端 `_resolved_deepseek_model()`：`global_config.json` 优先于环境变量 |

持久化文件：`backend/global_config.json`（含 `DEEPSEEK_MODEL`、`JIRA_DEADLINE_FIELD_BY_PROJECT` 等）。

---

## 五、架构铁律 (2026-06-04)

1. **VIP 直通车 > ReAct 循环**：diff/文档查询走 Python Pre-flight RAG + LLM 纯流式 (无 tools, temp=0.1)
2. **硬编码 = 死罪**：所有关键词必须通过 DynamicContextResolver 动态提取
3. **deepseek-v4-flash 能力边界**：不支持标准 tools 参数，输出 DSML 文本代替 function calling
4. **核选项 N+V2**：ReAct 循环中的表决机制，列表查询直接出表格，跳过被污染的 Final Stream LLM
5. **反幻觉溯源**：所有 LLM 入参必须包含真实文档标题 + 防编造强制指令

---

## 六、数据流（VIP Diff 直通车示例）

```
[用户] "帮我分析一下 r40538 的代码 diff"
    │
    ▼
[VIP 预检] _diff_rev="40538" + _diff_intent=True
    │
    ├── Hop 1: get_single_commit_diff("40538") → SVN CLI → raw_diff (3KB)
    ├── Hop 2: extract_dynamic_keywords() → Jira API → "新增-阵型养成"
    ├── Hop 3: _exec_search_docs_catalog("阵型养成") → Notion → catalog
    ├── Hop 4: _exec_read_specific_doc(first doc) → doc_content (2KB)
    │
    ▼
[final_prompt]
    【业务背景】（来自 NOTION 文档《战术系统设计案》）：...
    【代码 Diff】：...
    【防幻觉指令】：如实回答来源于上述文档
    │
    ▼
[LLM stream] tools=∅, temperature=0.1
    │ 不经过 ReAct，直接流式输出 Code Review
    ▼
[用户] 看到 2000+ chars 专业分析
```

---

## 七、项目结构

```
H:\workbuddy\alice\
├── backend/                  # Python AI 引擎
│   ├── ai_bridge.py          # Flask 主服务 + Admin API
│   ├── admin.html            # Web 管理后台（Vue CDN）
│   ├── global_config.json    # 全局配置（模型、Jira、Key 等）
│   ├── prompt_manager.py     # 周报 JQL / 截止时间字段解析
│   ├── intent_router.py      # 意图路由（含周报）
│   └── tools/registry.yaml   # 6 原子工具
├── frontend/                 # React 19 + Vite
│   └── src/store/slices/chatSlice.ts
├── desktop/                  # Electron 桌面壳
├── docs/master/              # 主文档（本目录）
└── eval/                     # 评测流水线
```

---

## 八、测试

| 模块 | 用例 | 结果 |
|------|------|------|
| intent_classifier.py | 20/20 | 100% |
| jira_operation_manager.py | 11/11 | 100% |
| audit_gateway.py | 9/9 | 100% |
| test_vip_pipeline.py | 2/2 | 100% |
| T1 列表查询 (回归) | 1.4s, 526 chars | ✅ |
| T2 Diff 分析 (回归) | 15.3s, 2209 chars | ✅ |

---

## 九、关键设计决策

| 决策 | 原因 |
|------|------|
| deepseek-v4-flash 不走 ReAct | 该模型不支持标准 tools 参数，输出 DSML 文本 |
| Diff 用 Python 全检索 | 避免 LLM 在工具链末端崩溃 (重复搜索/不读文档) |
| Nuclear V2 绕过 Final Stream | LLM 在最后一步仍然输出 tool_calls 文本，需直接输出工具数据 |
| RotatingFileHandler 持久化 | 10MB×5 滚动日志，格式含 filename:lineno 便于追踪 |
