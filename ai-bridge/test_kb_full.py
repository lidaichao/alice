#!/usr/bin/env python3
"""
Alice 知识库全链路自测 — 10 个场景
每个问题调用 ai_bridge.py → 打印回答摘要 + 管道日志
"""
import requests, json, sys, time, os

URL = "http://127.0.0.1:9099/v1/chat/completions"
KEY = "sk-17da90973c574066b3229a42ce053e1c"
MODEL = "deepseek-chat"

# ── 10 个测试问题 ──
TESTS = [
    # 序号 | 场景 | 问题 | 期望源
    (1,  "Jira单任务",  "CT-11246 的详细信息是什么",                                ["jira"]),
    (2,  "Jira+SVN提交", "CT-11112 最近代码提交了哪些文件，谁提交的",                  ["jira","svn"]),
    (3,  "Jira多任务搜索","CT项目待处理的任务有哪些，按优先级排列",                     ["jira"]),
    (4,  "Notion列表",   "Notion知识库里有哪些技术相关的文档",                       ["notion"]),
    (5,  "GDrive列表",   "Google云盘有哪些策划文档",                                ["gdrive"]),
    (6,  "Notion内容",   "战术系统是怎么设计的，有哪些进攻和防守战术",                 ["notion"]),
    (7,  "GDrive内容",   "点球玩法是什么，规则是怎样的",                             ["gdrive"]),
    (8,  "跨源球员属性",  "球员属性相关的设计文档有哪些，代码是怎么实现的",             ["jira","svn","notion","gdrive"]),
    (9,  "按人查询",     "杨正江负责哪些任务，进度如何",                              ["jira"]),
    (10, "版本查询",     "DevelopV4版本最近新增了哪些任务",                           ["jira"]),
]

def run_test(tid, scene, question, expected_sources):
    """执行单条测试"""
    print(f"\n{'='*70}")
    print(f"测试 {tid}/10: {scene}")
    print(f"问题: {question}")
    print(f"期望源: {expected_sources}")
    print(f"{'='*70}")

    payload = {
        "messages": [{"role": "user", "content": question}],
        "config": {"deepseek_key": KEY, "deepseek_model": MODEL}
    }

    start = time.time()
    full_text = ""
    tool_chain = []
    try:
        r = requests.post(URL, json=payload, stream=True, timeout=60)
        plugin_state = ""
        for line in r.iter_lines():
            if not line:
                continue
            try:
                d = json.loads(line[6:]) if line.startswith(b'data: {') else None
                if not d:
                    continue
                # 工具调用链
                ps = d.get('plugin', {})
                if ps.get('name') and ps.get('status') != plugin_state:
                    tool_chain.append(f"[{ps['status']}] {ps['name']}")
                    plugin_state = ps['status']
                # 回答内容
                c = d.get('choices', [{}])[0].get('delta', {}).get('content', '')
                if c:
                    full_text += c
            except:
                pass
    except Exception as e:
        print(f"  ❌ 请求异常: {e}")
        return False

    elapsed = time.time() - start
    print(f"\n  ⏱ {elapsed:.1f}s")

    # 工具调用
    if tool_chain:
        unique_tools = []
        seen = set()
        for t in tool_chain:
            if t not in seen:
                seen.add(t)
                unique_tools.append(t)
        print(f"  🔧 工具调用链: {' → '.join(unique_tools[-5:])}")
    else:
        print(f"  🔧 工具调用链: (无)")

    # 回答摘要
    clean = full_text[:500].replace('\n', ' ')
    print(f"  💬 回答: {clean}...")
    
    # 检查引用标注
    if '[Jira:' in full_text or '[Notion:' in full_text or '[SVN:' in full_text or '[GDrive:' in full_text:
        sources = []
        if '[Jira:' in full_text: sources.append('Jira')
        if '[Notion:' in full_text: sources.append('Notion')
        if '[SVN:' in full_text: sources.append('SVN')
        if '[GDrive:' in full_text: sources.append('GDrive')
        print(f"  📎 引用溯源: {', '.join(sources)}")

    # 质量评估
    passes = []
    if full_text and len(full_text) > 20:
        passes.append("有内容")
    else:
        passes.append("内容不足")
    if '未找到' not in full_text and '无法回答' not in full_text and '没有' not in full_text[:100]:
        passes.append("非否定回答")
    else:
        passes.append("可能无数据")
    if '<|' not in full_text and 'DSML' not in full_text and 'tool_calls' not in full_text:
        passes.append("无标签泄漏")
    else:
        passes.append("标签泄漏")
    print(f"  ✅ 质量: {' | '.join(passes)}")
    
    return full_text, len(full_text) > 20 and '<|' not in full_text


if __name__ == '__main__':
    print("=" * 70)
    print("Alice 知识库全链路自测")
    print(f"目标: {URL}")
    print(f"模型: {MODEL}")
    print("=" * 70)

    results = []
    for tid, scene, question, expected in TESTS:
        try:
            text, ok = run_test(tid, scene, question, expected)
            results.append((tid, scene, ok, len(text) if text else 0))
        except Exception as e:
            print(f"  ❌ 崩溃: {e}")
            results.append((tid, scene, False, 0))
        time.sleep(1)  # 避免并发压力
    
    # ── 汇总 ──
    print(f"\n\n{'='*70}")
    print("📊 全链路自测汇总")
    print(f"{'='*70}")
    passed = sum(1 for _, _, ok, _ in results if ok)
    print(f"  通过: {passed}/10")
    print(f"  失败: {10-passed}/10")
    print(f"\n{'序号':<5} {'场景':<18} {'状态':<8} {'字数':<6}")
    print(f"{'-'*5:<5} {'-'*18:<18} {'-'*8:<8} {'-'*6:<6}")
    for tid, scene, ok, length in results:
        status = "✅" if ok else "❌"
        print(f"{tid:<5} {scene:<18} {status:<8} {length:<6}")
    
    if passed == 10:
        print("\n🎉 全部通过！")
    else:
        print(f"\n⚠️ {10-passed} 个测试未通过，需要排查")
