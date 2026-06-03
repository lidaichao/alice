#!/usr/bin/env python3
"""
照妖镜 Stage 2 — 底层知识库搬运工测试
测试 knowledge_retriever 各底层函数的原始数据返回
直接用 Python import，不经过 HTTP 层
"""
import sys, os, json

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def test(name, fn):
    """运行测试并打印结果"""
    print(f"\n{'='*60}")
    print(f"  [测试] {name}")
    print(f"{'='*60}")
    try:
        result = fn()
        if result is None or (isinstance(result, str) and not result.strip()):
            print(f"{RED}  ❌ 空结果!{RESET}")
        elif isinstance(result, str) and '失败' in result:
            print(f"{YELLOW}  ⚠️ {result[:200]}{RESET}")
        else:
            text = str(result)[:600]
            print(f"{GREEN}  ✅ 返回 {len(str(result))} 字符{RESET}")
            print(f"  ┌─ 前300字符 ─────────────────")
            for line in text.split('\n')[:15]:
                print(f"  │ {line[:100]}")
            print(f"  └──────────────────────────────")
    except Exception as e:
        print(f"{RED}  ❌ 异常: {e}{RESET}")

def main():
    print("=" * 60)
    print("  照妖镜 Stage 2 — 底层搬运工测试")
    print("=" * 60)

    from knowledge_retriever import (
        get_single_commit_diff,
        extract_dynamic_keywords,
        fetch_precise_commits_via_fisheye,
    )

    # Test 1: SVN Diff 直拉
    test("SVN Diff r40538", lambda: get_single_commit_diff("40538"))

    # Test 2: 动态关键词提取
    test("DynamicContextResolver: CT-10888 阵型养成",
         lambda: extract_dynamic_keywords("CT-10888 阵型养成 代码diff", "CT-10888"))

    # Test 3: FishEye 提交列表
    test("FishEye 提交列表: CT-10888",
         lambda: fetch_precise_commits_via_fisheye("CT-10888"))

    # Test 4: 非法参数防御
    test("非法版本号 r99999", lambda: get_single_commit_diff("99999"))

    print(f"\n{'='*60}")
    print(f"  Stage 2 完成. 上方如有 ❌ 红色需排查.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
