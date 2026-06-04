"""Tests for Jira field glossary helpers."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jira_field_glossary import (
    normalize_glossary,
    format_glossary_for_prompt,
    resolve_glossary_entry_by_text,
    resolve_field_by_alias,
    glossary_suggests_deadline,
)
from jira_runtime_config import load_jira_runtime_config


class TestJiraFieldGlossary(unittest.TestCase):
    def test_normalize_list(self):
        raw = [
            {
                "fieldName": "End date",
                "meaning": "业务截止",
                "aliases": ["ddl", "截止时间"],
            }
        ]
        out = normalize_glossary(raw)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["fieldName"], "End date")
        self.assertEqual(out[0]["aliases"], ["ddl", "截止时间"])

    def test_normalize_aliases_string(self):
        raw = [{"fieldName": "X", "aliases": "a, b，c"}]
        out = normalize_glossary(raw)
        self.assertEqual(out[0]["aliases"], ["a", "b", "c"])

    def test_format_prompt_truncates(self):
        glossary = [{"fieldName": f"F{i}", "meaning": "m", "aliases": []} for i in range(40)]
        text = format_glossary_for_prompt(glossary, max_items=5)
        self.assertIn("F0", text)
        self.assertIn("另有", text)

    def test_resolve_by_alias(self):
        glossary = normalize_glossary([
            {"fieldName": "End date", "meaning": "截止", "aliases": ["本周要完成"]},
        ])
        entry = resolve_glossary_entry_by_text("张三本周要完成哪些任务", glossary)
        self.assertIsNotNone(entry)
        self.assertEqual(resolve_field_by_alias("ddl 在哪", glossary), "End date")

    def test_glossary_suggests_deadline(self):
        glossary = normalize_glossary([
            {"fieldName": "End date", "aliases": ["ddl"]},
        ])
        self.assertTrue(glossary_suggests_deadline("本周 ddl 任务", glossary))
        self.assertFalse(glossary_suggests_deadline("谁创建的", glossary))

    def test_runtime_config_loads_glossary(self):
        cfg = load_jira_runtime_config(
            global_cfg={
                "JIRA_PROJECTS": "CT",
                "JIRA_FIELD_GLOSSARY": [{"fieldName": "End date", "meaning": "x", "aliases": []}],
            }
        )
        self.assertEqual(len(cfg.field_glossary), 1)
        self.assertEqual(cfg.field_glossary[0]["fieldName"], "End date")


if __name__ == "__main__":
    unittest.main()
