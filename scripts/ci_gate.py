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

    if os.environ.get("ALICE_RUN_INTEGRATION", "").strip() in ("1", "true", "yes"):
        base = os.environ.get("ALICE_BASE_URL", "http://127.0.0.1:9099")
        if not _hub_up(base):
            print(f"FAIL Hub not reachable at {base} (start ai_bridge first)")
            return 1
        _run([py, os.path.join("scripts", "smoke_chat_only.py")])
        _run([py, os.path.join("scripts", "e2e_short_draft_memory.py")])
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
