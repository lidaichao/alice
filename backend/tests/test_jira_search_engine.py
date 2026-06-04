"""jira_search_engine 单元测试"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jira_search_engine import (
    JiraSearchQuery,
    build_resolved_jql,
    analyze_issues,
    parse_query_from_natural_language,
    validate_recovery_jql,
    is_jira_structured_read_query,
    format_search_result_for_llm,
)
from jira_runtime_config import JiraRuntimeConfig, load_jira_runtime_config


def test_build_jql_project_and_unresolved():
    cfg = JiraRuntimeConfig(default_project_keys=["CT"], done_status_keywords=["完成", "Done"])
    q = JiraSearchQuery(project_key="CT", unresolved_only=True)
    out = build_resolved_jql(q, cfg)
    assert "project" in out["jql"]
    assert "CT" in out["jql"]
    assert "status NOT IN" in out["jql"]


def test_build_jql_assignee_or_owner():
    cfg = JiraRuntimeConfig(
        default_project_keys=["CT"],
        owner_field_candidates=["任务负责人"],
        projects={"CT": __import__("jira_runtime_config", fromlist=["ProjectJiraConfig"]).ProjectJiraConfig("CT", ["customfield_10130"])},
    )
    q = JiraSearchQuery(project_key="CT", assignees=["zhangsan"])
    out = build_resolved_jql(q, cfg, resolved_users=[{"name": "zhangsan", "displayName": "张三"}])
    assert "assignee" in out["jql"] or "zhangsan" in out["jql"]


def test_analyze_issues():
    issues = [
        {"key": "CT-1", "status": "完成", "assignee": "A"},
        {"key": "CT-2", "status": "进行中", "assignee": "B"},
    ]
    a = analyze_issues(issues)
    assert a["total"] == 2
    assert "summary" in a
    assert a["completionRate"] == 50


def test_parse_natural_language():
    cfg = load_jira_runtime_config({"jira_projects": "CT"})
    q = parse_query_from_natural_language("统计张三本周未完成的 Jira 任务", cfg)
    assert q.unresolved_only
    assert "张三" in q.assignees
    q2 = parse_query_from_natural_language("帮我查一下本周需要完成的任务有哪些", cfg)
    assert q2.unresolved_only
    assert not q2.assignees or q2.assignee_is_current_user
    q3 = parse_query_from_natural_language("和球员系统属性设计有关的 Jira 任务", cfg)
    assert "球员" in q3.text or "系统" in q3.text
    assert not q3.assignees
    q4 = parse_query_from_natural_language("项目 CT 有哪些进行中的 bug", cfg)
    q5 = parse_query_from_natural_language("本周需要完成的任务有哪些", cfg)
    assert q5.assignee_is_current_user, "本周待办应默认 currentUser"
    assert "完成" not in (q5.statuses or []), "需要完成不应匹配完成态"
    assert q4.project_key == "CT"
    assert q4.issue_types == ["Bug"]


def test_validate_recovery_jql():
    ok = validate_recovery_jql('project = "CT" AND assignee = "u1"', "")
    assert ok["valid"]
    bad = validate_recovery_jql("ORDER BY updated", "")
    assert not bad["valid"]


def test_is_structured_read():
    assert is_jira_structured_read_query("统计本周 CT 未完成任务", "jira_query")
    assert not is_jira_structured_read_query("CT-1 提交了什么代码", "jira_query")


def test_should_not_force_structured_on_commit_or_single_key():
    from jira_search_engine import should_force_jira_structured_read

    assert not should_force_jira_structured_read(
        "CT-10859 这个任务今天程序提交了什么", "jira_query", ""
    )
    assert not should_force_jira_structured_read("CT-10859 详情", "jira_query", "")
    assert should_force_jira_structured_read("统计本周 CT 未完成任务", "jira_query", "")


def test_empty_result_prompt():
    r = {"jql": "project=CT", "issues": [], "analysis": analyze_issues([])}
    text = format_search_result_for_llm(r)
    assert "禁止编造" in text


if __name__ == "__main__":
    test_build_jql_project_and_unresolved()
    test_build_jql_assignee_or_owner()
    test_analyze_issues()
    test_parse_natural_language()
    test_validate_recovery_jql()
    test_is_structured_read()
    test_empty_result_prompt()
    print("All jira_search_engine tests passed")
