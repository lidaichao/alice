"""
Structured oracle assertions (coordinator ground truth) — no LLM required.
"""
from __future__ import annotations

import re
from typing import Any


def split_semicolon_list(value: str | None) -> list[str]:
    if not value or not str(value).strip():
        return []
    return [p.strip() for p in str(value).split(";") if p.strip()]


def check_must_contain_any(content: str, terms: list[str]) -> tuple[bool, str]:
    if not terms:
        return True, ""
    lower = (content or "").lower()
    if any(t.lower() in lower for t in terms):
        return True, ""
    return False, f"must_contain_any: none of {terms}"


def check_must_not_contain(content: str, terms: list[str]) -> tuple[bool, str]:
    if not terms:
        return True, ""
    lower = (content or "").lower()
    for t in terms:
        if t.lower() in lower:
            return False, f"must_not_contain: found '{t}'"
    return True, ""


def check_plugins(
    plugins_seen: set[str] | list[str],
    expected: list[str],
    forbidden: list[str],
) -> tuple[bool, str]:
    seen = set(plugins_seen or [])
    if forbidden:
        bad = [p for p in forbidden if p in seen]
        if bad:
            return False, f"forbidden_plugins hit: {bad}"
    if expected:
        if not any(p in seen for p in expected):
            return False, f"expected_plugins: need one of {expected}, got {sorted(seen)}"
    return True, ""


def check_lane_flags(result: dict, case: dict[str, Any]) -> tuple[bool, str]:
    """Optional lane hints from CSV tier=live_lane extras."""
    lane = (case.get("lane_hint") or "").strip()
    if not lane:
        return True, ""
    if lane == "structured_or_weekly":
        ok = (
            result.get("structured_lane")
            or result.get("weekly_lane")
            or "JQL" in (result.get("content") or "")
        )
        if not ok:
            return False, "lane_hint: expected structured_or_weekly"
    if lane == "write_or_block":
        content = result.get("content") or ""
        ok = result.get("confirm_card") or any(
            x in content
            for x in (
                "拦截",
                "拒绝",
                "确认",
                "不能",
                "无法",
                "无法直接",
                "不支持",
                "手动",
                "confirm",
            )
        )
        if not ok:
            return False, "lane_hint: expected write_or_block"
    if lane == "commits_only":
        ok = result.get("commits_lane") or "get_issue_commits" in (result.get("plugins_seen") or set())
        if not ok:
            return False, "lane_hint: expected commits lane"
    return True, ""


def evaluate_struct_oracle(case: dict[str, Any], stream_result: dict) -> dict:
    """
    Run oracle_struct checks on a live stream result.
    Returns {passed, failures: list[str], checks: dict}
    """
    content = stream_result.get("content") or ""
    plugins = stream_result.get("plugins_seen") or set()
    failures: list[str] = []

    if stream_result.get("error"):
        return {
            "passed": False,
            "failures": [f"stream error: {stream_result['error']}"],
            "checks": {},
        }

    must_any = split_semicolon_list(case.get("must_contain_any"))
    must_not = split_semicolon_list(case.get("must_not_contain"))
    expected_plugins = split_semicolon_list(case.get("expected_plugins"))
    forbidden_plugins = split_semicolon_list(case.get("forbidden_plugins"))

    checks = {}

    ok, msg = check_must_contain_any(content, must_any)
    checks["must_contain_any"] = ok
    if not ok:
        failures.append(msg)

    ok, msg = check_must_not_contain(content, must_not)
    checks["must_not_contain"] = ok
    if not ok:
        failures.append(msg)

    ok, msg = check_plugins(plugins, expected_plugins, forbidden_plugins)
    checks["plugins"] = ok
    if not ok:
        failures.append(msg)

    ok, msg = check_lane_flags(stream_result, case)
    checks["lane_hint"] = ok
    if not ok:
        failures.append(msg)

    # Optional regex anchors in ground_truth column: pattern:...
    gt = (case.get("ground_truth") or "")
    for line in gt.split("\n"):
        line = line.strip()
        if line.startswith("regex:"):
            pat = line[6:].strip()
            if pat and not re.search(pat, content, re.I):
                failures.append(f"regex failed: {pat}")
                checks["regex"] = False
            else:
                checks["regex"] = True

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "checks": checks,
    }


def evaluate_live_case(case: dict[str, Any], stream_result: dict, verdict_mode: str) -> dict:
    """
    Full live evaluation: plugins + struct; human_only skips content oracle.
    """
    verdict_mode = (verdict_mode or "oracle_struct").strip()
    plugins_only = verdict_mode == "human_only"

    base = evaluate_struct_oracle(
        {
            **case,
            "must_contain_any": "" if plugins_only else case.get("must_contain_any"),
            "must_not_contain": case.get("must_not_contain"),
        },
        stream_result,
    )

    if plugins_only:
        # human_only: only plugin/lane checks matter for auto pass
        must_any = split_semicolon_list(case.get("must_contain_any"))
        if must_any:
            ok, msg = check_must_contain_any(stream_result.get("content") or "", must_any)
            if not ok:
                base["passed"] = False
                base["failures"].append(msg)

    base["verdict_mode"] = verdict_mode
    base["quality_skip"] = verdict_mode == "human_only"
    return base
