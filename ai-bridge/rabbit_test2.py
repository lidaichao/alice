"""兔子测试2: 捕获所有日志"""
import subprocess, time, urllib.request, json, sys, threading

proc = subprocess.Popen(
    [r"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe", "-u", "ai_bridge.py"],
    stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    text=True, cwd=r"H:\workbuddy\alice\ai-bridge"
)

stderr_lines = []
def read_stderr():
    for line in proc.stderr:
        stderr_lines.append(line)
        sys.stderr.write("[STDERR] " + line)
t = threading.Thread(target=read_stderr, daemon=True)
t.start()

# Drain stdout
def drain_stdout():
    for line in proc.stdout:
        pass
threading.Thread(target=drain_stdout, daemon=True).start()

time.sleep(4)

# Send request
try:
    data = json.dumps({"messages": [{"role": "user", "content": "CT-10888这个任务中最近的代码提交有什么内容，摘要说明下。"}]}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:9099/v1/chat/completions", data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        answer = []
        for i, line in enumerate(resp):
            d = line.decode('utf-8', errors='replace').strip()
            if d and 'delta' in d:
                try:
                    c = json.loads(d.replace('data: ','').strip())
                    ct = c.get('choices',[{}])[0].get('delta',{}).get('content','')
                    if ct: answer.append(ct)
                except: pass
            if i > 200: break
        print("ANSWER:", ''.join(answer)[:600])
except Exception as e:
    print("REQUEST ERROR:", e)

time.sleep(1)
print("\n=== TRACE LOGS ===")
for line in stderr_lines:
    if 'ReAct-TRACE' in line or 'DSML' in line or 'Leak' in line or 'RABBIT' in line or 'Step' in line or 'Tool_calls' in line or 'finish_reason' in line or 'direct-output' in line:
        print(line.strip())

proc.terminate()
