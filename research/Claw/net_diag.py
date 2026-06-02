import requests, time, socket

tests = [
    # 国内直连
    ("DeepSeek API (直连)", "https://api.deepseek.com/v1/models", None),
    ("Jira (内网直连)", "http://ctjira1.lmdgame.com:8080", None),
    ("FishEye (内网直连)", "http://192.168.8.34:8060", None),
    # 需代理
    ("Google API (代理)", "https://www.googleapis.com/discovery/v1/apis",
     {"https": "http://127.0.0.1:7897", "http": "http://127.0.0.1:7897"}),
    ("Notion API (直连)", "https://api.notion.com/v1/users/me", None),
    # 代理存活检测
    ("Clash 端口 7897", "http://127.0.0.1:7897", None),
]

print("=" * 55)
print("  网络诊断  %s" % time.strftime("%H:%M:%S"))
print("=" * 55)

for name, url, proxies in tests:
    t0 = time.time()
    try:
        kw = {"timeout": 8}
        if proxies: kw["proxies"] = proxies
        r = requests.get(url, **kw)
        t = time.time() - t0
        icon = "✅" if r.status_code < 500 else "⚠️ "
        print("%-28s %s %.2fs  HTTP %d" % (name, icon, t, r.status_code))
    except Exception as e:
        t = time.time() - t0
        err = str(e)[:50]
        print("%-28s ❌ %.2fs  %s" % (name, t, err))

# DNS 测试
print("\n--- DNS ---")
for host in ["api.deepseek.com", "api.notion.com", "www.googleapis.com", "ctjira1.lmdgame.com"]:
    try:
        ip = socket.gethostbyname(host)
        print("  %-30s → %s" % (host, ip))
    except:
        print("  %-30s → 解析失败" % host)
