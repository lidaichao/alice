#!/usr/bin/env python3
"""Sync backend/eval/datasets/kb_matrix.yaml from eval/data/testset_kb_matrix.csv (M1 subset)."""
from __future__ import annotations

import csv
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "eval", "data", "testset_kb_matrix.csv")
YAML_PATH = os.path.join(ROOT, "backend", "eval", "datasets", "kb_matrix.yaml")

# M1: prefer live_lane + coord-*; skip offline tier
PREFERRED_IDS = [
    "smoke-commits",
    "smoke-weekly",
    "smoke-block",
    "smoke-kb",
    "smoke-cross",
    "jira-01",
    "jira-02",
    "jira-05",
    "jira-07",
    "jira-09",
    "jira-10",
    "svn-01",
    "kb-01",
    "kb-02",
    "bench-01",
    "route-01",
    "route-02",
    "coord-001",
    "coord-003",
    "coord-004",
    "coord-007",
    "coord-008",
]
MIN_CASES = 20


def _split_semi(s: str) -> list[str]:
    if not s or not str(s).strip():
        return []
    return [x.strip() for x in str(s).split(";") if x.strip()]


def _row_to_case(row: dict) -> dict:
    plugins = _split_semi(row.get("expected_plugins", ""))
    forbidden = _split_semi(row.get("forbidden_plugins", ""))
    keywords = _split_semi(row.get("must_contain_any", ""))
    sources = (row.get("sources") or "general").split(",")[0].strip() or "general"
    case: dict = {
        "id": row["id"],
        "input": row["question"],
        "category": sources,
        "min_score": 40,
    }
    if plugins:
        case["expected_plugins"] = plugins
    if forbidden:
        case["forbidden_plugins"] = forbidden
    if keywords:
        case["expected_keywords"] = keywords
    return case


def main() -> int:
    if not os.path.isfile(CSV_PATH):
        print(f"MISSING {CSV_PATH}")
        return 1
    by_id: dict[str, dict] = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("tier") or "").strip() == "offline":
                continue
            by_id[row["id"]] = row

    cases: list[dict] = []
    for cid in PREFERRED_IDS:
        if cid in by_id:
            cases.append(_row_to_case(by_id[cid]))
    for row in by_id.values():
        if len(cases) >= MIN_CASES:
            break
        if row["id"] in {c["id"] for c in cases}:
            continue
        if (row.get("tier") or "") == "offline":
            continue
        cases.append(_row_to_case(row))

    if len(cases) < MIN_CASES:
        print(f"FAIL only {len(cases)} cases (need {MIN_CASES})")
        return 1

    doc = {
        "name": "kb_matrix",
        "version": "1.1",
        "description": "多数据源知识库回归（Admin / run_eval；由 scripts/sync_kb_matrix_from_csv.py 生成）",
        "rubric": {
            "max_score": 100,
            "dimensions": [
                {"name": "routing", "weight": 40, "description": "工具/快车道是否正确"},
                {"name": "oracle", "weight": 60, "description": "协调者结构化断言"},
            ],
        },
        "test_cases": cases[: max(len(cases), MIN_CASES)],
    }
    os.makedirs(os.path.dirname(YAML_PATH), exist_ok=True)
    with open(YAML_PATH, "w", encoding="utf-8") as out:
        out.write("# KB matrix — M1 subset (>=20 cases). Regenerate: py scripts/sync_kb_matrix_from_csv.py\n")
        yaml.dump(doc, out, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"OK wrote {len(doc['test_cases'])} cases -> {YAML_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
