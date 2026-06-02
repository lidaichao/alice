# Alice V2.0 第二轮诊断报告 — 供 Gemini 分析

## 上一轮修复结果

按 Gemini 建议做了两项修改：
1. **数据瘦身**: `fetch_precise_commits_via_fisheye` 删除 SVN CLI raw diff 拉取，5466字 → 500字元数据表格
2. **流式约束强化**: 最终回答前注入 `"绝对信任 tool 返回值，禁止 '无记录' 等兜底话术"`

## 当前症状（新问题）

用户问："CT-10888 最近的代码提交有什么内容"

| | 期望 | Alice 实际回答 |
|------|------|------|
| 版本号 | **r40538** (袁伟伟) | **r95582** (丁儒) ❌ |
| 范围 | 40274-40538 | r95582 完全不存在于 FishEye |

Alice 编造了 r95582，这个版本号在 FishEye 中根本不存在。

## 已验证的事实

1. FishEye DevStatus API 返回 CT-10888 的真实提交：r40538/r40415/r40414/r40379/r40312... ✅
2. 所有提交在 r40274-r40538 区间，无 r95582 ✅
3. 直接查询 FishEye r95582 → HTTP 401/not found ✅
4. 工具 `get_issue_commits` 返回了正确的元数据表格 ✅
5. SSE 追踪显示 `get_issue_commits` 已被执行 ✅
6. 但最终回答中 LLM 输出了完全不在数据中的 r95582 ❌

## 核心矛盾

**工具返回了正确数据 (r40538)，LLM 却输出了不存在的数据 (r95582)。**

这不是"工具没返回数据所以 LLM 脑补"的问题——工具返回了正确数据。
这是"LLM 收到了正确数据但仍然脑补了错误结果"。

## 当前架构的 ReAct 流程

```
1. Intent Router: '代码提交' → CODE_COMMIT → [get_issue_commits, query_jira_metadata]
2. Probe: DeepSeek + tools → tool_calls: get_issue_commits(CT-10888)
3. Execute: Python 运行工具 → 返回 r40538 元数据
4. Tool result → 追加到 messages: {"role":"tool","content":"r40538 袁伟伟..."}
5. 空值检查: 无空值信号，跳过熔断
6. Final stream: DeepSeek + messages (含正确 tool result) → 输出 "r95582 丁儒"
```

Step 6 中，DeepSeek 收到了包含 r40538 的 tool message，但最终回答却是 r95582。

## 可能根因

A. **LLM 训练数据干扰**: DeepSeek 可能在其他训练数据中见过 "阵型养成" + "r95582" 的关联，回归到训练数据而非当前 tool result

B. **工具返回 JSON 而非纯文本**: 工具返回 `{"status":"ok","llm_text":"r40538..."}` 的 JSON 结构。LLM 看到的 tool content 是 JSON 字符串（含 `"status"`, `"llm_text"` 等键），可能未正确解析 `llm_text` 字段

C. **ReAct 多轮 messages 污染**: messages 数组中可能有旧轮次的残留数据，让 LLM 混淆

D. **流式输出 buffering**: SSE 流式输出的 UTF-8 字节分割可能破坏中文字符

## 请求 Gemini 分析

这个 Agent 的 ReAct 循环中，步骤 3-4 确定工具返回了正确的 r40538 数据，工具返回值以 JSON `{"status":"ok","llm_text":"..."}` 格式追加到 messages 的 tool role 中。但在步骤 6 的最终流式回答中，DeepSeek V4 Pro 输出了完全不在 tool result 中的 r95582。请分析最可能的根因以及如何修复。
