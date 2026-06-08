#!/usr/bin/env python3
"""
M1 CI gate (no LLM required): intent self-test + kb_matrix count + optional Hub smokes.
Set ALICE_RUN_INTEGRATION=1 and start Hub on 9099 for smoke/e2e.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(cmd: list[str], cwd: str | None = None) -> None:
    print("+", " ".join(cmd))
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run(cmd, cwd=cwd or ROOT, check=True, env=env)


def _hub_up(base: str) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    py = sys.executable
    _run([py, os.path.join("backend", "intent_classifier.py")])
    _run([py, os.path.join("scripts", "validate_kb_matrix_yaml.py")])
    _run([py, os.path.join("backend", "tests", "test_chat_orchestrator.py")])
    _run([py, os.path.join("backend", "tests", "test_hitl_sse.py")])
    _run([py, os.path.join("backend", "tests", "test_intent_router.py")])
    _run([py, os.path.join("backend", "tests", "test_doc_content_extractor.py")])
    _run([py, os.path.join("backend", "tests", "test_recovery_supplement.py")])
    _run([py, os.path.join("backend", "tests", "test_catalog_hybrid.py")])
    _run([py, os.path.join("backend", "tests", "test_mcp_registry.py")])
    _run([py, os.path.join("backend", "tests", "test_audit_trace.py")])
    _run([py, os.path.join("backend", "tests", "test_workflow_engine.py")])
    _run([py, os.path.join("backend", "tests", "test_shallow_memory_injection.py")])
    _run([py, os.path.join("backend", "tests", "test_kb_context_cache.py")])
    _run([py, os.path.join("backend", "tests", "test_gdrive_knowledge.py")])
    _run([py, os.path.join("scripts", "check_kb_domain_hardcode.py")])
    _run([py, os.path.join("scripts", "test_mailbox_store.py")])

    if os.environ.get("ALICE_RUN_INTEGRATION", "").strip() in ("1", "true", "yes"):
        base = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
        if not _hub_up(base):
            print(f"FAIL Hub not reachable at {base} (start ai_bridge first)")
            return 1
        _run([py, os.path.join("scripts", "smoke_chat_only.py")])
        _run([py, os.path.join("scripts", "e2e_short_draft_memory.py")])
        if os.environ.get("ALICE_RUN_W6", "").strip() in ("1", "true", "yes"):
            if not os.environ.get("W6_ISSUE_KEY", "").strip():
                print("FAIL ALICE_RUN_W6=1 requires W6_ISSUE_KEY")
                return 1
            _run([py, os.path.join("scripts", "e2e_w6_transition.py")])
            print("OK w6 transition e2e")
        if os.environ.get("ALICE_RUN_E4", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "e2e_e4_hub_only.py")])
            print("OK e4 hub-only e2e")
        if os.environ.get("ALICE_RUN_MCP", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "cursor_e2e_mcp.py")])
            print("OK cursor mcp e2e")
        if os.environ.get("ALICE_RUN_GDRIVE_E2E", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "e2e_gdrive_sheet.py")])
            _run([py, os.path.join("scripts", "e2e_gdrive_chat.py")])
            print("OK gdrive sheet + chat e2e")
        if os.environ.get("ALICE_RUN_MAILBOX_E2E", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "e2e_mailbox.py")])
            print("OK mailbox e2e")
        if os.environ.get("ALICE_RUN_MAILBOX_MCP_E2E", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "e2e_mailbox_mcp.py")])
            print("OK mailbox mcp e2e")
        if os.environ.get("ALICE_RUN_OPS_CONSOLE_E2E", "").strip() in ("1", "true", "yes"):
            _run([py, os.path.join("scripts", "e2e_operations_console.py")])
            print("OK operations console e2e")
        print("OK integration smokes")
    else:
        print("SKIP integration (set ALICE_RUN_INTEGRATION=1 to run smoke/e2e)")

    print("CI_GATE_OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        print(f"CI_GATE_FAIL exit={e.returncode}")
        sys.exit(e.returncode or 1)
