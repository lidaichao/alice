"""兔子测试脚本：启动服务 + 发请求 + 捕获所有日志"""
import subprocess, time, urllib.request, json, sys, threading

# Start ai_bridge as subprocess, capturing stderr
proc = subprocess.Popen(
    [r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe", "ai_bridge.py"],
    stderr=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    cwd=r"H:\workbuddy\alice\ai-bridge"
)

# Collect stderr in background
stderr_lines = []
def read_stderr():
    for line in proc.stderr:
        stderr_lines.append(line)
        sys.stderr.write(line)

t = threading.Thread(target=read_stderr, daemon=True)
t.start()

# Wait for server to start
time.sleep(4)

# Send test query
try:
    data = json.dumps({"messages": [{"role": "user", "content": "CT-10888这个任务中最近的代码提交有什么内容，摘要说明下。"}]}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:9099/v1/chat/completions", data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        answer = []
        for line in resp:
            d = line.decode('utf-8', errors='replace')
            if 'delta' in d:
                try:
                    c = json.loads(d.replace('data: ','').strip())
                    ct = c.get('choices',[{}])[0].get('delta',{}).get('content','')
                    if ct: answer.append(ct)
                except: pass
        print("RESPONSE:", ''.join(answer)[:600])
except Exception as e:
    print("REQUEST ERROR:", e)

time.sleep(1)

# Show Rabbit interceptor
print("\n=== RABBIT INTERCEPTOR ===")
for line in stderr_lines:
    if 'RABBIT' in line or 'INTERCEPTOR' in line or 'MSG [' in line or 'Total messages' in line or '=====' in line:
        print(line, end='')

# Also show DSML / tool / ReAct logs
print("\n=== REQUEST-RELATED LOGS ===")
for line in stderr_lines:
    if any(kw in line for kw in ['ReAct', 'DSML', 'Tool_calls', 'Step', 'tool', 'DEBUG-FINAL']):
        print(line, end='')

proc.terminate()
