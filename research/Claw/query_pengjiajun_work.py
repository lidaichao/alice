#!/usr/bin/env python3
"""
查询彭家俊（pengjiajun）近两周的工作内容
"""
import requests
import json
from datetime import datetime

# JIRA 配置
JIRA_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_TOKEN = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

# 查询参数
assignee_username = "pengjiajun"
start_date = "2026-05-12"  # 近两周
end_date = "2026-05-26"

# 构造 JQL 查询 - 查询创建或更新在近两周内的任务
jql = f'assignee = "{assignee_username}" AND (created >= {start_date} OR updated >= {start_date}) ORDER BY updated DESC'

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
    "fields": "key,summary,status,assignee,updated,created,description,issuetype,priority,progress,timeoriginalestimate,timespent,aggregatetimespent"
}

try:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    total = data.get('total', 0)
    
    print(f"查询结果：彭家俊 近两周工作内容")
    print(f"查询时间范围：{start_date} ~ {end_date}")
    print(f"找到任务总数：{total}\n")
    print("=" * 100)
    
    if total == 0:
        print("\n未找到符合条件的任务。")
        print("\n可能的原因：")
        print("1. 任务创建和更新时间都不在最近两周内")
        print("2. 尝试扩大时间范围或检查用户名")
    else:
        # 按状态分组统计
        status_count = {}
        for issue in data.get('issues', []):
            status = issue['fields']['status']['name']
            status_count[status] = status_count.get(status, 0) + 1
        
        print(f"\n📊 任务状态统计：")
        for status, count in sorted(status_count.items(), key=lambda x: -x[1]):
            print(f"  {status}: {count} 个")
        
        print("\n" + "=" * 100)
        print("\n📋 任务详细列表（方便复制）：\n")
        
        for idx, issue in enumerate(data.get('issues', []), 1):
            key = issue['key']
            summary = issue['fields']['summary']
            status = issue['fields']['status']['name']
            issue_type = issue['fields']['issuetype']['name']
            priority = issue['fields'].get('priority', {}).get('name', '无')
            created = issue['fields']['created'][:10]
            updated = issue['fields']['updated'][:10]
            
            # 计算工时
            time_original = issue['fields'].get('timeoriginalestimate', 0) or 0
            time_spent = issue['fields'].get('timespent', 0) or 0
            
            time_original_hours = time_original / 3600 if time_original else 0
            time_spent_hours = time_spent / 3600 if time_spent else 0
            
            print(f"{idx}. [{key}] {summary}")
            print(f"   类型: {issue_type} | 优先级: {priority} | 状态: {status}")
            print(f"   创建: {created} | 更新: {updated}")
            if time_original_hours > 0 or time_spent_hours > 0:
                print(f"   预估工时: {time_original_hours:.1f}h | 实际工时: {time_spent_hours:.1f}h")
            print(f"   链接: {JIRA_URL}/browse/{key}")
            print()
    
    print("=" * 100)
    
    # 输出纯文本格式（方便复制）
    print("\n\n📄 纯文本格式（方便复制到邮件/文档）：\n")
    print(f"彭家俊 近两周工作内容（{start_date} ~ {end_date}）")
    print(f"共 {total} 个任务\n")
    
    for idx, issue in enumerate(data.get('issues', []), 1):
        key = issue['key']
        summary = issue['fields']['summary']
        status = issue['fields']['status']['name']
        print(f"{idx}. {key} - {summary} [{status}]")
    
except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"响应内容: {e.response.text[:1000]}")
