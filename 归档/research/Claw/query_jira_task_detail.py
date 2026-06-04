#!/usr/bin/env python3
"""
查询 JIRA 任务的详细信息，包括代码提交、评论、附件等
"""
import requests
import json

# JIRA 配置
JIRA_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_TOKEN = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

# 任务 Key
ISSUE_KEY = "CT-11074"

# 设置请求头
headers = {
    "Authorization": f"Bearer {JIRA_TOKEN}",
    "Content-Type": "application/json"
}

print(f"=" * 80)
print(f"查询任务：{ISSUE_KEY}")
print(f"=" * 80)

try:
    # 1. 获取任务基本信息
    print(f"\n📋 任务基本信息：\n")
    response = requests.get(
        f"{JIRA_URL}/rest/api/2/issue/{ISSUE_KEY}",
        headers=headers,
        params={"fields": "key,summary,status,assignee,reporter,created,updated,description,issuetype,priority,components,fixVersions,comment,attachment"},
        timeout=30
    )
    response.raise_for_status()
    issue = response.json()
    fields = issue['fields']
    
    print(f"任务 Key: {issue['key']}")
    print(f"标题: {fields['summary']}")
    print(f"状态: {fields['status']['name']}")
    print(f"类型: {fields['issuetype']['name']}")
    print(f"优先级: {fields.get('priority', {}).get('name', '无')}")
    print(f"负责人: {fields.get('assignee', {}).get('displayName', '未分配')}")
    print(f"报告人: {fields.get('reporter', {}).get('displayName', '未知')}")
    print(f"创建时间: {fields['created'][:19]}")
    print(f"更新时间: {fields['updated'][:19]}")
    
    if fields.get('components'):
        print(f"组件: {', '.join([c['name'] for c in fields['components']])}")
    
    if fields.get('fixVersions'):
        print(f"修复版本: {', '.join([v['name'] for v in fields['fixVersions']])}")
    
    # 描述
    if fields.get('description'):
        print(f"\n📝 描述:\n{fields['description'][:500]}...")
    
    # 2. 获取评论
    comments = fields.get('comment', {}).get('comments', [])
    if comments:
        print(f"\n💬 评论 ({len(comments)} 条)：\n")
        for idx, comment in enumerate(comments[-5:], 1):  # 只显示最后 5 条
            author = comment['author']['displayName']
            created = comment['created'][:19]
            body = comment['body'][:300]
            print(f"{idx}. {author} ({created}):")
            print(f"   {body}")
            if len(comment['body']) > 300:
                print(f"   ...")
            print()
    
    # 3. 获取附件
    attachments = fields.get('attachment', [])
    if attachments:
        print(f"\n📎 附件 ({len(attachments)} 个)：\n")
        for att in attachments[-10:]:  # 只显示最后 10 个
            print(f"- {att['filename']} ({att['size']} bytes)")
            print(f"  下载: {att['content']}")
    
    # 4. 查询开发信息（如果有 Git 提交、代码审查等）
    print(f"\n" + "=" * 80)
    print("🔍 查询开发相关信息...")
    print("=" * 80)
    
    # 尝试获取变更日志
    print(f"\n📜 变更历史：\n")
    response = requests.get(
        f"{JIRA_URL}/rest/api/2/issue/{ISSUE_KEY}/changelog",
        headers=headers,
        timeout=30
    )
    if response.status_code == 200:
        changelog = response.json()
        histories = changelog.get('values', [])
        print(f"共 {len(histories)} 条变更记录\n")
        
        for hist in histories[-10:]:  # 只显示最后 10 条
            author = hist['author']['displayName']
            created = hist['created'][:19]
            print(f"[{created}] {author}:")
            for item in hist['items']:
                field = item['field']
                from_val = item.get('fromString', '(空)')
                to_val = item.get('toString', '(空)')
                print(f"  - {field}: {from_val} → {to_val}")
            print()
    else:
        print(f"无法获取变更历史 (状态码: {response.status_code})")
    
    # 5. 尝试查找 Git 提交信息（通过 JIRA 的开发面板 API）
    print(f"\n" + "=" * 80)
    print("🔗 查询关联的 Git 提交...")
    print("=" * 80)
    
    # 尝试开发信息 API (JIRA DevOps 集成)
    dev_endpoints = [
        f"/rest/dev-status/1.0/issue/detail?issueId={issue['id']}&applicationType=github&dataType=pullrequest",
        f"/rest/dev-status/1.0/issue/detail?issueId={issue['id']}&applicationType=git&dataType=repository",
        f"/rest/git/1.0/issues/{ISSUE_KEY}/repositories",
        f"/rest/aiogit/1.0/details/{ISSUE_KEY}",
    ]
    
    for endpoint in dev_endpoints:
        try:
            response = requests.get(f"{JIRA_URL}{endpoint}", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"\n✅ 找到开发信息 ({endpoint}):")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:1000])
            else:
                print(f"❌ {endpoint} - 状态码: {response.status_code}")
        except Exception as e:
            print(f"❌ {endpoint} - 异常: {e}")
    
except requests.exceptions.RequestException as e:
    print(f"❌ 请求失败: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"响应内容: {e.response.text[:1000]}")
