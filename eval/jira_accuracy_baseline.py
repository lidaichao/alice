#!/usr/bin/env python3
"""
Phase 0: Jira 准确性基线脚本（离线，不调用真实 Jira API）
用法: python eval/jira_accuracy_baseline.py
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from jira_search_engine import (
    parse_query_from_natural_language,
    build_resolved_jql,
    is_jira_structured_read_query,
    JiraSearchQuery,
)
from jira_runtime_config import load_jira_runtime_config
from intent_classifier import classify_intent

CSV_PATH = os.path.join(ROOT, "eval", "data", "testset_jira_accuracy.csv")
REPORT_PATH = os.path.join(ROOT, "eval", "reports", "jira_accuracy_baseline.md")


def main():
    cfg = load_jira_runtime_config({"jira_projects": "CT"})
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = row["question"]
            intent = classify_intent(q)
            lane = "structured_search" if is_jira_structured_read_query(q, intent.get("route", "")) else "other"
            jql = ""
            err = ""
            try:
                query = parse_query_from_natural_language(q, cfg)
                built = build_resolved_jql(query, cfg)
                jql = built.get("jql", "")
            except Exception as e:
                err = str(e)[:120]
            rows.append({
                "question": q,
                "expected": row.get("expected_behavior", ""),
                "expected_lane": row.get("jira_lane", ""),
                "intent": intent.get("route"),
                "actual_lane": lane,
                "jql": jql,
                "error": err,
                "lane_ok": lane == row.get("jira_lane", "") or row.get("jira_lane", "") in ("structured_search", "other"),
            })

    lane_ok = sum(1 for r in rows if r["actual_lane"] == r["expected_lane"] or r["expected_lane"] in ("react_commits", "write_confirm", "issue_key_vip", "weekly_vip"))
    jql_ok = sum(1 for r in rows if r["jql"] and not r["error"])

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    lines = [
        "# Jira 准确性基线报告 (Phase 0)",
        "",
        f"- 用例数: {len(rows)}",
        f"- 可生成 JQL: {jql_ok}/{len(rows)}",
        "",
        "| 问题 | 意图 | 车道(预期/实际) | JQL 片段 |",
        "|------|------|-----------------|----------|",
    ]
    for r in rows:
        jq = (r["jql"] or r["error"])[:80].replace("|", "/")
        lines.append(
            f"| {r['question'][:40]} | {r['intent']} | {r['expected_lane']}/{r['actual_lane']} | `{jq}` |"
        )
    lines.extend([
        "",
        "## 与 Baize 差距摘要",
        "",
        "- Baize: Claude Code 结构化 query + buildResolvedJql + analyzeIssues 再回答",
        "- Alice (本基线后): 规则 parse_query + build_resolved_jql + 读直通车",
        "- 待 A/B: 同 PAT 下协调者 5–10 条历史问句对比",
        "",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {REPORT_PATH}")
    print(f"JQL generated: {jql_ok}/{len(rows)}")


if __name__ == "__main__":
    main()
