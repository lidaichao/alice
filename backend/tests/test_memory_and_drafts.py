"""浅层记忆 + 草稿箱单测"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_memory_persist(tmp_path, monkeypatch):
    import memory_manager as mm

    mem_file = tmp_path / "shallow_memory.json"
    monkeypatch.setattr(mm, "_MEMORY_FILE", str(mem_file))
    entry = mm.add_memory_entry("以后所有的前端 Bug 都指派给李四")
    assert entry["text"]
    loaded = mm.get_all_memory()
    assert any("李四" in e["text"] for e in loaded)
    block = mm.format_memory_for_prompt()
    assert "李四" in block
    parsed = mm.parse_remember_instruction("请记住，以后所有的前端 Bug 都指派给李四。")
    assert parsed and "李四" in parsed


def test_draft_box(tmp_path, monkeypatch):
    import jira_operation_manager as jom

    draft_file = tmp_path / "jira_draft_box.json"
    ops_file = tmp_path / "operations.json"
    monkeypatch.setattr(jom, "_DRAFTS_FILE", str(draft_file))
    monkeypatch.setattr(jom, "_OPS_FILE", str(ops_file))
    monkeypatch.setattr(jom, "_DATA_DIR", str(tmp_path))
    jom._draft_box.clear()
    jom._store.clear()

    items = [
        {"summary": "UI 优化 1", "projectKey": "CT", "issueType": "Task"},
        {"summary": "UI 优化 2", "projectKey": "CT", "issueType": "Task"},
    ]
    draft = jom.create_issues_draft(items, source_text="草拟 2 条")
    assert draft["id"].startswith("draft-")
    payload = jom.build_draft_tool_response(draft)
    assert payload["status"] == "draft_required"
    assert len(payload["items"]) == 2
    assert os.path.isfile(draft_file)

    op = jom.submit_draft_to_operation(draft["id"])
    assert op["id"].startswith("jira-op-")
    assert op["status"] == "awaiting_confirmation"
