import requests, time

tests = [
    ("DeepSeek 直连", "https://api.deepseek.com/v1/models", None, {}),
    ("Google 代理(localhost)", "https://www.googleapis.com/discovery/v1/apis",
     {"https": "http://127.0.0.1:7897", "http": "http://127.0.0.1:7897"}, {}),
    ("Google 代理(LAN)", "https://www.googleapis.com/discovery/v1/apis",
     {"https": "http://192.168.72.95:7897", "http": "http://192.168.72.95:7897"}, {}),
    ("Notion 直连", "https://api.notion.com/v1/users/me", None,
     {"Authorization": "Bearer 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", "Notion-Version": "2025-09-03"}),
]

for name, url, proxies, headers in tests:
    t0 = time.time()
    try:
        kw = {"timeout": 10}
        if proxies: kw["proxies"] = proxies
        if headers: kw["headers"] = headers
        r = requests.get(url, **kw)
        t1 = time.time()
        print("%-22s: %.2fs | HTTP %d" % (name, t1-t0, r.status_code))
    except Exception as e:
        print("%-22s: 失败 (%s)" % (name, str(e)[:60]))
