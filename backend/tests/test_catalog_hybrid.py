import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from catalog_hybrid import boost_catalog_entries, extract_catalog_needles, merge_hybrid_snippets


def test_extract_kb_and_issue():
    needles = extract_catalog_needles("查 KB-foo 和 CT-123 文档")
    assert "KB-FOO" in needles
    assert "CT-123" in needles


def test_boost_kb_id_first():
    cat = [
        {"doc_id": "1", "title": "无关", "snippet": ""},
        {"doc_id": "2", "title": "KB-FOO 策划", "snippet": ""},
    ]
    out = boost_catalog_entries(cat, "KB-FOO")
    assert out[0]["doc_id"] == "2"


def test_merge_dedupe():
    merged = merge_hybrid_snippets(
        [{"doc_id": "a", "title": "A"}],
        [{"doc_id": "a", "title": "A2"}, {"doc_id": "b", "title": "B"}],
        top_k=3,
    )
    assert len(merged) == 2


if __name__ == "__main__":
    test_extract_kb_and_issue()
    test_boost_kb_id_first()
    test_merge_dedupe()
    print("test_catalog_hybrid OK")
