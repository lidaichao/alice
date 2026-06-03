"""
E2E Agent Retrieval Test — 验证三刀修复后 Jira→FishEye→SVN 提交查询链路
用法: python test_agent_retrieval.py
前置: ai_bridge.py 已启动在 :9099
"""
import os, sys, json, requests

# ── 读取凭据 ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "global_config.json")

deepseek_key = os.getenv("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_API_KEY")

if not deepseek_key and os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    deepseek_key = cfg.get("DEEPSEEK_KEY", "")

if not deepseek_key:
    print("[FATAL] 未找到 DEEPSEEK_KEY，请检查 .env 或 global_config.json")
    sys.exit(1)

print(f"[INFO] 使用 DEEPSEEK_KEY: {deepseek_key[:12]}...")

# ── 模拟前端 Payload ─────────────────────────────────────
payload = {
    "messages": [{"role": "user", "content": "CT-11112这个任务下面最近程序提交了什么代码？"}],
    "user_config": {"ai_api_key": deepseek_key, "ai_model": "deepseek-chat"},
    "config": {"max_steps": 5, "jira_projects": "CT", "_wbUser": "test_user"}
}

# ── 发送请求 + 解析 SSE ──────────────────────────────────
print("[INFO] 发送请求到 http://127.0.0.1:9099/v1/chat/completions ...")
try:
    r = requests.post(
        "http://127.0.0.1:9099/v1/chat/completions",
        json=payload,
        stream=True,
        timeout=60
    )
    r.raise_for_status()
except Exception as e:
    print(f"[FATAL] HTTP 请求失败: {e}")
    sys.exit(1)

full_text = ""
plugin_calls = []

for raw_line in r.iter_lines():
    if not raw_line:
        continue
    line = raw_line.decode("utf-8", errors="replace")
    if not line.startswith("data: "):
        continue
    data_str = line[6:]
    if data_str == "[DONE]":
        break
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        continue

    # 记录插件调用
    if data.get("custom_type") == "plugin_state":
        plugin_calls.append(data.get("plugin", {}))
    # 拼接内容
    content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
    if content:
        full_text += content

# ── 输出 ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("📋 插件调用链:")
for p in plugin_calls:
    print(f"  [{p.get('status')}] {p.get('name')}")

print("\n" + "=" * 60)
print("💬 AI 回复:")
print(full_text[:800])

# ── 核心断言 ──────────────────────────────────────────────
print("\n" + "=" * 60)
REQUIRED_TERMS = ["r40446", "杨正江", "attr_v2.go"]
missing = [t for t in REQUIRED_TERMS if t not in full_text]

if not missing:
    print("✅ [TEST PASSED] 所有核心特征词均已命中！")
    print(f"   已匹配: {', '.join(REQUIRED_TERMS)}")
else:
    print(f"❌ [TEST FAILED] 缺失特征词: {missing}")
    print(f"   已匹配: {[t for t in REQUIRED_TERMS if t in full_text]}")
    print(f"\n📄 实际返回全文:\n{full_text}")
    sys.exit(1)
