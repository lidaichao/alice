#!/usr/bin/env python3
"""
尝试多种方式查找 CT-11074 关联的 Git 提交
"""
import requests
import re

# JIRA 配置
JIRA_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_TOKEN = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

ISSUE_KEY = "CT-11074"

headers = {
    "Authorization": f"Bearer {JIRA_TOKEN}",
    "Content-Type": "application/json"
}

print("=" * 80)
print(f"查找 {ISSUE_KEY} 关联的 Git 提交")
print("=" * 80)

# 方法 1: 从 JIRA 评论中提取 Git commit hash
print("\n📝 方法 1: 从 JIRA 评论中提取 Git 信息...\n")

response = requests.get(
    f"{JIRA_URL}/rest/api/2/issue/{ISSUE_KEY}/comment",
    headers=headers,
    timeout=30
)

if response.status_code == 200:
    data = response.json()
    comments = data.get('comments', [])
    
    # 正则表达式匹配 Git commit hash (7-40位十六进制)
    commit_pattern = r'\b([a-f0-9]{7,40})\b'
    # 也匹配常见的 Git 提交信息格式
    git_patterns = [
        r'commit\s+([a-f0-9]{7,40})',
        r'git\s+commit\s+([a-f0-9]{7,40})',
        r'https?://.*?/commit/([a-f0-9]{7,40})',
        r'\[([a-f0-9]{7,40})\]',
    ]
    
    found_commits = []
    
    for comment in comments:
        body = comment['body']
        author = comment['author']['displayName']
        created = comment['created'][:19]
        
        # 搜索所有 pattern
        for pattern in git_patterns:
            matches = re.finditer(pattern, body, re.IGNORECASE)
            for match in matches:
                commit_hash = match.group(1)
                found_commits.append({
                    'hash': commit_hash,
                    'author': author,
                    'date': created,
                    'context': body[max(0, match.start()-50):match.end()+50]
                })
    
    if found_commits:
        print(f"✅ 在评论中找到 {len(found_commits)} 个可能的 Git commit:\n")
        for idx, commit in enumerate(found_commits, 1):
            print(f"{idx}. Commit: {commit['hash']}")
            print(f"   作者: {commit['author']} ({commit['date']})")
            print(f"   上下文: ...{commit['context']}...")
            print()
    else:
        print("❌ 评论中未找到 Git commit 信息")
else:
    print(f"❌ 无法获取评论 (状态码: {response.status_code})")

# 方法 2: 尝试通过 JIRA 的 Git 插件 API
print("\n" + "=" * 80)
print("📦 方法 2: 尝试 JIRA Git 插件 API...")
print("=" * 80)

git_plugin_endpoints = [
    f"/rest/gitplugin/1.0/issues/{ISSUE_KEY}/commits",
    f"/rest/git/1.0/issues/{ISSUE_KEY}/changesets",
    f"/rest/bitbucket/1.0/issue/{ISSUE_KEY}/commits",
    f"/rest/stash/1.0/issue/{ISSUE_KEY}/commits",
]

for endpoint in git_plugin_endpoints:
    try:
        response = requests.get(f"{JIRA_URL}{endpoint}", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ {endpoint} - 找到数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
            break
        else:
            print(f"❌ {endpoint} - 状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ {endpoint} - 异常: {e}")

# 方法 3: 检查是否有智慧提交（Wisdom Commit）或工作日志
print("\n" + "=" * 80)
print("⏱️ 方法 3: 检查工作日志...")
print("=" * 80)

response = requests.get(
    f"{JIRA_URL}/rest/api/2/issue/{ISSUE_KEY}/worklog",
    headers=headers,
    timeout=30
)

if response.status_code == 200:
    data = response.json()
    worklogs = data.get('worklogs', [])
    
    if worklogs:
        print(f"\n✅ 找到 {len(worklogs)} 条工作日志:\n")
        for wl in worklogs[-10:]:
            author = wl['author']['displayName']
            created = wl['created'][:19]
            time_spent = wl.get('timeSpent', 'N/A')
            comment = wl.get('comment', '')[:200]
            
            print(f"- {author} ({created}) - 工时: {time_spent}")
            if comment:
                print(f"  备注: {comment}")
            print()
    else:
        print("\n❌ 没有工作日志")
else:
    print(f"\n❌ 无法获取工作日志 (状态码: {response.status_code})")

print("\n" + "=" * 80)
print("💡 建议:")
print("=" * 80)
print("""
如果以上方法都没有找到 Git 提交信息，可能的原因：
1. Git 仓库没有和 JIRA 集成
2. 开发者没有在提交信息中引用 JIRA 任务号 (CT-11074)
3. 使用了其他的代码管理系统 (如 Perforce, SVN)

请提供以下信息之一：
- Git 仓库地址和访问凭证
- Perforce (P4) 服务器地址
- 或者告诉我代码提交到了哪个系统/平台
""")
