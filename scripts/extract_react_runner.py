#!/usr/bin/env python3
"""One-off: build backend/react_runner.py from ai_bridge ReAct section."""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
src_lines = (ROOT / "backend" / "ai_bridge.py").read_text(encoding="utf-8").splitlines()
block = src_lines[1989:2534]

HEADER = '''"""
ReAct runner — LangGraph fallback + ReAct loop + final stream (E1.3).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Set

from chat_pipeline.dsml_cleaner import clean_dsml_leak

logger = logging.getLogger(__name__)
SSE_DONE = b"data: [DONE]\\n\\n"


class ReactFallback(Exception):
    pass


@dataclass
class ReactRunContext:
    cleaned_msgs: list
    user_text: str
    issue_keys_found: set
    intent_info: dict
    user_cfg: dict
    frontend_cfg: dict
    headers: dict
    active_tools: list
    tool_names: list = field(default_factory=list)
    jira_client: Any = None
    deepseek_url: str = ""
    http_post: Callable = None
    execute_tool_call: Callable = None
    core_system_prompt: str = ""
    resolve_jira_username: Callable = None
    tool_executors: dict = field(default_factory=dict)

    @property
    def max_steps(self) -> int:
        return int(self.frontend_cfg.get("max_steps", 5) or 5)


def iter_v2_graph_stream(ctx: ReactRunContext) -> Iterator[bytes]:
    if ctx.user_cfg.get("engine") != "v2-graph" and os.environ.get("ALICE_ENGINE") != "v2":
        raise ReactFallback()
    logger.info("[V2 Graph] Invoking LangGraph Plan-and-Execute agent")
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from backend.agent.graph import graph as _v2_graph
    from backend.agent.nodes import init_agent as _v2_init
    import requests as _http
    _v2_init(
        deepseek_key=ctx.user_cfg["deepseek_key"],
        model=ctx.user_cfg["deepseek_model"],
        tools=ctx.active_tools[:5],
        executors=ctx.tool_executors,
        http_module=_http,
    )
    _v2_msgs = [m for m in ctx.cleaned_msgs if m.get("role") != "system"]
    if ctx.user_text:
        _v2_msgs.append({"role": "user", "content": ctx.user_text})
    final_state = _v2_graph.invoke({
        "messages": _v2_msgs,
        "plan": [],
        "plan_mode": "cross_domain",
        "past_steps": [],
        "final_answer": "",
    })
    answer = final_state.get("final_answer", "")
    if answer:
        payload = json.dumps({"choices": [{"delta": {"content": answer}}]}, ensure_ascii=False)
        yield f"data: {payload}\\n\\n".encode("utf-8")
    else:
        payload = json.dumps(
            {"choices": [{"delta": {"content": "[V2 Agent] 分析完成，但未生成回答。"}}]},
            ensure_ascii=False,
        )
        yield f"data: {payload}\\n\\n".encode("utf-8")
    yield SSE_DONE


def iter_react_pipeline(ctx: ReactRunContext) -> Iterator[bytes]:
    step = 0
    max_steps = ctx.max_steps
    user_text = ctx.user_text
    issue_keys_found = ctx.issue_keys_found
    user_cfg = ctx.user_cfg
    frontend_cfg = ctx.frontend_cfg
    headers = ctx.headers
    active_tools = ctx.active_tools
    tool_names = ctx.tool_names
'''

replacements = [
    ("jira.jira_get", "ctx.jira_client.jira_get"),
    ("jira.api_url", "ctx.jira_client.api_url"),
    ("resolve_jira_username(jira,", "ctx.resolve_jira_username(ctx.jira_client,"),
    ("CORE_SYSTEM_PROMPT_V2", "ctx.core_system_prompt"),
    ("DEEPSEEK_URL", "ctx.deepseek_url"),
    ("execute_tool_call(", "ctx.execute_tool_call("),
    ("http.post", "ctx.http_post"),
]

body_lines = []
for line in block:
    if line.startswith("        # ── 构建初始消息列表"):
        line = "    # ── 构建初始消息列表 (旧 ReAct)"
    if line.startswith("        "):
        line = "    " + line[8:]
    body_lines.append(line)

body = "\n".join(body_lines)
for old, new in replacements:
    body = body.replace(old, new)

out = HEADER + body + "\n"
(ROOT / "backend" / "react_runner.py").write_text(out, encoding="utf-8")
print("OK", (ROOT / "backend" / "react_runner.py").stat().st_size)
