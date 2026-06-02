# Alice V2.0 诊断简报 — 供 Gemini 分析

## 问题现象

用户问："CT-10888 最近1天的代码提交有什么内容"

**期望答案**：r40538 袁伟伟 06-02 +67/-1 + r40415 魏诗豪 06-01 +369/-0（CT-10888 确实有 SVN 提交）

**Alice 实际回答**："没有任何代码提交记录"（反复出现，即使后端数据正确）

## 系统架构（极简版）

```
用户 → Web UI → Vite Proxy(:5174) → Flask/Waitress(:9099) → ReAct Loop → DeepSeek V4 Pro
                                          ↑
                                    Intent Router (Python regex)
                                    ↓
                              5 atomic tools ← Jira/SVN/Notion/GDrive
```

## ReAct 循环流程

```
1. Intent Router 根据用户意图预选工具子集
2. Probe: LLM + filtered_tools (非流式) → 决定调哪些工具
3. Execute: Python 执行工具 (get_issue_commits → FishEye + SVN CLI)
4. Tool results → 追加到 messages
5. 重复 2-4 直到 LLM 决定回答
6. Final: 流式 SSE 输出 (无 tools，纯文本模式)
```

## 关键文件（只有这些相关）

| 文件 | 作用 | 行数 |
|------|------|:--:|
| `ai-bridge/ai_bridge.py` | 主入口，ReAct 循环，工具执行，CORE_SYSTEM_PROMPT_V2 | 1700+ |
| `ai-bridge/intent_router.py` | 意图路由层，匹配问法→工具子集 | 100 |
| `ai-bridge/tools/registry.yaml` | 5个工具的 JSON Schema | 100 |
| `ai-bridge/knowledge_retriever.py` | SVN/FishEye 实际数据拉取 | ~300 |

## 已验证的事实

1. `_exec_get_issue_commits('CT-10888')` 返回 5466 字，包含 r40538/r40415 ✅
2. `route_intent('代码提交')` 正确匹配 CODE_COMMIT 模式 → [get_issue_commits, query_jira_metadata] ✅
3. curl 直测 9099 端口：SSE 显示 get_issue_commits 被调用 ✅
4. 最终流式回答阶段偶尔出现 `<|tool_calls|>` 文本泄漏 ✅（已加 system message 修复）
5. 但用户通过浏览器 (5174) 仍看到 "没有任何提交记录" ❌

## 已尝试的修复

1. Intent Router: 让 LLM 看不到任务状态，直接给 get_issue_commits
2. Bigram JQL: 中文搜索从 `text~` 改为 `summary~` OR 分解
3. 空值占位符: 工具返回空时注入【禁止编造】信号
4. 最终流式 system message: "工具已完成，输出纯文本"
5. 跨工具关联检索 prompt: 读文档→抽特征→搜Jira

## 当前怀疑方向

A. **多轮对话污染**：Alice 在第一轮答错后，后续轮次被自己的错误回答影响
B. **浏览器缓存**：Web UI 缓存了旧的 SSE 响应
C. **tool_calls 泄漏未完全修复**：流式回答中仍有标记文本，用户只看到前半段

## 请 Gemini 帮助诊断

这个 Agent 的后端数据是正确的——FishEye 返回了真实的 SVN 提交记录（r40538 袁伟伟、r40415 魏诗豪），Intent Router 也正确选择了 get_issue_commits 工具，工具被执行并返回了 5466 字的真实数据。但 DeepSeek V4 Pro 模型在最终回答阶段，仍然告诉用户"没有任何代码提交记录"。最可能的根因是什么？如何在不打破 LlamaIndex 架构的前提下修复？
