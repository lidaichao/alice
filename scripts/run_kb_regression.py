#!/usr/bin/env python3
"""
Alice multi-source KB regression — Tier1 offline / Tier2 live lane / Tier3 LLM judge.

Usage:
  py -3 scripts/run_kb_regression.py --tier all
  py -3 scripts/run_kb_regression.py --tier 2 --filter sources=jira
  py -3 scripts/run_kb_regression.py --offline-only
  py -3 scripts/run_kb_regression.py --tier 3 --live-only
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_DIR = os.path.join(ROOT, "eval")
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, EVAL_DIR)

from lib.oracle_assert import evaluate_live_case, split_semicolon_list
from lib.sse_collect import DEFAULT_BASE_URL, stream_chat, stream_result_to_serializable
from lib import llm_judge

MATRIX_CSV = os.path.join(EVAL_DIR, "data", "testset_kb_matrix.csv")
REPORTS_DIR = os.path.join(EVAL_DIR, "reports")
LATEST_REPORT = os.path.join(REPORTS_DIR, "kb_regression_latest.md")


def load_matrix(
    path: str,
    source_filter: str | None,
    coordinator_only: bool = False,
    id_prefix: str | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid = (row.get("id") or "").strip()
            if coordinator_only and not rid.startswith("coord-"):
                continue
            if id_prefix and not rid.startswith(id_prefix):
                continue
            if source_filter:
                src = (row.get("sources") or "").lower()
                want = [s.strip().lower() for s in source_filter.split(",")]
                if not any(w in src for w in want):
                    continue
            rows.append(row)
    return rows


def run_tier1() -> dict[str, Any]:
    """Offline Jira parse + jira_accuracy_baseline report."""
    results: dict[str, Any] = {"name": "tier1", "passed": 0, "total": 0, "details": []}

    # Inline offline suite (same as test_jira_accuracy_e2e)
    try:
        from jira_search_engine import parse_query_from_natural_language, build_resolved_jql
        from jira_runtime_config import load_jira_runtime_config

        cfg = load_jira_runtime_config({"jira_projects": "CT"})
        cases = [
            ("统计张三本周未完成", lambda q: "张三" in q.assignees and q.unresolved_only),
            ("本周需要完成的任务", lambda q: q.unresolved_only and not q.assignees),
            ("和球员系统属性有关的 Jira 任务", lambda q: bool(q.text) and not q.assignees),
            ("项目 CT 进行中 bug", lambda q: q.project_key == "CT" and q.issue_types == ["Bug"]),
        ]
        for text, check in cases:
            results["total"] += 1
            q = parse_query_from_natural_language(text, cfg)
            jql = build_resolved_jql(q, cfg)["jql"]
            ok = check(q) and "我查" not in jql and "属性有关" not in jql
            if ok:
                results["passed"] += 1
            results["details"].append({"case": text, "passed": ok, "jql": jql[:120]})
    except Exception as e:
        results["error"] = str(e)

    # Subprocess: jira baseline + test_jira_accuracy_e2e offline
    for script in (
        os.path.join(EVAL_DIR, "jira_accuracy_baseline.py"),
        os.path.join(ROOT, "scripts", "test_jira_accuracy_e2e.py"),
    ):
        if not os.path.isfile(script):
            continue
        try:
            cmd = [sys.executable, script]
            if script.endswith("test_jira_accuracy_e2e.py"):
                cmd.append("--offline-only")
            subprocess.run(cmd, cwd=ROOT, check=False, timeout=120, capture_output=True)
        except Exception as e:
            results.setdefault("subprocess_errors", []).append(f"{os.path.basename(script)}: {e}")
    results["baseline_report"] = os.path.join(REPORTS_DIR, "jira_accuracy_baseline.md")

    # Matrix offline rows
    for row in load_matrix(MATRIX_CSV, None):
        if (row.get("tier") or "").strip() != "offline":
            continue
        results["total"] += 1
        qtext = row.get("question", "")
        try:
            from jira_search_engine import parse_query_from_natural_language, build_resolved_jql
            from jira_runtime_config import load_jira_runtime_config

            cfg = load_jira_runtime_config({"jira_projects": "CT"})
            q = parse_query_from_natural_language(qtext, cfg)
            jql = build_resolved_jql(q, cfg).get("jql", "")
            ok = bool(jql) and "我查" not in jql
            if ok:
                results["passed"] += 1
            results["details"].append({"id": row.get("id"), "case": qtext, "passed": ok, "jql": jql[:120]})
        except Exception as e:
            results["details"].append({"id": row.get("id"), "case": qtext, "passed": False, "error": str(e)})

    return results


def run_tier2(rows: list[dict], base_url: str, skip_live: bool) -> list[dict]:
    import requests

    case_results: list[dict] = []
    if skip_live:
        return case_results

    live_rows = [r for r in rows if (r.get("tier") or "").strip() in ("live_lane", "live_judge", "")]
    if not live_rows:
        return case_results

    try:
        h = requests.get(f"{base_url}/health", timeout=5)
        if h.status_code != 200:
            return [{"error": f"health HTTP {h.status_code}", "passed": False}]
    except Exception as e:
        return [{"error": f"backend offline: {e}", "passed": False}]

    for row in live_rows:
        cid = row.get("id", "")
        question = row.get("question", "")
        verdict_mode = (row.get("verdict_mode") or "oracle_struct").strip()

        stream = stream_chat(question, base_url=base_url)
        eval_out = evaluate_live_case(row, stream, verdict_mode)

        passed = eval_out.get("passed", False)
        full_content = stream.get("content") or ""
        case_results.append({
            "id": cid,
            "question": question,
            "sources": row.get("sources"),
            "verdict_mode": verdict_mode,
            "passed": passed,
            "failures": eval_out.get("failures", []),
            "plugins_seen": sorted(stream.get("plugins_seen") or []),
            "content_preview": full_content[:300],
            "answer_full": full_content,
            "latency_s": stream.get("latency_s"),
            "error": stream.get("error"),
            "stream": stream_result_to_serializable(stream),
        })
        time.sleep(0.3)

    return case_results


def run_tier3(rows: list[dict], tier2_results: list[dict], base_url: str, skip_live: bool) -> list[dict]:
    if skip_live:
        return []

    by_id = {r["id"]: r for r in tier2_results if r.get("id")}
    judge_rows = [
        r for r in rows
        if (r.get("verdict_mode") or "").strip() == "oracle_llm"
        or (r.get("tier") or "").strip() == "live_judge"
    ]

    out: list[dict] = []
    key = llm_judge.get_deepseek_key()
    if not key:
        return [{"error": "DEEPSEEK_KEY not set — skip Tier3", "passed": False}]

    for row in judge_rows:
        cid = row.get("id", "")
        question = row.get("question", "")
        ground = row.get("ground_truth", "")

        prev = by_id.get(cid)
        if prev and prev.get("answer_full"):
            answer = prev["answer_full"]
        elif prev and prev.get("stream", {}).get("content"):
            answer = prev["stream"]["content"]
        else:
            stream = stream_chat(question, base_url=base_url)
            answer = stream.get("content") or ""

        verdict = llm_judge.judge_answer(question, ground, answer)
        passed = llm_judge.judge_passes(verdict)
        out.append({
            "id": cid,
            "question": question,
            "passed": passed,
            "faithfulness": verdict.get("faithfulness"),
            "relevance": verdict.get("relevance"),
            "reason": verdict.get("reason", ""),
        })
        time.sleep(0.5)

    return out


def merge_pass(row: dict, t2: dict | None, t3: dict | None, tier3_ran: bool) -> bool:
    mode = (row.get("verdict_mode") or "oracle_struct").strip()
    if t2 and not t2.get("passed", True):
        return False
    if mode == "oracle_llm":
        if not tier3_ran:
            return bool(t2 and t2.get("passed"))
        if t3 is None:
            return False
        return bool(t3.get("passed"))
    if mode == "human_only":
        return bool(t2 and t2.get("passed"))
    return bool(t2 and t2.get("passed"))


def write_report(
    path: str,
    tier1: dict,
    tier2: list[dict],
    tier3: list[dict],
    matrix_rows: list[dict],
    base_url: str,
) -> None:
    t2_by_id = {r["id"]: r for r in tier2 if r.get("id")}
    t3_by_id = {r["id"]: r for r in tier3 if r.get("id")}

    live_rows = [r for r in matrix_rows if (r.get("tier") or "").strip() != "offline"]
    tier3_ran = bool(tier3) and not (len(tier3) == 1 and tier3[0].get("error"))
    passed = sum(
        1
        for r in live_rows
        if merge_pass(r, t2_by_id.get(r.get("id", "")), t3_by_id.get(r.get("id", "")), tier3_ran)
    )
    failed = [
        r
        for r in live_rows
        if not merge_pass(r, t2_by_id.get(r.get("id", "")), t3_by_id.get(r.get("id", "")), tier3_ran)
    ]

    lines = [
        "# Alice KB Regression Report",
        "",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> Backend: {base_url}",
        f"> Dataset: testset_kb_matrix.csv ({len(matrix_rows)} rows, {len(live_rows)} live)",
        "",
        "## Summary",
        "",
        "| Tier | Result |",
        "|------|--------|",
        f"| Tier1 offline | {tier1.get('passed', 0)}/{tier1.get('total', 0)} |",
        f"| Tier2 live lane | {sum(1 for x in tier2 if x.get('passed'))}/{len(tier2)} |",
        f"| Tier3 LLM judge | {sum(1 for x in tier3 if x.get('passed'))}/{len(tier3)} |",
        f"| **Overall live PASS** | **{passed}/{len(live_rows)}** |",
        "",
    ]

    if failed:
        lines += ["## Failed cases", ""]
        for r in failed[:25]:
            cid = r.get("id", "")
            t2 = t2_by_id.get(cid, {})
            lines.append(f"### {cid}")
            lines.append(f"- **Q:** {r.get('question', '')[:200]}")
            lines.append(f"- **Mode:** {r.get('verdict_mode')}")
            if t2.get("failures"):
                lines.append(f"- **Failures:** {'; '.join(t2['failures'])}")
            if t2.get("plugins_seen"):
                lines.append(f"- **Plugins:** {t2['plugins_seen']}")
            if t2.get("content_preview"):
                lines.append(f"- **Answer preview:** {t2['content_preview'][:200]}...")
            t3 = t3_by_id.get(cid)
            if t3:
                lines.append(f"- **Judge:** F={t3.get('faithfulness')} R={t3.get('relevance')} — {t3.get('reason', '')[:120]}")
            lines.append("")

    lines += ["## Tier1 details", ""]
    for d in tier1.get("details", [])[:20]:
        status = "PASS" if d.get("passed") else "FAIL"
        lines.append(f"- [{status}] {d.get('case', d.get('id', ''))[:60]}")

    lines += ["", "## Tier2 all", "", "| id | pass | plugins | failures |", "|----|:----:|---------|----------|"]
    for t2 in tier2:
        if t2.get("error") and not t2.get("id"):
            lines.append(f"| — | FAIL | — | {t2['error']} |")
            continue
        fail = "; ".join(t2.get("failures") or [])[:80]
        lines.append(
            f"| {t2.get('id','')} | {'Y' if t2.get('passed') else 'N'} | "
            f"{','.join(t2.get('plugins_seen') or [])[:40]} | {fail} |"
        )

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Alice KB multi-source regression")
    parser.add_argument("--tier", default="all", help="1, 2, 3, or all")
    parser.add_argument("--filter", dest="source_filter", default=None, help="sources=jira,svn")
    parser.add_argument("--offline-only", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--report", default=None, help="Report path (default eval/reports/kb_regression_latest.md)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--coordinator-only",
        action="store_true",
        help="Only run rows with id prefix coord- (from coordinator_questions.txt)",
    )
    args = parser.parse_args()

    source_filter = None
    if args.source_filter:
        source_filter = args.source_filter.split("=", 1)[-1].strip()

    matrix_path = MATRIX_CSV
    if not os.path.isfile(matrix_path):
        print(f"Missing {matrix_path}")
        return 1

    rows = load_matrix(
        matrix_path,
        source_filter,
        coordinator_only=args.coordinator_only,
    )
    tiers = args.tier.lower().replace("tier", "").strip()
    run_t1 = tiers in ("all", "1") and not args.live_only
    run_t2 = tiers in ("all", "2") and not args.offline_only
    run_t3 = tiers in ("all", "3") and not args.offline_only

    print("=" * 70)
    print("  Alice KB Regression")
    print("=" * 70)

    tier1: dict = {}
    tier2: list = []
    tier3: list = []

    if run_t1:
        print("\n[Tier 1] Offline Jira parse + baseline...")
        tier1 = run_tier1()
        print(f"  Tier1: {tier1.get('passed', 0)}/{tier1.get('total', 0)}")

    if run_t2:
        print(f"\n[Tier 2] Live lane assertions ({len([r for r in rows if r.get('tier') != 'offline'])} cases)...")
        tier2 = run_tier2(rows, args.base_url, skip_live=args.offline_only)
        if tier2 and tier2[0].get("error") and len(tier2) == 1:
            print(f"  {tier2[0]['error']}")
        else:
            p2 = sum(1 for x in tier2 if x.get("passed"))
            print(f"  Tier2: {p2}/{len(tier2)}")

    if run_t3:
        print("\n[Tier 3] LLM judge (oracle_llm / live_judge)...")
        tier3 = run_tier3(rows, tier2, args.base_url, skip_live=args.offline_only)
        if tier3 and tier3[0].get("error"):
            print(f"  {tier3[0]['error']}")
        else:
            p3 = sum(1 for x in tier3 if x.get("passed"))
            print(f"  Tier3: {p3}/{len(tier3)}")

    report_path = args.report or LATEST_REPORT
    ts_report = os.path.join(REPORTS_DIR, f"kb_regression_{int(time.time())}.md")
    write_report(ts_report, tier1, tier2, tier3, rows, args.base_url)
    write_report(report_path, tier1, tier2, tier3, rows, args.base_url)
    print(f"\nReport: {report_path}")
    print(f"        {ts_report}")

    # Exit code
    ok = True
    if run_t1 and tier1.get("total"):
        ok = ok and tier1.get("passed", 0) >= tier1.get("total", 1) * 0.9
    if run_t2 and tier2 and not (len(tier2) == 1 and tier2[0].get("error")):
        ok = ok and sum(1 for x in tier2 if x.get("passed")) >= max(1, len(tier2) * 0.75)
    print(f"\n{'PASS' if ok else 'FAIL'} (exit {'0' if ok else '1'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
