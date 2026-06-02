"""
Alice V2.0 E2E 验证脚本
测试: LlamaIndex 层级检索 + ReAct 并发循环 + 防泄漏
"""
import subprocess, json, re, time, sys

AI_BRIDGE = "http://127.0.0.1:9099"
HEADERS = {"Content-Type": "application/json"}

TEST_CASES = [
    {
        "id": "T1",
        "name": "轻量级查询 — 杀鸡不用牛刀",
        "question": "CT-10852 现在的状态是什么，谁在负责？",
        "checks": {
            "max_steps": 2,
            "must_call": ["query_jira_metadata"],
            "must_not_call": ["search_docs_catalog", "get_issue_commits", "read_specific_doc"],
        }
    },
    {
        "id": "T2",
        "name": "代码精准双跳 — SVN Diff 检索",
        "question": "CT-10852 这个任务改了哪些代码？给我代码的 diff 摘要。",
        "checks": {
            "max_steps": 2,
            "must_call": ["get_issue_commits"],
            "must_not_call": ["search_docs_catalog", "read_specific_doc"],
        }
    },
    {
        "id": "T3",
        "name": "终极Boss — LlamaIndex 层级检索",
        "question": "CT-10852 这个任务，详细说明一下关联的《球员系统属性设计》这份文档的内容。",
        "checks": {
            "min_steps": 2,
            "must_call": ["search_docs_catalog", "read_specific_doc"],
            "call_order": ["search_docs_catalog", "read_specific_doc"],
        }
    },
]

def run_test(tc):
    """运行单个测试用例"""
    print(f"\n{'='*60}")
    print(f"🧪 {tc['id']}: {tc['name']}")
    print(f"{'='*60}")
    print(f"Q: {tc['question']}")

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": tc["question"]}
        ],
        "config": {"max_steps": 5},
        "stream": True
    }

    t_start = time.time()
    tool_calls = []
    sse_events = []
    answer_chunks = []
    step_count = 0
    dsml_detected = False
    raw_lines = []

    try:
        proc = subprocess.Popen(
            ["curl", "-s", "-N", "-X", "POST",
             f"{AI_BRIDGE}/v1/chat/completions",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        for line in iter(proc.stdout.readline, b''):
            raw = line.decode('utf-8', errors='replace').strip()
            if not raw or not raw.startswith("data: "):
                continue
            raw_lines.append(raw)

            data_str = raw[6:]  # strip "data: "
            if data_str == "[DONE]":
                break

            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Capture SSE events
            ct = chunk.get("custom_type", "")
            if ct == "agent_step":
                step_count = chunk.get("step", step_count)
                sse_events.append(f"  [Step {step_count}]")
            elif ct == "plugin_state":
                pn = chunk.get("plugin", {}).get("name", "?")
                ps = chunk.get("plugin", {}).get("status", "?")
                sse_events.append(f"  [Tool] {pn} → {ps}")
                if ps == "done":
                    tool_calls.append(pn)
            elif ct == "confirm_required":
                sse_events.append(f"  [Confirm] {chunk.get('operation',{}).get('kind','?')}")

            # Capture content
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                answer_chunks.append(content)

        proc.wait(timeout=30)
    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        return False

    t_elapsed = time.time() - t_start
    full_answer = "".join(answer_chunks)

    # ── 泄漏检测 ──
    leakage_patterns = [
        r'<\s*\|?\s*DSML',
        r'<\s*\|?\s*tool_calls',
        r'<\s*\|?\s*invoke',
        r'<\s*\|?\s*parameter',
    ]
    for pat in leakage_patterns:
        if re.search(pat, full_answer, re.I):
            dsml_detected = True
            print(f"  🚨 标签泄漏! 检测到: {pat}")
            break

    # ── 报告 ──
    checks = tc["checks"]
    all_pass = True

    print(f"\n📊 结果:")
    print(f"  耗时: {t_elapsed:.1f}s | ReAct 步数: {step_count} | 工具调用: {tool_calls}")

    # Check 1: Step count
    if "max_steps" in checks and step_count > checks["max_steps"]:
        print(f"  ❌ 步数超标: {step_count} > {checks['max_steps']}")
        all_pass = False
    if "min_steps" in checks and step_count < checks["min_steps"]:
        print(f"  ❌ 步数不足: {step_count} < {checks['min_steps']}")
        all_pass = False
    else:
        print(f"  ✅ 步数检查通过")

    # Check 2: Must-call tools
    for t in checks.get("must_call", []):
        if t not in tool_calls:
            print(f"  ❌ 缺少工具调用: {t}")
            all_pass = False
    if all(t in tool_calls for t in checks.get("must_call", [])):
        print(f"  ✅ 必须工具调用通过: {checks.get('must_call', [])}")

    # Check 3: Must-not-call tools
    for t in checks.get("must_not_call", []):
        if t in tool_calls:
            print(f"  ❌ 不应调用的工具被触发: {t}")
            all_pass = False
    if not any(t in tool_calls for t in checks.get("must_not_call", []) if t):
        print(f"  ✅ 禁止工具调用通过")

    # Check 4: Call order
    if "call_order" in checks:
        called_order = [t for t in tool_calls if t in checks["call_order"]]
        if called_order == checks["call_order"]:
            print(f"  ✅ 调用顺序正确: {called_order}")
        else:
            print(f"  ❌ 调用顺序错误: 期望 {checks['call_order']}, 实际 {called_order}")
            all_pass = False

    # Check 5: Tag leakage
    if dsml_detected:
        print(f"  ❌ 标签泄漏!")
        all_pass = False
    else:
        print(f"  ✅ 无标签泄漏")

    # Show SSE trace
    print(f"\n📡 SSE 事件跟踪:")
    for evt in sse_events:
        print(evt)

    # Show answer preview
    print(f"\n💬 回答预览 (前200字):")
    print(f"  {full_answer[:200]}...")

    return all_pass


if __name__ == "__main__":
    results = []
    for tc in TEST_CASES:
        passed = run_test(tc)
        results.append((tc["id"], passed))
        time.sleep(2)  # 间隔避免并发冲突

    print(f"\n{'='*60}")
    print(f"🏆 总结果:")
    for tid, passed in results:
        print(f"  {tid}: {'✅ PASS' if passed else '❌ FAIL'}")
    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n  通过: {passed}/{total}")
    if passed == total:
        print(f"  🎉 全部通过!")
    else:
        print(f"  ⚠️ 有失败用例，需排查")
        sys.exit(1)
