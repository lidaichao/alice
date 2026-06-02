#!/usr/bin/env python3
"""
测试 jira_get_commits 和 jira_get_svn_diff 工具
查询 CT-11074 的代码提交和 diff
"""
import sys
import os

# 添加 wecom-jira-bridge 到路径
sys.path.insert(0, "H:/workbuddy/2026-05-26-00-26-09/wecom-jira-bridge")

# 设置环境变量
os.environ["JIRA_BASE_URL"] = "http://ctjira1.lmdgame.com:8080"
os.environ["JIRA_PAT"] = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"
os.environ["NO_PROXY"] = "*"
os.environ["SVN_URL"] = "https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3"
os.environ["SVN_USERNAME"] = "lidaichao"
os.environ["SVN_PASSWORD"] = "123456"

from jira_mcp_server import jira_get_commits, jira_get_svn_diff

ISSUE_KEY = "CT-11074"

print("=" * 80)
print(f"测试 1: jira_get_commits({ISSUE_KEY})")
print("=" * 80)
print("\n功能：获取提交信息、文件清单、增删统计（via FishEye API）\n")

try:
    result = jira_get_commits(ISSUE_KEY)
    print(result)
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print(f"测试 2: jira_get_svn_diff({ISSUE_KEY})")
print("=" * 80)
print("\n功能：获取完整代码 Diff（via SVN 直连）\n")

try:
    result = jira_get_svn_diff(ISSUE_KEY, max_files=5)
    print(result)
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
