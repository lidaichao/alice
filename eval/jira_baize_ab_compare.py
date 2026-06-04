#!/usr/bin/env python3
"""
Alice vs Baize Jira 准确性 A/B（同 PAT、同问句集）。

用法:
  py -3 eval/jira_baize_ab_compare.py
  py -3 eval/jira_baize_ab_compare.py --live-chat   # 含 Alice /v1/chat 探针
  BAIZE_BASE_URL=http://127.0.0.1:3000 py -3 eval/jira_baize_ab_compare.py  # 可选 Baize 侧

输出: eval/reports/jira_baize_ab_latest.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
REPORT = os.path.join(ROOT, "eval", "reports", "jira_baize_ab_latest.md")
CSV_PATH = os.path.join(ROOT, "eval", "data", "testset_jira_accuracy.csv")
ALICE_BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
BAIZE_BASE = os.environ.get("BAIZE_BASE_URL", "").rstrip("/")


def load_gc():
    path = os.path.join(ROOT, "backend", "global_config.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def alice_offline_rows():
    from jira_search_engine import parse_query_from_natural_language, build_resolved_jql
    from jira_runtime_config import load_jira_runtime_config

    cfg = load_jira_runtime_config({"jira_projects": "CT"})
    rows = []
    import csv
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            q = row["question"]
            try:
                query = parse_query_from_natural_language(q, cfg)
                jql = build_resolved_jql(query, cfg).get("jql", "")
                rows.append({"question": q, "jql": jql[:200], "ok": bool(jql)})
            except Exception as e:
                rows.append({"question": q, "jql": "", "ok": False, "error": str(e)[:80]})
    return rows


def alice_live_search(question: str, gc: dict) -> dict:
    import requests
    r = requests.post(
        f"{ALICE_BASE}/v1/jira/search",
        json={"query": question, "config": {"jira_projects": "CT"}},
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    if r.status_code != 200:
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    data = r.json()
    res = data.get("result") or {}
    return {
        "ok": data.get("ok", False),
        "total": res.get("total", 0),
        "jql": (res.get("jql") or "")[:200],
        "recovery": (res.get("jira_search_recovery") or {}).get("status"),
    }


def baize_search(question: str) -> dict:
    import requests
    if not BAIZE_BASE:
        return {"skipped": True}
    try:
        r = requests.post(
            f"{BAIZE_BASE}/plugins/jira/search",
            json={"query": question},
            timeout=90,
        )
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        data = r.json()
        return {
            "ok": True,
            "total": data.get("total", data.get("issueCount", 0)),
            "jql": (data.get("jql") or "")[:200],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-chat", action="store_true", help="运行 run_jira_coordinator_test 对话探针")
    args = ap.parse_args()

    gc = load_gc()
    offline = alice_offline_rows()
    off_ok = sum(1 for r in offline if r["ok"])

    live_rows = []
    if gc.get("JIRA_PAT"):
        import csv
        with open(CSV_PATH, encoding="utf-8") as f:
            questions = [row["question"] for row in csv.DictReader(f)][:8]
        for q in questions:
            a = alice_live_search(q, gc)
            b = baize_search(q)
            live_rows.append({"question": q, "alice": a, "baize": b})

    chat_summary = ""
    if args.live_chat:
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_jira_coordinator_test.py")], check=False)
        chat_summary = "（已刷新 jira_coordinator_brief_latest.md）"

    lines = [
        "# Alice Jira 准确性对照报告",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> Alice: `{ALICE_BASE}` | 对照服务: `{BAIZE_BASE or '未配置（可选）'}`",
        "",
        "## 1. Alice 离线 JQL（规则引擎）",
        f"- 通过: **{off_ok}/{len(offline)}**",
        "",
        "| 问句 | JQL 片段 |",
        "|------|----------|",
    ]
    for r in offline:
        lines.append(f"| {r['question'][:36]} | `{(r.get('jql') or r.get('error', ''))[:70]}` |")

    lines.extend(["", "## 2. 同问句 Live 搜索（Alice API vs 可选对照服务）", ""])
    if not live_rows:
        lines.append("- 跳过（无 JIRA_PAT 或未执行 live）")
    else:
        lines.append("| 问句 | Alice total | Alice JQL | 对照 |")
        lines.append("|------|-------------|-----------|-------|")
        for row in live_rows:
            a, b = row["alice"], row["baize"]
            btxt = "跳过" if b.get("skipped") else f"{b.get('total', '?')} / {str(b.get('jql', b.get('error', '')))[:40]}"
            lines.append(
                f"| {row['question'][:30]} | {a.get('total', '?')} | `{a.get('jql', '')[:50]}` | {btxt} |"
            )

    lines.extend([
        "",
        "## 3. 准确性对齐路线图",
        "",
        "| 能力 | 目标 | Alice 当前 | 优先级 |",
        "|------|------|------------|--------|",
        "| NL→结构化 query | 语义槽位提取 | 规则 parse_query | P0 逐步加 LLM 槽位 |",
        "| JQL 失败恢复 | 智能改写 JQL | 规则 + **LLM recovery**（JIRA_LLM_RECOVERY） | P0 已接入 |",
        "| 负责人字段 | Admin 可配置 | Admin 表单化配置 | P0 已加 UI |",
        "| 用户消歧 | LLM 自动选 | 仅 supplement 卡片 | P1 |",
        "| Bug 分析/批量导入 | 完整流水线 | Phase 4 占位 | P2 |",
        "",
        f"## 4. 对话探针 {chat_summary}",
        "",
        "协调者可将历史问句追加到 `eval/data/testset_jira_accuracy.csv` 后重跑本脚本。",
    ])

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {REPORT}")
    print(f"SUMMARY offline={off_ok}/{len(offline)} live={len(live_rows)} baize={'on' if BAIZE_BASE else 'off'}")


if __name__ == "__main__":
    main()
