#!/usr/bin/env python3
"""
Read eval/data/coordinator_questions.txt and merge coord-* rows into testset_kb_matrix.csv.
"""
from __future__ import annotations

import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS_TXT = os.path.join(ROOT, "eval", "data", "coordinator_questions.txt")
MATRIX_CSV = os.path.join(ROOT, "eval", "data", "testset_kb_matrix.csv")

CSV_FIELDS = [
    "id",
    "question",
    "sources",
    "tier",
    "verdict_mode",
    "expected_plugins",
    "forbidden_plugins",
    "must_contain_any",
    "must_not_contain",
    "ground_truth",
    "lane_hint",
]


def parse_questions_txt(path: str) -> list[tuple[str, str]]:
    """Return list of (question, optional_expected)."""
    items: list[tuple[str, str]] = []
    if not os.path.isfile(path):
        return items
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "\t" in line:
                parts = line.split("\t", 1)
                q, exp = parts[0].strip(), parts[1].strip()
            else:
                q, exp = line, ""
            if q:
                items.append((q, exp))
    return items


def _is_jira_write_intent(q: str) -> bool:
    """Status change / create — not substring '完成' in '完成的任务'."""
    if not re.search(r"(?:Jira|jira|任务|CT-|bug|Bug|状态)", q, re.I):
        return False
    if re.search(
        r"(?:改成|改为|修改为|设为|设置为|更新为).*(?:状态|为|处理中|进行中|完成|关闭)",
        q,
    ):
        return True
    if re.search(r"(?:创建|新建|删除).*(?:jira|任务|issue|bug)", q, re.I):
        return True
    if re.search(r"CT-\d+.*(?:改成|改为).*(?:完成|关闭|处理中)", q, re.I):
        return True
    return False


def _is_knowledge_doc_intent(q: str) -> bool:
    if re.search(r"文档|知识库|wiki|云盘|策划案|设计案|KB-|Google", q, re.I):
        return True
    if "文档" in q and re.search(r"设计|规则|讲讲|分析", q):
        return True
    return False


def infer_case(question: str, expected_note: str, index: int) -> dict[str, str]:
    q = question

    sources = []
    expected_plugins: list[str] = []
    forbidden_plugins: list[str] = []
    must_contain: list[str] = []
    must_not: list[str] = []
    lane_hint = ""
    verdict_mode = "oracle_struct"
    tier = "live_lane"
    ground_truth = expected_note or "根据问句自动推断：应诚实作答，不得编造数据。"

    # Commits / FishEye / SVN
    if any(k in q for k in ("提交", "FishEye", "fisheye", "改了什么", "SVN", "svn", "r40")):
        sources.extend(["jira", "fisheye", "svn"])
        expected_plugins.append("get_issue_commits")
        forbidden_plugins.append("jira_structured_search")
        must_contain.extend(["提交", "版本", "r", "FishEye", "未找到", "没有"])
        must_not.extend(["JQL", "assignee="])
        lane_hint = "commits_only"
        ground_truth = expected_note or "应查询代码提交记录（含版本号），不要返回 Jira 任务列表。"

    # Write / dangerous (explicit status change only)
    elif _is_jira_write_intent(q):
        sources.append("jira")
        must_contain.extend(
            ["确认", "拦截", "不能", "无法", "拒绝", "confirm", "手动", "不支持"]
        )
        must_not.extend(["已为您", "已修改", "已创建"])
        lane_hint = "write_or_block"
        ground_truth = expected_note or "写操作应弹出确认或明确拒绝，不得擅自改 Jira。"

    # Docs / KB / Notion (align with intent_router tools)
    elif _is_knowledge_doc_intent(q):
        sources.extend(["kb", "notion"])
        if "云盘" in q or "Google" in q:
            sources.append("gdrive")
        expected_plugins.extend(["search_docs_catalog", "read_specific_doc"])
        must_contain.extend(["文档", "未找到", "没有", "知识库", "Notion", "云盘"])
        verdict_mode = "oracle_struct"
        tier = "live_lane"
        ground_truth = expected_note or "应检索知识库/文档后回答，或诚实说明未找到。"

    # Diff / review
    elif any(k in q for k in ("diff", "Diff", "分析", "Review", "审查")) and re.search(r"r\d+", q):
        sources.extend(["svn", "fisheye"])
        verdict_mode = "human_only"
        must_contain.extend(["diff", "分析", "代码", "未找到", "没有"])
        ground_truth = expected_note or "应结合版本做代码分析；开放题由协调者人工抽检。"

    # Jira list / weekly
    else:
        sources.append("jira")
        expected_plugins.extend(["jira_structured_search", "search_jira_issues"])
        must_contain.extend(["JQL", "任务", "未找到", "没有", "Bug", "CT-"])
        lane_hint = "structured_or_weekly"
        ground_truth = expected_note or "应走 Jira 查询并返回任务列表或明确无结果。"

    # Issue key detail
    if re.search(r"CT-\d+", q) and any(k in q for k in ("详情", "是什么", "什么情况")):
        must_contain.extend(["CT-", "状态", "经办", "未找到"])

    sources_str = ",".join(dict.fromkeys(sources))
    row_id = f"coord-{index:03d}"

    return {
        "id": row_id,
        "question": q,
        "sources": sources_str,
        "tier": tier,
        "verdict_mode": verdict_mode,
        "expected_plugins": ";".join(dict.fromkeys(expected_plugins)),
        "forbidden_plugins": ";".join(dict.fromkeys(forbidden_plugins)),
        "must_contain_any": ";".join(dict.fromkeys(must_contain)),
        "must_not_contain": ";".join(dict.fromkeys(must_not)),
        "ground_truth": ground_truth.replace("\n", " "),
        "lane_hint": lane_hint,
    }


def load_matrix_rows(path: str) -> list[dict[str, str]]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_matrix(path: str, rows: list[dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def sync(questions_path: str = QUESTIONS_TXT, matrix_path: str = MATRIX_CSV) -> int:
    items = parse_questions_txt(questions_path)
    if not items:
        print(f"No questions in {questions_path}")
        return 1

    coord_rows = [
        infer_case(q, exp, i + 1) for i, (q, exp) in enumerate(items)
    ]

    existing = load_matrix_rows(matrix_path)
    kept = [r for r in existing if not (r.get("id") or "").startswith("coord-")]
    merged = kept + coord_rows
    write_matrix(matrix_path, merged)

    print(f"Synced {len(coord_rows)} coordinator question(s) -> {matrix_path}")
    for r in coord_rows:
        print(f"  {r['id']}: {r['question'][:50]}...")
    return 0


def main() -> int:
    return sync()


if __name__ == "__main__":
    sys.exit(main())
