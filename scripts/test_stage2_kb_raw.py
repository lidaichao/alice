#!/usr/bin/env python3
"""
照妖镜 Stage 2 — 底层知识库搬运工测试
测试 knowledge_retriever 各底层函数的原始数据返回
"""
import sys, os, json, traceback, logging

# 暴力日志 — 不静默任何输出
logging.basicConfig(level=logging.INFO, format="%(levelname)s| %(message)s")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def test(name, fn):
    print(f"\n{'─'*60}")
    print(f"[Test] {name}", flush=True)
    try:
        result = fn()
        if result is None or (isinstance(result, str) and not result.strip()):
            print(f"{RED}[FAIL] 空结果!{RESET}", flush=True)
        elif isinstance(result, str) and ('失败' in result or '异常' in result or 'Error' in result):
            print(f"{YELLOW}[WARN] {result[:300]}{RESET}", flush=True)
        else:
            text = str(result)
            print(f"{GREEN}[OK] {len(text)} chars{RESET}", flush=True)
            for line in text.split('\n')[:25]:
                print(f"  │ {line[:120]}", flush=True)
    except Exception:
        print(f"{RED}[EXCEPTION]{RESET}", flush=True)
        traceback.print_exc()

def main():
    print("=" * 60, flush=True)
    print("  照妖镜 Stage 2 — 底层搬运工测试", flush=True)
    print("=" * 60, flush=True)

    # 尝试导入
    try:
        from knowledge_retriever import (
            get_single_commit_diff,
            extract_dynamic_keywords,
            fetch_precise_commits_via_fisheye,
        )
        print(f"{GREEN}[INFO] knowledge_retriever imported OK{RESET}", flush=True)
    except Exception:
        print(f"{RED}[FATAL] Cannot import knowledge_retriever!{RESET}", flush=True)
        traceback.print_exc()
        return

    test("SVN Diff r40538", lambda: get_single_commit_diff("40538"))
    test("DynamicContextResolver: CT-10888", lambda: extract_dynamic_keywords("CT-10888 阵型养成", "CT-10888"))
    test("FishEye: CT-10888 commits", lambda: fetch_precise_commits_via_fisheye("CT-10888"))
    test("SVN Diff r99999 (invalid)", lambda: get_single_commit_diff("99999"))

    print(f"\n{'='*60}", flush=True)
    print("  Stage 2 完成", flush=True)

if __name__ == "__main__":
    main()
