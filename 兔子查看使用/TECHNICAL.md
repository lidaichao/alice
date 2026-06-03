# Alice AI Bridge — 技术架构文档

> 版本：v2.0 | 日期：2026-06-03 | 分支：master

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
│  │ diff意图     │  │ doc意图      │                 │
│  │ (r\d+ +diff) │  │ (notion/wiki) │                │
│  │    ↓         │  │    ↓         │                 │
│  │ VIP Diff     │  │ VIP Catalog  │                 │
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

### 3.2 knowledge_retriever.py — 知识检索

| 函数 | 职责 |
|------|------|
| `get_single_commit_diff(revision_id)` | SVN CLI 直拉单次提交 diff，语义裁剪去冗余 |
| `extract_dynamic_keywords(user_text, issue_key)` | DynamicContextResolver：Jira → user_text → issue_key 三级动态提取，零硬编码 |
| `fetch_precise_commits_via_fisheye(issue_key)` | FishEye 双跳精确检索提交列表 |
| `safe_get_commits(issue_key)` | 带 TTL 缓存 + 超时熔断的提交获取 |

### 3.3 intent_router.py — 意图路由

| 意图 | 正则 | 分配工具 |
|------|------|---------|
| `CODE_COMMIT_LIST` | 提交/commit/提交记录 | get_issue_commits + query_jira_metadata |
| `CODE_COMMIT_DIFF` | diff/分析代码/审查 | get_single_commit_diff + search_docs_catalog + read_specific_doc |
| `JIRA_QUERY` | 查/看/状态/谁/负责人 | query_jira_metadata + search_jira_issues |
| `KNOWLEDGE` | 文档/设计案/wiki | search_docs_catalog + read_specific_doc |

### 3.4 tools/registry.yaml — 工具注册表（6 原子工具）

| 工具 | 类型 | 说明 |
|------|------|------|
| `query_jira_metadata` | Jira | 获取任务元数据 |
| `get_issue_commits` | SVN | 获取提交列表（不含 diff） |
| `get_single_commit_diff` | SVN | 获取指定版本 Diff |
| `search_docs_catalog` | 知识库 | Notion/GDrive 目录检索 |
| `read_specific_doc` | 知识库 | 按 ID 读取文档全文 ⚠️ 禁止用于代码文件 |
| `search_jira_issues` | Jira | 关键词搜索任务 |

---

## 四、架构铁律 (2026-06-03)

1. **VIP 直通车 > ReAct 循环**：diff/文档查询走 Python Pre-flight RAG + LLM 纯流式 (无 tools, temp=0.1)
2. **硬编码 = 死罪**：所有关键词必须通过 DynamicContextResolver 动态提取
3. **deepseek-v4-flash 能力边界**：不支持标准 tools 参数，输出 DSML 文本代替 function calling
4. **核选项 N+V2**：ReAct 循环中的表决机制，列表查询直接出表格，跳过被污染的 Final Stream LLM
5. **反幻觉溯源**：所有 LLM 入参必须包含真实文档标题 + 防编造强制指令

---

## 五、数据流（VIP Diff 直通车示例）

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

## 六、项目结构

```
H:\workbuddy\alice\
├── ai-bridge/                # Python AI 引擎
│   ├── ai_bridge.py          # 核心服务 (VIP 入口 + ReAct 循环)
│   ├── knowledge_retriever.py # 知识检索 (SVN/Notion/动态关键词)
│   ├── intent_router.py      # 意图路由
│   ├── jira_mcp_server.py    # MCP 工具服务
│   ├── tools/
│   │   └── registry.yaml     # 6 原子工具注册表
│   ├── tests/
│   │   └── test_vip_pipeline.py  # VIP 离线测试 (2/2 PASS)
│   └── logs/
│       └── alice_bridge.log   # 持久化日志 (10MB×5)
│
├── src/                      # React 前端
│   ├── App.tsx               # 主界面 (含错误气泡)
│   ├── MobileApp.tsx         # 移动端适配
│   └── store/slices/chatSlice.ts  # SSE 流处理 + 异常兜底
│
├── desktop/                  # Electron 桌面壳
│   ├── main.js               # 主进程
│   ├── preload.js            # IPC 安全桥
│   └── bridge-manager.js     # Python 子进程管理
│
├── docs/ → 兔子查看使用/     # 设计文档
└── global_config.json.example  # 配置模板
```

---

## 七、测试

| 模块 | 用例 | 结果 |
|------|------|------|
| intent_classifier.py | 20/20 | 100% |
| jira_operation_manager.py | 11/11 | 100% |
| audit_gateway.py | 9/9 | 100% |
| test_vip_pipeline.py | 2/2 | 100% |
| T1 列表查询 (回归) | 1.4s, 526 chars | ✅ |
| T2 Diff 分析 (回归) | 15.3s, 2209 chars | ✅ |

---

## 八、关键设计决策

| 决策 | 原因 |
|------|------|
| deepseek-v4-flash 不走 ReAct | 该模型不支持标准 tools 参数，输出 DSML 文本 |
| Diff 用 Python 全检索 | 避免 LLM 在工具链末端崩溃 (重复搜索/不读文档) |
| Nuclear V2 绕过 Final Stream | LLM 在最后一步仍然输出 tool_calls 文本，需直接输出工具数据 |
| RotatingFileHandler 持久化 | 10MB×5 滚动日志，格式含 filename:lineno 便于追踪 |
