"""Alice V2.0 E2E — 精简版 (内联 curl，处理中文)"""
import subprocess, json, re, time, sys
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

AI_BRIDGE = "http://127.0.0.1:9099"

TESTS = [
    ("T1", "轻量级查询", "CT-10852 现在的状态是什么，谁在负责？",
     {"must_call": ["query_jira_metadata"], "must_not_call": ["search_docs_catalog", "get_issue_commits", "read_specific_doc"], "max_steps": 2}),
    ("T2", "代码精准双跳", "CT-10852 这个任务改了哪些代码？给我代码的 diff 摘要。",
     {"must_call": ["get_issue_commits"], "must_not_call": ["search_docs_catalog", "read_specific_doc"], "max_steps": 2}),
    ("T3", "LlamaIndex层级检索", "CT-10852 这个任务，详细说明一下关联的《球员系统属性设计》这份文档的内容。",
     {"must_call": ["search_docs_catalog", "read_specific_doc"], "min_steps": 2}),
]

for tid, name, question, checks in TESTS:
    print(f"\n{'='*60}")
    print(f"🧪 {tid}: {name}")
    print(f"Q: {question}")
    
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": question}],
        "stream": True
    }, ensure_ascii=False)
    
    t0 = time.time()
    tool_calls, sse_trace, answer_parts = [], [], []
    dsml = False
    
    proc = subprocess.Popen(
        ["curl", "-s", "-N", "-X", "POST", f"{AI_BRIDGE}/v1/chat/completions",
         "-H", "Content-Type: application/json", "--data-binary", payload],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    
    for line in iter(proc.stdout.readline, b''):
        raw = line.decode('utf-8', errors='replace').strip()
        if not raw.startswith("data: "): continue
        data_str = raw[6:]
        if data_str == "[DONE]": break
        try: chunk = json.loads(data_str)
        except: continue
        
        ct = chunk.get("custom_type", "")
        if ct == "agent_step":
            sse_trace.append(f"[Step {chunk.get('step','?')}]")
        elif ct == "plugin_state":
            p = chunk.get("plugin", {})
            sse_trace.append(f"[{p.get('name','?')} {p.get('status','?')}]")
            if p.get("status") == "done": tool_calls.append(p.get("name", "?"))
        
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        c = delta.get("content", "")
        if c: answer_parts.append(c)
    
    proc.wait(timeout=30)
    t1 = time.time()
    answer = "".join(answer_parts)
    
    # 泄漏检测
    for pat in [r'<\|DSML', r'<\|tool_calls', r'<\|invoke', r'<\|parameter']:
        if re.search(pat, answer, re.I):
            dsml = True; break
    
    # 报告
    ok = True
    print(f"  耗时: {t1-t0:.1f}s | 工具调用: {tool_calls} | SSE: {' → '.join(sse_trace)}")
    
    for t in checks.get("must_call", []):
        if t not in tool_calls:
            print(f"  ❌ 缺少: {t}"); ok = False
    for t in checks.get("must_not_call", []):
        if t in tool_calls:
            print(f"  ❌ 不应调用: {t}"); ok = False
    if dsml: print(f"  ❌ 标签泄漏!"); ok = False
    
    if ok:
        print(f"  ✅ PASS")
        print(f"  💬 {answer[:150]}...")
    else:
        print(f"  ❌ FAIL")
    
    time.sleep(2)

print(f"\n{'='*60}")
print(f"🏆 完成")
