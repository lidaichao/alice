#!/usr/bin/env python3
"""姓名解析回归测试 — 4 个针对性场景"""
import requests, json, time

URL = "http://127.0.0.1:9099/v1/chat/completions"
KEY = "sk-17da90973c574066b3229a42ce053e1c"

TESTS = [
    ("标签泄漏", "DevelopV4版本最近新增了哪些任务",
     lambda t: '<|' not in t, "P0"),
    ("姓名解析", "杨正江最近提交了什么代码",
     lambda t: len(t) > 300 and ('r40446' in t or 'attr_v2' in t or '杨正江' in t or 'r4' in t),
     "P0"),
    ("GDrive分词", "Google云盘有哪些策划文档",
     lambda t: len(t) > 200 and '策划' not in t[:30],  # 不出现"查不到策划"这类否定
     "P1"),
    ("跨源名称", "李翰斌负责什么任务",
     lambda t: len(t) > 100,
     "P2"),
]

def run():
    print("=" * 60)
    print("姓名解析回归测试")
    print("=" * 60)
    
    results = []
    for label, question, check, pri in TESTS:
        print(f"\n[{pri}] {label}: {question}")
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
                    if c: full += c
                except: pass
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            results.append((label, False))
            continue
        
        elapsed = time.time() - start
        passed = check(full)
        status = "✅" if passed else "❌"
        
        seen = set()
        ut = [t for t in tools if t not in seen and not seen.add(t)]
        print(f"  {status} {elapsed:.1f}s | {len(full)}字 | {' → '.join(ut[-4:])}")
        print(f"  {full[:150].replace(chr(10),' ')}...")
        results.append((label, passed))
        time.sleep(1.5)
    
    print(f"\n{'='*60}")
    p = sum(1 for _, ok in results if ok)
    print(f"  {'🎉 全部通过！' if p==4 else f'⚠️ {p}/4 通过'}")
    print(f"{'='*60}")

if __name__ == '__main__':
    run()
