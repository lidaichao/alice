import requests, time

def test(label, q, issue="CT-11074"):
    t0 = time.time()
    r = requests.post("http://localhost:9099/v1/chat/completions",
        json={"model":"t","messages":[
            {"role":"system","content":"Issue:t\nKey:"+issue+"\n---\n用一句话回答。"},
            {"role":"user","content":q}
        ]}, timeout=60)
    t1 = time.time()
    content = r.json()["choices"][0]["message"]["content"]
    print("[%s] %.1fs | %d chars" % (label, t1-t0, len(content)))
    print("  Q:", q[:60])
    print("  A:", content[:150])
    return t1 - t0

print("=== Test 1: Light (L1 only) ===")
t1 = test("T1-LIGHT", "简单说下这个任务是什么")
time.sleep(1)

print("\n=== Test 2: Cache hit (same issue) ===")
t2 = test("T2-CACHE", "再用一句话描述")

print("\n=== Test 3: Deep (L1+L2) ===")
t3 = test("T3-DEEP", "详细分析代码变更涉及哪些模块，具体改了什么，风险在哪")

print("\n=== Test 4: CT-10833 with Notion docs ===")
t4 = test("T4-NOTION", "需求文档核心内容是什么", "CT-10833")

print("\n=== SUMMARY ===")
print("T1(L1): %.1fs | T2(cache): %.1fs | T3(L1+L2): %.1fs | T4(notion): %.1fs" % (t1,t2,t3,t4))
if t2 > 0:
    print("Cache speedup: %.1fx faster" % (t1/t2))
