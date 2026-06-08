import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from doc_content_extractor import build_skeleton_from_markdown, should_use_skeleton


def test_skeleton_mode():
    long_text = "# Title\n\n" + ("line\n" * 3000)
    assert should_use_skeleton(long_text)
    sk = build_skeleton_from_markdown(long_text, title="Title")
    assert "文档骨架模式" in sk
    assert "目录" in sk


if __name__ == "__main__":
    test_skeleton_mode()
    print("test_doc_content_extractor OK")
