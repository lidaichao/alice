#!/usr/bin/env python3
"""CI: kb_matrix.yaml must have >= 20 test cases."""
from __future__ import annotations

import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(ROOT, "backend", "eval", "datasets", "kb_matrix.yaml")
MIN_CASES = 20


def main() -> int:
    if not os.path.isfile(YAML_PATH):
        print(f"FAIL missing {YAML_PATH}")
        return 1
    with open(YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    cases = data.get("test_cases") or []
    n = len(cases)
    if n < MIN_CASES:
        print(f"FAIL kb_matrix has {n} cases (need >={MIN_CASES})")
        return 1
    print(f"OK kb_matrix.yaml cases={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
