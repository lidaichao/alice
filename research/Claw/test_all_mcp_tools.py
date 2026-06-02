#!/usr/bin/env python3
"""
测试 wecom-jira-bridge MCP Server 的所有 8 个工具
"""
import os

# ⚠️ 先设置环境变量，再导入模块（避免模块导入时使用错误的环境变量）
os.environ["JIRA_BASE_URL"] = "http://ctjira1.lmdgame.com:8080"
os.environ["JIRA_PAT"] = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"
os.environ["SVN_URL"] = "https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3"
os.environ["SVN_USERNAME"] = "lidaichao"
os.environ["SVN_PASSWORD"] = "123456"
os.environ["NO_PROXY"] = "*"

import sys

# 添加 wecom-jira-bridge 到路径
sys.path.insert(0, "H:/workbuddy/jira/wecom-jira-bridge")

# 导入所有工具（此时环境变量已设置，模块会用正确的配置初始化）
print("正在导入 jira_mcp_server...")
try:
    from jira_mcp_server import (
        jira_test_connection,
        jira_list_projects,
        jira_search,
        jira_my_open_issues,
        jira_this_week_issues,
        jira_get_issue,
        jira_get_commits,
        jira_get_svn_diff
    )
    print("✅ 导入成功")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 80)
print("MCP Server 工具测试")
print("=" * 80)

# 测试 1: jira_test_connection
print("\n【测试 1/8】jira_test_connection() - 连通性测试")
try:
    result = jira_test_connection()
    print(f"✅ 成功:\n{result}\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 2: jira_list_projects
print("\n【测试 2/8】jira_list_projects() - 列出项目")
try:
    result = jira_list_projects()
    print(f"✅ 成功:\n{result[:500]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 3: jira_search
print("\n【测试 3/8】jira_search(jql) - JQL 查询")
try:
    # 注意：JQL 中状态名是中文，需要用双引号，但整个字符串用单引号包围
    result = jira_search('project = CT ORDER BY priority DESC')
    print(f"✅ 成功:\n{result[:800]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 4: jira_my_open_issues
print("\n【测试 4/8】jira_my_open_issues() - 我的未完成任务")
try:
    result = jira_my_open_issues()
    print(f"✅ 成功:\n{result[:500]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 5: jira_this_week_issues
print("\n【测试 5/8】jira_this_week_issues() - 本周未完成任务")
try:
    result = jira_this_week_issues()
    print(f"✅ 成功:\n{result[:500]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 6: jira_get_issue
print("\n【测试 6/8】jira_get_issue(issue_key) - 单任务详情")
try:
    result = jira_get_issue("CT-11074")
    print(f"✅ 成功:\n{result[:500]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 7: jira_get_commits
print("\n【测试 7/8】jira_get_commits(issue_key) - 关联提交信息")
try:
    result = jira_get_commits("CT-11074")
    print(f"✅ 成功:\n{result[:800]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试 8: jira_get_svn_diff
print("\n【测试 8/8】jira_get_svn_diff(issue_key, max_files) - 完整代码 Diff")
try:
    result = jira_get_svn_diff("CT-11074", max_files=3)
    print(f"✅ 成功:\n{result[:800]}...\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
