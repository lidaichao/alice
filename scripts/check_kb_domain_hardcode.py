#!/usr/bin/env python3
"""C9.6: block project-specific business terms in intent routing code."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# Terms that must not appear in routing classifiers (project eval may still use them).
FORBIDDEN_IN_INTENT = (
    "球员系统",
    "中锋",
    "门将",
    "前锋",
    "后卫",
)

SCAN_FILES = (
    BACKEND / "intent_classifier.py",
    BACKEND / "intent_router.py",
)


def main() -> int:
    failed: list[str] = []
    for path in SCAN_FILES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for term in FORBIDDEN_IN_INTENT:
            if term in text:
                failed.append(f"{path.name}: contains forbidden term {term!r}")
    if failed:
        for line in failed:
            print(f"FAIL {line}")
        return 1
    print("CHECK_KB_DOMAIN_HARDCODE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
