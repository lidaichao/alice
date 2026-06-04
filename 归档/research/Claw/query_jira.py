#!/usr/bin/env python3
"""
查询 JIRA 中指定用户近两周的工作内容
"""
import requests
import json
from datetime import datetime, timedelta

# JIRA 配置
JIRA_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_TOKEN = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

# 查询参数
assignee = "彭家俊"
start_date = "2026-05-12"  # 近两周
end_date = "2026-05-26"

# 构造 JQL 查询
jql = f'assignee = "{assignee}" AND updated >= {start_date} ORDER BY updated DESC'

# 设置请求头
headers = {
    "Authorization": f"Bearer {JIRA_TOKEN}",
    "Content-Type": "application/json"
}

# 发送请求
url = f"{JIRA_URL}/rest/api/2/search"
params = {
    "jql": jql,
    "maxResults": 100,
    "fields": "key,summary,status,assignee,updated,created,progress,timeoriginalestimate,timespent"
}

try:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    print(f"查询结果：共找到 {data.get('total', 0)} 个任务\n")
    print("=" * 80)
    
    for issue in data.get('issues', []):
        key = issue['key']
        summary = issue['fields']['summary']
        status = issue['fields']['status']['name']
        updated = issue['fields']['updated'][:10]  # 只取日期部分
        
        print(f"\n[{key}] {summary}")
        print(f"  状态: {status}")
        print(f"  更新时间: {updated}")
        print(f"  链接: {JIRA_URL}/browse/{key}")
    
    print("\n" + "=" * 80)
    print(f"总计: {len(data.get('issues', []))} 个任务")
    
except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"响应内容: {e.response.text}")
