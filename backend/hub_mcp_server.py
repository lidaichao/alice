#!/usr/bin/env python3
"""
Alice Hub MCP Server (stdio) — readonly + mailbox worker tools from tools/registry.yaml.

Usage:
  cd backend && py -3 hub_mcp_server.py

Cursor MCP config example:
  { "command": "py", "args": ["-3", "H:/workbuddy/alice/backend/hub_mcp_server.py"] }
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("NO_PROXY", "*")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_bridge import load_global_config, parse_user_config  # noqa: E402
from mcp_registry import (  # noqa: E402
    get_readonly_tools,
    get_worker_tools,
    invoke_mailbox_tool,
    invoke_readonly_tool,
)

_cfg = load_global_config()
for k, env in (
    ("JIRA_BASE_URL", "JIRA_BASE_URL"),
    ("JIRA_PAT", "JIRA_PAT"),
    ("JIRA_USERNAME", "JIRA_USERNAME"),
    ("DEEPSEEK_KEY", "DEEPSEEK_KEY"),
):
    if _cfg.get(k):
        os.environ.setdefault(env, str(_cfg[k]))

_USER_CFG = parse_user_config({})

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("Install mcp package: pip install mcp", file=sys.stderr)
    raise SystemExit(1)

mcp = FastMCP("alice-hub")


def _register_readonly_tools() -> None:
    for spec in get_readonly_tools():
        tool_name = spec["name"]
        tool_desc = (spec.get("description") or tool_name).strip()

        def _bind(name: str, desc: str):
            @mcp.tool(name=name, description=desc[:800])
            def _tool(**kwargs) -> str:
                out = invoke_readonly_tool(name, kwargs, _USER_CFG, origin="mcp_stdio")
                return json.dumps(out, ensure_ascii=False)

        _bind(tool_name, tool_desc)


def _register_worker_tools() -> None:
    for spec in get_worker_tools():
        tool_name = spec["name"]
        tool_desc = (spec.get("description") or tool_name).strip()

        def _bind(name: str, desc: str):
            @mcp.tool(name=name, description=desc[:800])
            def _tool(**kwargs) -> str:
                out = invoke_mailbox_tool(name, kwargs, origin="mcp_stdio")
                return json.dumps(out, ensure_ascii=False)

        _bind(tool_name, tool_desc)


_register_readonly_tools()
_register_worker_tools()


if __name__ == "__main__":
    mcp.run()
