import requests, socket, time, subprocess

print("=" * 55)
print("  代理深度排查  %s" % time.strftime("%H:%M:%S"))
print("=" * 55)

# 1. DNS 解析
print("\n--- 1. DNS 解析 ---")
for host in ["www.google.com", "api.notion.com", "www.googleapis.com"]:
    try:
        ip = socket.gethostbyname(host)
        print("  %-25s → %s" % (host, ip))
    except Exception as e:
        print("  %-25s → 解析失败: %s" % (host, e))

# 2. TCP 直连 Google (不过代理)
print("\n--- 2. TCP 直连测试 (443端口) ---")
for host, port in [("www.google.com", 443), ("api.notion.com", 443), ("127.0.0.1", 7897)]:
    try:
        s = socket.socket()
        s.settimeout(5)
        t0 = time.time()
        s.connect((host, port))
        t = time.time() - t0
        s.close()
        print("  %-25s:443  ✅ %.2fs" % (host, t))
    except Exception as e:
        print("  %-25s:443  ❌ %s" % (host, str(e)[:40]))

# 3. 经过Clash的HTTP请求
print("\n--- 3. 经代理HTTP请求 ---")
proxies = {"https": "http://127.0.0.1:7897", "http": "http://127.0.0.1:7897"}
for name, url in [("Google首页", "https://www.google.com"), ("Google API", "https://www.googleapis.com/discovery/v1/apis")]:
    t0 = time.time()
    try:
        r = requests.get(url, proxies=proxies, timeout=10)
        t = time.time() - t0
        print("  %-20s ✅ %.2fs  HTTP %d  (%d bytes)" % (name, t, r.status_code, len(r.text)))
    except Exception as e:
        t = time.time() - t0
        err = str(e)[:80]
        print("  %-20s ❌ %.2fs  %s" % (name, t, err))

# 4. Notion 直连 + 代理对比
print("\n--- 4. Notion API ---")
hd = {"Authorization": "Bearer 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", "Notion-Version": "2025-09-03"}
for mode, px in [("直连", None), ("走代理", proxies)]:
    t0 = time.time()
    try:
        kw = {"timeout": 10, "headers": hd}
        if px: kw["proxies"] = px
        r = requests.get("https://api.notion.com/v1/users/me", **kw)
        t = time.time() - t0
        print("  %-6s ✅ %.2fs  HTTP %d" % (mode, t, r.status_code))
    except Exception as e:
        t = time.time() - t0
        print("  %-6s ❌ %.2fs  %s" % (mode, t, str(e)[:50]))

# 5. Clash健康检查
print("\n--- 5. Clash 存活检测 ---")
for path in ["", "/version", "/configs", "/proxies"]:
    try:
        r = requests.get("http://127.0.0.1:9097" + path, timeout=3)
        print("  /%-14s HTTP %d" % (path, r.status_code))
    except:
        print("  /%-14s ❌ 不可达" % path)
