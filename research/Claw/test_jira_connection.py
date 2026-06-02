#!/usr/bin/env python3
"""
测试 JIRA 连接并获取基本信息
"""
import requests
import json

# JIRA 配置
JIRA_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_TOKEN = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

# 设置请求头
headers = {
    "Authorization": f"Bearer {JIRA_TOKEN}",
    "Content-Type": "application/json"
}

print("=" * 80)
print("测试 1: 检查 JIRA 连接")
print("=" * 80)

try:
    # 测试连接 - 获取服务器信息
    response = requests.get(f"{JIRA_URL}/rest/api/2/serverInfo", headers=headers, timeout=10)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"JIRA 版本: {data.get('version')}")
        print(f"版本号: {data.get('versionNumbers')}")
    else:
        print(f"响应内容: {response.text[:500]}")
except Exception as e:
    print(f"连接失败: {e}")

print("\n" + "=" * 80)
print("测试 2: 搜索最近更新的任务（不限用户）")
print("=" * 80)

try:
    # 搜索最近的任务
    params = {
        "jql": "updated >= 2026-05-01 ORDER BY updated DESC",
        "maxResults": 5,
        "fields": "key,summary,assignee,updated"
    }
    response = requests.get(f"{JIRA_URL}/rest/api/2/search", headers=headers, params=params, timeout=30)
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"找到 {data.get('total', 0)} 个任务")
        print("\n前 5 个任务:")
        for issue in data.get('issues', [])[:5]:
            key = issue['key']
            summary = issue['fields']['summary']
            assignee = issue['fields'].get('assignee')
            assignee_name = assignee['displayName'] if assignee else '未分配'
            updated = issue['fields']['updated'][:10]
            print(f"  [{key}] {summary} - 负责人: {assignee_name} - 更新: {updated}")
    else:
        print(f"响应内容: {response.text[:500]}")
except Exception as e:
    print(f"查询失败: {e}")

print("\n" + "=" * 80)
print("测试 3: 尝试查找用户 '彭家俊'")
print("=" * 80)

try:
    # 搜索用户
    params = {
        "username": "彭家俊"
    }
    response = requests.get(f"{JIRA_URL}/rest/api/2/user", headers=headers, params=params, timeout=10)
    print(f"状态码: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"找到用户: {data.get('displayName')} ({data.get('name')})")
    else:
        print(f"未找到用户或权限不足")
        print(f"响应: {response.text[:500]}")
except Exception as e:
    print(f"查询失败: {e}")

print("\n" + "=" * 80)
print("测试 4: 使用 assignee 用户名格式查询")
print("=" * 80)

# 尝试常见的用户名格式
possible_usernames = ["pengjiajun", "peng.jiajun", "彭家俊", "PENGJIAJUN"]

for username in possible_usernames:
    try:
        params = {
            "jql": f'assignee = "{username}" AND updated >= 2026-05-01',
            "maxResults": 1,
            "fields": "key,summary"
        }
        response = requests.get(f"{JIRA_URL}/rest/api/2/search", headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            count = data.get('total', 0)
            print(f"用户名 '{username}': 找到 {count} 个任务")
            if count > 0:
                print(f"  ✓ 这个用户名格式可能是正确的！")
                break
        else:
            print(f"用户名 '{username}': 查询失败 (状态码 {response.status_code})")
    except Exception as e:
        print(f"用户名 '{username}': 异常 - {e}")
