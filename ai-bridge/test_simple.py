"""最小测试：发请求并读 SSE 流，打印所有行"""
import urllib.request, json

data = json.dumps({"messages": [{"role": "user", "content": "CT-10888这个任务中最近的代码提交有什么内容，摘要说明下。"}]}).encode('utf-8')
req = urllib.request.Request("http://127.0.0.1:9099/v1/chat/completions", data=data, headers={"Content-Type": "application/json; charset=utf-8"})

with urllib.request.urlopen(req, timeout=90) as resp:
    for i, line in enumerate(resp):
        d = line.decode('utf-8', errors='replace').strip()
        if d:
            print(d)
        if i > 100:
            print("... truncated")
            break
