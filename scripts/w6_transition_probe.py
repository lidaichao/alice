#!/usr/bin/env python3
"""Probe CT-11152 status + transitions via Hub global_config."""
from __future__ import annotations

import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

from ai_bridge import load_global_config  # noqa: E402

cfg = load_global_config()
os.environ["JIRA_BASE_URL"] = cfg.get("JIRA_BASE_URL", "")
os.environ["JIRA_PAT"] = cfg.get("JIRA_PAT", "")
os.environ["JIRA_USERNAME"] = cfg.get("JIRA_USERNAME", "admin")

from jira_mcp_server import ensure_jira_connected  # noqa: E402

client, err = ensure_jira_connected()
if err:
    print("CONNECT_ERR", err)
    raise SystemExit(1)

key = sys.argv[1] if len(sys.argv) > 1 else "CT-11152"
r = client._request("GET", f"/issue/{key}?fields=status,summary", timeout=15)
data = r.json()
status = data["fields"]["status"]["name"]
summary = data["fields"]["summary"]
print(json.dumps({"issue_key": key, "status": status, "summary": summary}, ensure_ascii=False))
trans = client.list_transitions(key)
print(json.dumps(
    [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "to_status": (t.get("to") or {}).get("name"),
        }
        for t in trans
    ],
    ensure_ascii=False,
    indent=2,
))
