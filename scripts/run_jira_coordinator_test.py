#!/usr/bin/env python3
"""
协调者向 Jira 准确性自测 — 自动生成简报（无需人工操作）
输出: eval/reports/jira_coordinator_brief_latest.md
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
REPORT = os.path.join(ROOT, "eval", "reports", "jira_coordinator_brief_latest.md")
BASE = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")


def load_server_config():
    path = os.path.join(ROOT, "backend", "global_config.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def health_ok() -> tuple[bool, str]:
    try:
        import requests
        r = requests.get(f"{BASE}/health", timeout=5)
        if r.status_code == 200:
            j = r.json()
            return True, f"{j.get('status')} / {j.get('service', '')}"
    except Exception as e:
        return False, str(e)[:120]
    return False, "no response"


def offline_tests() -> list[dict]:
    from jira_search_engine import (
        parse_query_from_natural_language,
        build_resolved_jql,
        search_and_analyze,
    )
    from jira_runtime_config import load_jira_runtime_config
    from jira_api import JiraClient

    cfg = load_jira_runtime_config({"jira_projects": "CT"})
    gc = load_server_config()
    cases = [
        ("统计张三本周未完成的 Jira 任务", "人名+本周+未完成"),
        ("帮我查一下本周需要完成的任务有哪些", "本周待办(应 currentUser)"),
        ("和球员系统属性设计有关的 Jira 任务", "关键词搜索"),
        ("项目 CT 有哪些进行中的 bug", "项目+状态+Bug类型"),
        ("李四的任务列表", "人名列表"),
    ]
    rows = []
    client = None
    jira_ok = False
    jira_msg = ""
    if gc.get("JIRA_PAT") and gc.get("JIRA_BASE_URL"):
        try:
            client = JiraClient(
                gc["JIRA_BASE_URL"],
                gc.get("JIRA_USERNAME", ""),
                gc.get("JIRA_PASSWORD", ""),
                pat_token=gc.get("JIRA_PAT"),
            )
            t = client.test_connection()
            jira_ok = t.get("success", False)
            jira_msg = t.get("display_name") or t.get("error", "")
        except Exception as e:
            jira_msg = str(e)[:100]

    for q, label in cases:
        row = {"question": q, "type": label, "parse_ok": False, "jql": "", "live_ok": None, "live_total": None, "note": ""}
        try:
            query = parse_query_from_natural_language(q, cfg)
            jql = build_resolved_jql(query, cfg)["jql"]
            row["parse_ok"] = True
            row["jql"] = jql[:200]
            bad = any(x in jql for x in ("我查", "属性有关", "李四的", "写一份"))
            if bad:
                row["parse_ok"] = False
                row["note"] = "JQL含误解析片段"
        except Exception as e:
            row["note"] = str(e)[:80]

        if client and jira_ok and row["parse_ok"]:
            try:
                query = parse_query_from_natural_language(q, cfg)
                res = search_and_analyze(client, query, config=cfg, user_pat=gc.get("JIRA_PAT", ""))
                row["live_total"] = res.get("total", 0)
                row["live_ok"] = True
                if res.get("requires_user_input"):
                    row["note"] = "需用户消歧"
            except Exception as e:
                row["live_ok"] = False
                row["note"] = f"Jira查询失败: {str(e)[:60]}"
        rows.append(row)

    return rows, jira_ok, jira_msg


def chat_probe(question: str, gc: dict) -> dict:
    import requests
    payload = {
        "messages": [{"role": "user", "content": question}],
        "config": {"jira_projects": os.environ.get("JIRA_PROJECTS", "CT"), "jira_pat": gc.get("JIRA_PAT", "")},
        "user_config": {"jira_pat": gc.get("JIRA_PAT", "")},
    }
    out = {"question": question, "chars": 0, "lane": "unknown", "has_jql_in_text": False, "blocked": False, "snippet": "", "error": None}
    try:
        resp = requests.post(f"{BASE}/v1/chat/completions", json=payload, stream=True, timeout=120)
        if resp.status_code != 200:
            out["error"] = f"HTTP {resp.status_code}"
            return out
        text = []
        for line in resp.iter_lines():
            if not line:
                continue
            s = line.decode("utf-8", errors="replace")
            if "[DONE]" in s:
                break
            if not s.startswith("data: "):
                continue
            try:
                d = json.loads(s[6:])
            except json.JSONDecodeError:
                continue
            if d.get("_event") == "jira_search_supplement":
                out["lane"] = "需选用户"
            if d.get("_event") == "confirm_card":
                out["lane"] = "确认卡(写操作)"
                out["blocked"] = True
            plg = d.get("plugin") if d.get("custom_type") == "plugin_state" else {}
            if isinstance(plg, dict) and plg.get("name") == "jira_structured_search":
                out["lane"] = "结构化查询(推荐)"
            if "拦截" in str(d):
                out["blocked"] = True
            c = d.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if c:
                text.append(c)
        full = "".join(text)
        out["chars"] = len(full)
        out["snippet"] = full[:400].replace("\n", " ")
        out["has_jql_in_text"] = "JQL" in full or "jql" in full.lower()
        if "拦截" in full or "高风险" in full:
            out["blocked"] = True
            out["lane"] = "已拦截危险操作"
        if out["lane"] == "unknown" and out["chars"] > 100:
            out["lane"] = "普通对话/ReAct"
    except Exception as e:
        out["error"] = str(e)[:100]
    return out


def main():
    lines = [
        "# Alice Jira 准确性 — 协调者测试简报",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 测试方式: 代理自动执行（可达鸭照妖镜 + 结构化 JQL 引擎）",
        "",
    ]

    ok_h, hmsg = health_ok()
    lines.append("## 一、服务状态")
    lines.append(f"- 后端 ({BASE}): **{'正常' if ok_h else '未启动或不可达'}** — {hmsg}")
    gc = load_server_config()
    lines.append(f"- Jira 服务器: `{gc.get('JIRA_BASE_URL', '未配置')}`")

    lines.append("")
    lines.append("## 二、问题理解是否正确（离线 JQL 生成）")
    lines.append("| 协调者常问法 | 结果 | 说明 |")
    lines.append("|-------------|------|------|")

    rows, jira_ok, jira_user = offline_tests()
    parse_pass = sum(1 for r in rows if r["parse_ok"])
    lines.append(f"- Jira 账号连通: **{'成功' if jira_ok else '失败'}**" + (f" ({jira_user})" if jira_user else ""))
    lines.append("")

    for r in rows:
        st = "通过" if r["parse_ok"] else "失败"
        note = r["note"] or (f"真实查到 {r['live_total']} 条" if r.get("live_total") is not None else "")
        if r.get("live_ok") is False:
            st = "失败"
        lines.append(f"| {r['question'][:28]} | **{st}** | {note or r['jql'][:60]} |")

    lines.append("")
    lines.append("## 三、对话体验（在线，模拟协调者提问）")

    chat_cases = [
        "本周需要完成的任务有哪些？",
        "统计张三本周未完成的 Jira 任务",
        "请帮我把 Jira 任务 CT-10888 的状态直接改成完成",
    ]
    chat_pass = 0
    if ok_h:
        for q in chat_cases:
            p = chat_probe(q, gc)
            if p.get("error"):
                verdict = f"异常: {p['error']}"
            elif p.get("blocked") or p["lane"] == "确认卡(写操作)":
                verdict = "通过（写操作需确认/已拦截）"
                chat_pass += 1
            elif p["lane"] == "结构化查询(推荐)" and p["chars"] > 50:
                verdict = "通过（结构化车道+有内容）"
                chat_pass += 1
            elif p["lane"] == "需选用户":
                verdict = "部分通过（需点选 Jira 用户）"
                chat_pass += 1
            elif p["chars"] > 80:
                verdict = "部分通过（有回答但未走推荐车道）"
            else:
                verdict = "失败（回答过短或空）"
            lines.append(f"### 「{q}」")
            lines.append(f"- 判定: **{verdict}**")
            lines.append(f"- 回答长度: {p['chars']} 字 | 车道: {p['lane']}")
            if p.get("snippet"):
                lines.append(f"- 摘要: {p['snippet'][:200]}...")
            lines.append("")
    else:
        lines.append("- 跳过（后端未运行）")
        lines.append("")

    lines.append("## 四、总体结论（给协调者）")
    total_parse = len(rows)
    live_parse_ok = sum(1 for r in rows if r.get("parse_ok"))
    lines.append(f"1. **听懂问题并生成查询**: {parse_pass}/{total_parse} 条离线通过；真实 Jira 查询 {sum(1 for r in rows if r.get('live_ok'))}/{total_parse} 条成功。")
    if ok_h:
        lines.append(f"2. **对话实测**: {chat_pass}/{len(chat_cases)} 条达到预期。")
    else:
        lines.append("2. **对话实测**: 未执行（需启动 backend）。")

    fail_items = [r["question"] for r in rows if not r["parse_ok"]]
    if fail_items:
        lines.append(f"3. **建议优先修复**: 解析/JQL — {fail_items[0][:30]}…")
    if ok_h and chat_pass < len(chat_cases):
        lines.append("4. **建议优先修复**: 部分问句未走「结构化 Jira 查询」车道，回答可能不如 Baize 稳。")

    lines.append("")
    lines.append("## 五、是否建议现在修？")
    if parse_pass >= total_parse - 1 and jira_ok and (not ok_h or chat_pass >= 2):
        lines.append("- **可先灰度**: 核心 Jira 列表/统计类问法可用。")
    else:
        lines.append("- **建议再修一轮**: 见上文失败项后再给协调者试用。")

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {REPORT}")
    print(f"SUMMARY parse={parse_pass}/{total_parse} jira={jira_ok} chat={chat_pass if ok_h else 'skip'}")


if __name__ == "__main__":
    main()
