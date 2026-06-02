# Alice 知识库智能检索系统 — 架构升级设计计划

> 版本: v1.0 | 日期: 2026-06-02 | 状态: ✅ 已实施

---

## 一、目标

用户向 AI 提问 → AI 自动从 Notion / Google Drive / SVN+FishEye / Jira 四个知识库中获取真实数据 → 基于数据回答，不编造。

---

## 二、理论验证

| 学术/工业方案 | 验证点 | 对应本方案 |
|-------------|--------|-----------|
| **AgentRouter** (arXiv 2510.05445) | 知识图谱引导的多Agent路由器，根据查询特征选择正确的知识源 | S0 Source Router |
| **Plan-and-Execute** (经典范式) | 先规划后执行，每步执行后重规划；探索性任务 S 级表现 | L0→L4 渐进检索 + 步级 Replan |
| **ReWOO** (Reasoning WithOut Observation) | 无依赖任务可并行执行，仅 2 次 LLM 调用 | S1 多源并行搜索 |
| **Google Deep Research** | 多步研究计划 → 多次搜索 → 融合生成报告 | S0 计划 → S1 并行搜 → 汇总 |
| **Anthropic Context Engineering** | Just-in-Time 加载，渐进揭示，不要预装全部数据 | 每层搜完才决定下一层 |
| **LobeHub Brain/Engine 分离** | Agent 输出 Instruction[]，Runtime 执行 | L0 输出搜索指令，Execute Engine 执行 |
| **Baize Jira 经验** | LLM 输出结构化 JSON → Python 组装执行 | 所有层 LLM 决策 → Python 执行 |

**结论：方案可行。** 核心模式（Plan-and-Execute + Source Router + Multi-Source Parallel）有充分的学术和工业验证。

---

## 三、架构总览

```
用户提问
    │
┌───▼─────────────────────────────────────────────┐
│  S0: Source Router (源路由器)                     │
│  输入: 用户问题                                   │
│  LLM 输出: {                                     │
│    "sources": ["jira","svn","notion"],           │
│    "skip": ["gdrive"],                           │
│    "queries": {"jira":"...","notion":"..."},     │
│    "plan": "先查Jira找需求，再查SVN看代码"         │
│  }                                               │
│  LLM调用: 1次                                    │
└───┬─────────────────────────────────────────────┘
    │
┌───▼─────────────────────────────────────────────┐
│  S1: Multi-Source Parallel Search (并行检索)      │
│  ┌─ Notion: search API → [标题+链接]             │
│  ├─ GDrive: list files → [文件名+内容摘要]        │
│  ├─ Jira: JQL搜索 → [Issue摘要列表]              │
│  └─ SVN: log grep → [提交记录]                   │
│  并行执行，Python层，无LLM调用                     │
└───┬─────────────────────────────────────────────┘
    │
┌───▼─────────────────────────────────────────────┐
│  L0: Depth Router (深度路由器)                   │
│  输入: S1各源返回的摘要                           │
│  LLM 输出: {                                     │
│    "deep_read": ["jira:CT-11112","notion:pageX"],│
│    "skip": ["gdrive:文件Y(不相关)"],              │
│    "need_more": true                             │
│  }                                               │
│  LLM调用: 1次                                    │
└───┬─────────────────────────────────────────────┘
    │
┌───▼─────────────────────────────────────────────┐
│  L1-L4: Progressive Depth (逐层深挖)              │
│  L1: Issue详情(元数据) → LLM看 →                  │
│  L2: 关联需求+子任务(关系层) → LLM看 →             │
│  L3: 代码Diff+文档全文(证据层) → LLM看 →           │
│  L4: 全局上下文(深度层)                            │
│  每层1次LLM调用(Replan)                           │
└───┬─────────────────────────────────────────────┘
    │
┌───▼─────────────────────────────────────────────┐
│  Final: Synthesize (汇总生成)                     │
│  LLM: 基于所有已获取的真实数据，生成最终回答        │
│  LLM调用: 1次                                    │
└─────────────────────────────────────────────────┘

总计LLM调用: 3-7次 (相比当前1-5次Agent Loop)
但每层数据精准，不浪费token在无关数据上
```

---

## 四、执行计划 (6个阶段，9个工作日)

### Phase 1: S0 Source Router — 2天

| 任务 | 文件 | 内容 |
|------|------|------|
| 1.1 | `ai_bridge.py` | 新增 `s0_source_router()` 函数：LLM 输出 JSON `{sources, queries, plan}` |
| 1.2 | `ai_bridge.py` | 在 chat_completions 入口处调用 S0，替换当前硬编码 PreFetch |
| 1.3 | `tools/registry.yaml` | 新增 `route_sources` 元工具描述，让 LLM 知道有哪些知识库可用 |
| 1.4 | 测试 | 验证不同问题能正确路由到对应知识库 |

**验收**: 
- "点球玩法怎么设计" → S0 输出 sources=["notion","gdrive"], skip=["jira","svn"]
- "CT-11112 提交了什么" → S0 输出 sources=["jira","svn"], skip=["notion","gdrive"]

### Phase 2: S1 Multi-Source Parallel Search — ✅ 已接入

| 任务 | 文件 | 内容 | 状态 |
|------|------|------|------|
| 2.1 | `ai_bridge.py` | `s1_parallel_search()` → chat_completions 中调用 | ✅ |
| 2.2 | `ai_bridge.py` | 结果注入 tool_messages 为 enriched_msgs | ✅ |

### Phase 3: L0 Depth Router — ✅ 已接入

| 任务 | 文件 | 内容 | 状态 |
|------|------|------|------|
| 3.1 | `ai_bridge.py` | `l0_depth_router()` → chat_completions 中调用 | ✅ |

### Phase 4: L1-L4 Progressive Depth — ✅ 已接入

| 任务 | 文件 | 内容 | 状态 |
|------|------|------|------|
| 4.1 | `ai_bridge.py` | query_jira_issues 14字段扩展 | ✅ |
| 4.2 | `ai_bridge.py` | `l2_relationship_context()` + `l3_evidence_context()` → chat_completions 中调用 | ✅ |

### Phase 5: Final Synthesize — ✅ 已完成

| 任务 | 文件 | 内容 | 状态 |
|------|------|------|------|
| 5.1 | `ai_bridge.py` | 最终回答汇总 | ✅ |
| 5.2 | `ai_bridge.py` | CORE_AGENT_PROMPT 新增规则5：数据溯源 `[SVN:CT-11112]` | ✅ |

### Phase 6: Context Compaction — ⏭ 跳过

---

## 五、文件变更清单

| 文件 | 变更类型 | 预计行数变化 |
|------|---------|-------------|
| `ai_bridge.py` | 重大重构 | +400行 (S0/S1/L0/L1-L4/压缩) |
| `tools/registry.yaml` | 新增描述 | +20行 |
| `test_agent_retrieval.py` | 扩展用例 | +50行 |

不涉及前端修改。

---

## 六、风险与回退

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| LLM 调用次数增加导致延迟 | 高 | S0/L0 用轻量 prompt + 低 temperature；S1 并行无 LLM 调用 |
| 某源返回空结果导致 LLM 误判 | 中 | 空结果显式标注 `"empty": true`，LLM 跳过该源 |
| Token 消耗超过当前方案 | 中 | 每层硬限制返回 token 上限 (L1:200, L2:500, L3:1500, L4:2000) |
| 重构破坏现有功能 | 低 | 新增函数不删除旧代码，先用 feature flag 切换 |

**回退方案**: 保留当前 `execute_tool_call` + Agent Loop 代码不变，新架构作为独立函数并行运行，通过 config 开关切换。

---

## 七、验收标准

| 场景 | 期望行为 |
|------|---------|
| "点球玩法怎么设计" | S0→Notion+GDrive → 基于文档全文回答 |
| "CT-11112 提交了什么" | S0→Jira+SVN → L1详情→L3 Diff → 代码级分析 |
| "赛季系统和属性有关联吗" | S0→Notion+Jira → 跨源综合分析 |
| "Google云盘有哪些文件" | S0→GDrive → S1列表 → 直接回答 |
| "最近谁改了战斗模块" | S0→SVN+Jira → Commits → 作者+文件列表 |

---

## 八、执行顺序

```
Phase 1 (S0) → Phase 2 (S1) → Phase 3 (L0) → Phase 4 (L1-L4) → Phase 5 (Final) → Phase 6 (可选)
```

每个 Phase 独立可测试，不必等全部完成才能验证。
