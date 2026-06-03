#!/usr/bin/env python3
"""回归测试 — 针对修复的 4 个问题"""
import requests, json, time

URL = "http://127.0.0.1:9099/v1/chat/completions"
KEY = "sk-17da90973c574066b3229a42ce053e1c"

REGRESSION_TESTS = [
    # (标签, 问题, 检查项, 类型)
    ("标签泄漏回归", "DevelopV4版本最近新增了哪些任务",
     lambda t: '<|tool_calls' not in t and '<|invoke' not in t and '<|parameter' not in t,
     "P0"),
    ("S1 jira JQL", "CT项目待处理的任务有哪些",
     lambda t: 'CT-' in t and len(t) > 100,
     "P0"),
    ("S1 gdrive宽泛", "Google云盘有哪些策划文档",
     lambda t: len(t) > 200 and ('点球' in t or '球员' in t or '足小' in t),
     "P1"),
    ("姓名解析", "杨正江负责哪些任务",
     lambda t: len(t) > 100 and ('杨正江' in t or 'CT-' in t),
     "P1"),
    ("跨源汇总", "球员属性相关的设计文档和代码实现",
     lambda t: len(t) > 500 and ('Jira' in t or 'Notion' in t or 'SVN' in t or 'GDrive' in t),
     "P2"),
]

def run_regression():
    print("=" * 65)
    print("Alice 回归测试 — 4 处修复验证")
    print("=" * 65)
    
    results = []
    for label, question, check_fn, priority in REGRESSION_TESTS:
        print(f"\n[{priority}] {label}")
        print(f"  问题: {question}")
        
        start = time.time()
        full = ""
        tools = []
        try:
            r = requests.post(URL,
                json={"messages": [{"role": "user", "content": question}],
                      "config": {"deepseek_key": KEY, "deepseek_model": "deepseek-chat"}},
                stream=True, timeout=60)
            for line in r.iter_lines():
                if not line or not line.startswith(b'data: {'):
                    continue
                try:
                    d = json.loads(line[6:])
                    p = d.get('plugin', {})
                    if p.get('name') and p.get('status'):
                        tools.append(f"[{p['status']}] {p['name']}")
                    c = d.get('choices', [{}])[0].get('delta', {}).get('content', '')
                    if c:
                        full += c
                except:
                    pass
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            results.append((label, False, 0, str(e)[:80]))
            continue
        
        elapsed = time.time() - start
        passed = check_fn(full)
        status = "✅" if passed else "❌"
        
        # 工具链去重
        seen = set()
        unique_tools = [t for t in tools if t not in seen and not seen.add(t)]
        
        print(f"  {status} {elapsed:.1f}s | {len(full)}字 | {' → '.join(unique_tools[-4:])}")
        print(f"  摘要: {full[:120].replace(chr(10),' ')}...")
        
        if not passed:
            # 诊断
            if '<|tool_calls' in full:
                print(f"  ⚠️ 发现标签泄漏！")
            if len(full) < 100:
                print(f"  ⚠️ 回答过短 ({len(full)}字)")
        
        results.append((label, passed, len(full), ""))
        time.sleep(1)
    
    # 汇总
    print(f"\n{'='*65}")
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"  {'🎉 全部通过！' if passed == len(results) else f'⚠️ {passed}/{len(results)} 通过'}")
    print(f"{'='*65}")
    return results

if __name__ == '__main__':
    run_regression()
