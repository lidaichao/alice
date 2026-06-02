#!/usr/bin/env python3
"""
最简单的 jira_search 测试
"""
import os

# 先设置环境变量
os.environ['JIRA_BASE_URL'] = 'http://ctjira1.lmdgame.com:8080'
os.environ['JIRA_PAT'] = 'NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG'
os.environ['NO_PROXY'] = '*'

import sys
sys.path.insert(0, 'H:/workbuddy/jira/wecom-jira-bridge')

# 导入
print("导入 jira_mcp_server...")
from jira_mcp_server import jira_search
print("✅ 导入成功")

# 测试 1：简单 JQL
print("\n测试 1: jira_search('key = CT-11074')")
try:
    result = jira_search('key = CT-11074')
    print("✅ 成功:", result[:200])
except Exception as e:
    print("❌ 失败:", e)
    import traceback
    traceback.print_exc()

# 测试 2：复杂 JQL
print("\n\n测试 2: jira_search('project = CT ORDER BY priority DESC')")
try:
    result = jira_search('project = CT ORDER BY priority DESC')
    print("✅ 成功:", result[:200])
except Exception as e:
    print("❌ 失败:", e)
    import traceback
    traceback.print_exc()

print("\n测试完成")
