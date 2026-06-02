#!/usr/bin/env python
"""Agent 评估 CLI 工具 — 运行 Benchmark 并输出报告"""
import sys, json, yaml
from eval_engine import run_evaluation, list_eval_datasets, get_eval_result

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_eval.py <dataset_name>")
        print("\nAvailable datasets:")
        for ds in list_eval_datasets():
            print(f"  {ds['file']} ({ds['cases']} cases)")
        sys.exit(0)
    
    dataset = sys.argv[1]
    print(f"Running benchmark: {dataset}")
    print("-" * 50)
    
    result = run_evaluation(dataset)
    
    print(f"\nResults: {result['passed']}/{result['total_cases']} passed")
    print(f"Avg Score: {result['avg_score']}%")
    print(f"Run ID: {result['run_id']}")
    
    for r in result['results']:
        status = "✅" if r['passed'] else "❌"
        print(f"\n{status} [{r['category']}] {r['id']}: score={r['score']}% (min={r['min_score']}%)")
        print(f"   Latency: {r['latency_ms']}ms")
        if r.get('matched_keywords'):
            print(f"   Keywords matched: {', '.join(r['matched_keywords'])}")
        if r.get('error'):
            print(f"   Error: {r['error']}")
