"""E1 — chat_orchestrator / plugin_gateway 单元测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chat_orchestrator import (
    clean_chat_messages,
    last_user_message_text,
    extract_issue_keys,
    prepare_orchestrator_context,
    iter_preflight_sse,
)
import plugin_gateway


def test_clean_multipart_message():
    msgs = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "你好"}],
        }
    ]
    out = clean_chat_messages(msgs)
    assert out[0]["content"] == "你好"


def test_extract_issue_keys():
    keys = extract_issue_keys("查 CT-10888 和 PROJ-1")
    assert "CT-10888" in keys


def test_dangerous_preflight_terminates():
    ctx = prepare_orchestrator_context(
        [{"role": "user", "content": "rm -rf /tmp"}],
        {"deepseek_model": "deepseek-chat", "deepseek_key": "x"},
        {},
        {},
        "",
        "FULL_SET",
        [],
        deepseek_url="http://test",
        http_post=lambda *a, **k: None,
        jira_client=None,
        exec_search_docs_catalog=lambda a: "",
        exec_read_specific_doc=lambda a: "",
        build_weekly_jira_snapshot=lambda *a: ("", ""),
        iter_jira_structured_read_lane=lambda *a: iter(()),
    )
    chunks = list(iter_preflight_sse(ctx))
    assert ctx.terminated
    assert any(b"[DONE]" in c for c in chunks)
    body = b"".join(chunks).decode("utf-8", errors="replace")
    assert "拦截" in body


def test_heuristic_drafts_count():
    items = plugin_gateway.heuristic_issues_drafts("创建5个关于登录的 Jira 任务")
    assert len(items) == 5
    assert items[0]["projectKey"] == "CT"


def test_collect_draft_chunks_event():
    chunks = plugin_gateway.collect_draft_sse_chunks(
        "帮我草拟 2 个 UI 优化任务",
        issues_list=[
            {"summary": "A", "projectKey": "CT", "issueType": "Task"},
        ],
    )
    assert chunks
    text = chunks[0].decode("utf-8")
    assert "draft_card" in text


if __name__ == "__main__":
    test_clean_multipart_message()
    test_extract_issue_keys()
    test_dangerous_preflight_terminates()
    test_heuristic_drafts_count()
    test_collect_draft_chunks_event()
    print("test_chat_orchestrator: OK")
