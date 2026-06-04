#!/usr/bin/env python3
"""
Coordinator one-click eval: sync questions.txt -> run regression -> plain Chinese report.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "eval", "reports")
COORD_REPORT = os.path.join(REPORTS_DIR, "协调者报告_latest.md")
TECH_REPORT = os.path.join(REPORTS_DIR, "kb_regression_latest.md")
QUESTIONS_TXT = os.path.join(ROOT, "eval", "data", "coordinator_questions.txt")


def translate_failures(failures: list[str]) -> list[str]:
    out: list[str] = []
    for f in failures or []:
        msg = f
        if "expected_plugins" in msg:
            if "get_issue_commits" in msg:
                out.append("Alice 没有按预期去查「代码提交 / FishEye」，可能误走了 Jira 任务列表。")
            elif "search_doc_chunks" in msg or "search_docs_catalog" in msg or "read_specific_doc" in msg:
                out.append("Alice 没有按预期去查「知识库 / 文档」（目录检索或读取全文）。")
            elif "jira_structured_search" in msg or "search_jira_issues" in msg:
                out.append("Alice 没有按预期去查「Jira 任务列表」。")
            else:
                out.append("Alice 没有调用预期的查询功能。")
        elif "forbidden_plugins" in msg:
            if "jira_structured_search" in msg:
                out.append("Alice 误用了「Jira 任务列表」查询（本题应查提交记录等）。")
            else:
                out.append("Alice 调用了不该使用的功能。")
        elif "must_contain_any" in msg:
            out.append("回答里缺少应有内容（例如：提交记录、任务、或诚实的「未找到」）。")
        elif "must_not_contain" in msg:
            out.append("回答里出现了不该有的内容（例如误展示 JQL、或声称已擅自修改 Jira）。")
        elif "lane_hint" in msg:
            if "commits" in msg:
                out.append("本题应走「查提交」通道，但实际没有。")
            elif "write_or_block" in msg:
                out.append("本题应拦截或要求确认才能改 Jira，但回答未体现。")
            elif "structured_or_weekly" in msg:
                out.append("本题应走「Jira 列表 / 周报」通道，但实际没有。")
            else:
                out.append("Alice 走的查询通道与问题类型不匹配。")
        elif msg.startswith("stream error"):
            out.append(f"无法连接 Alice 服务：{msg}")
        else:
            out.append(msg)
    return out


def build_chinese_report(
    question_count: int,
    backend_ok: bool,
    tier2_results: list[dict],
    tier3_by_id: dict[str, dict],
    matrix_rows: list[dict],
) -> str:
    """Build plain Chinese report from live tier2/tier3 results."""
    import run_kb_regression as reg

    coord_questions = {
        r["id"]: r.get("question", "")
        for r in matrix_rows
        if (r.get("id") or "").startswith("coord-")
    }
    t2_by_id = {r["id"]: r for r in tier2_results if r.get("id")}
    tier3_ran = bool(tier3_by_id)

    failed_items: list[dict] = []
    passed_ids: set[str] = set()
    total_coord = question_count

    def _coord_sort_key(rid: str) -> int:
        try:
            return int(rid.replace("coord-", ""))
        except ValueError:
            return 9999

    for rid, question in sorted(coord_questions.items(), key=lambda x: _coord_sort_key(x[0])):
        row = next((r for r in matrix_rows if r.get("id") == rid), {})
        t2 = t2_by_id.get(rid)
        t3 = tier3_by_id.get(rid)
        if not backend_ok or not t2:
            continue
        ok = reg.merge_pass(row, t2, t3, tier3_ran)
        if ok:
            passed_ids.add(rid)
        else:
            failed_items.append({
                "id": rid,
                "question": question,
                "failures": t2.get("failures", []),
                "preview": t2.get("content_preview", ""),
            })

    passed_n = len(passed_ids)

    lines = [
        "# Alice 问题评测报告（协调者版）",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 您录入的问题数：**{question_count}**",
        f"> 问题文件：`eval/data/coordinator_questions.txt`",
        "",
        "## 总体结果",
        "",
    ]

    if not backend_ok:
        lines += [
            "**说明：Alice 服务未启动或未连接**，本次可能只做了部分检查。",
            "请先启动 `backend/ai_bridge.py`（端口 9099），再重新运行评测。",
            "",
        ]

    if total_coord:
        fail_n = total_coord - passed_n
        lines.append(f"- **通过：{passed_n} 题**")
        lines.append(f"- **未通过：{fail_n} 题**")
    else:
        lines.append("- 未检测到已同步的问题，请检查 questions.txt 是否为空。")

    lines += ["", "## 逐题结果", "", "| 序号 | 结果 | 您的问题 | 说明 |", "|:--:|:--:|----------|------|"]

    for i in range(1, question_count + 1):
        cid = f"coord-{i:03d}"
        q = coord_questions.get(cid, "（未同步）")
        if cid in passed_ids:
            result = "通过"
            note = "—"
        elif any(f["id"] == cid for f in failed_items):
            f0 = next(x for x in failed_items if x["id"] == cid)
            result = "未通过"
            plain = translate_failures(f0.get("failures", []))
            note = "；".join(plain) if plain else "回答不符合自动检查规则"
        elif not backend_ok:
            result = "未测"
            note = "服务未连接，未实际提问"
        else:
            result = "未通过"
            note = "请查看技术报告或稍后重试"

        q_short = q[:40] + ("…" if len(q) > 40 else "")
        lines.append(f"| {i} | {result} | {q_short} | {note} |")

    if failed_items:
        lines += ["", "## 未通过详情（白话）", ""]
        for f in failed_items:
            lines.append(f"### 第 {f['id'].replace('coord-', '').lstrip('0') or '0'} 题")
            lines.append(f"- **问题：** {f.get('question', '')}")
            for p in translate_failures(f.get("failures", [])):
                lines.append(f"- **原因：** {p}")
            if f.get("preview"):
                lines.append(f"- **Alice 回答摘录：** {f['preview'][:250]}")
            lines.append("")

    lines += ["", "## 每题 Alice 完整答复", ""]
    for i in range(1, question_count + 1):
        cid = f"coord-{i:03d}"
        q = coord_questions.get(cid, "")
        t2 = t2_by_id.get(cid, {})
        ans = (t2.get("answer_full") or t2.get("content_preview") or "").strip()
        lines.append(f"### 第 {i} 题")
        lines.append(f"**问：** {q}")
        if ans:
            lines.append(f"**答：**\n\n{ans[:8000]}")
        else:
            lines.append("**答：**（无正文 — 可能服务未连接或超时）")
        lines.append("")

    lines += [
        "",
        "## 您只需记住",
        "",
        "1. 用记事本改 `eval/data/coordinator_questions.txt`（一行一个问题）",
        "2. 保存后双击 `run_coordinator_eval.bat`，或在 Cursor 说「跑问题评测」",
        "3. 只看本报告「通过 / 未通过」；未通过且确认是 Alice 的锅 → 交给开发/Agent 修",
        "",
        f"（技术人员可查看：`eval/reports/kb_regression_latest.md`）",
    ]
    return "\n".join(lines)


def check_backend(base_url: str = "http://127.0.0.1:9099") -> bool:
    try:
        import requests
        r = requests.get(f"{base_url}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def main() -> int:
    os.chdir(ROOT)
    scripts_dir = os.path.join(ROOT, "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    eval_dir = os.path.join(ROOT, "eval")
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)
    sys.path.insert(0, os.path.join(ROOT, "backend"))

    import run_kb_regression as reg

    print("=" * 60)
    print("  Alice 协调者评测（只测您录入的问题）")
    print("=" * 60)

    if not os.path.isfile(QUESTIONS_TXT):
        print(f"缺少问题文件: {QUESTIONS_TXT}")
        return 1

    # 1) Sync
    print("\n[1/3] 同步您的问题列表...")
    sync_script = os.path.join(ROOT, "scripts", "sync_coordinator_questions.py")
    rc = subprocess.call([sys.executable, sync_script])
    if rc != 0:
        return rc

    with open(QUESTIONS_TXT, encoding="utf-8") as f:
        qcount = sum(
            1
            for line in f
            if line.strip() and not line.strip().startswith("#")
        )

    backend_ok = check_backend()
    if not backend_ok:
        print("\n[提示] Alice 后端未连接 (9099)，将只跑离线检查 + 生成报告。")

    matrix_rows = reg.load_matrix(reg.MATRIX_CSV, None, coordinator_only=True)

    # 2) Regression
    print("\n[2/3] 自动提问 Alice 并检查回答...")
    tier2: list[dict] = []
    tier3: list[dict] = []
    if backend_ok:
        tier2 = reg.run_tier2(matrix_rows, reg.DEFAULT_BASE_URL, skip_live=False)
        tier3 = reg.run_tier3(matrix_rows, tier2, reg.DEFAULT_BASE_URL, skip_live=False)
        reg.write_report(TECH_REPORT, {}, tier2, tier3, matrix_rows, reg.DEFAULT_BASE_URL)
    else:
        tier1 = reg.run_tier1()
        reg.write_report(TECH_REPORT, tier1, [], [], matrix_rows, reg.DEFAULT_BASE_URL)

    tier3_by_id = {r["id"]: r for r in tier3 if r.get("id")}

    # 3) Chinese report
    print("\n[3/3] 生成中文报告...")
    report_text = build_chinese_report(qcount, backend_ok, tier2, tier3_by_id, matrix_rows)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(COORD_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n完成！请打开：\n  {COORD_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
