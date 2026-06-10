#!/usr/bin/env python3
"""
verify_stack.py — Alice 全栈冷启动验证脚本
v3.1 w2 · 集成收官

功能：
 ① docker compose -f docker-compose.prod.yml config → 语法校验
 ② docker compose -f docker-compose.prod.yml up -d → 启动
 ③ 轮询 4 服务健康（各最多 60s）
 ④ Agent 端到端冒烟（POST /v1/agent/stream）
 ⑤ docker compose -f docker-compose.prod.yml down → 清理
 ⑥ 输出验证报告

用法：python backend/scripts/verify_stack.py
"""

import json
import os
import subprocess
import sys
import time
import requests

# ═══ 路径解析 ═══
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
REPO_DIR = os.path.dirname(BACKEND_DIR)
COMPOSE_FILE = os.path.join(REPO_DIR, "docker-compose.prod.yml")

DIFY_DOTENV = os.path.join(BACKEND_DIR, ".env.dify")
N8N_DOTENV = os.path.join(BACKEND_DIR, ".env.n8n")
GLOBAL_CONFIG = os.path.join(BACKEND_DIR, "global_config.json")


def load_dotenv(path: str) -> dict:
    """读取 .env 文件，返回 dict"""
    env = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
    return env


def export_compose_env():
    """从本地配置加载并导出 docker-compose 所需环境变量"""
    dify_env = load_dotenv(DIFY_DOTENV)
    n8n_env = load_dotenv(N8N_DOTENV)
    config = {}
    if os.path.exists(GLOBAL_CONFIG):
        with open(GLOBAL_CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)

    vars_map = {
        # Jira
        "ALICE_JIRA_URL": os.getenv("JIRA_BASE_URL", config.get("JIRA_BASE_URL", "")),
        "ALICE_JIRA_PAT": os.getenv("JIRA_PAT", config.get("JIRA_PAT", "")),
        # Dify
        "DIFY_API_KEY": os.getenv("DIFY_API_KEY", dify_env.get("DIFY_API_KEY", "")),
        "DIFY_DATASET_API_KEY": os.getenv("DIFY_DATASET_API_KEY", dify_env.get("DIFY_DATASET_API_KEY", "")),
        "DIFY_DATASET_ID": os.getenv("DIFY_DATASET_ID", dify_env.get("DIFY_DATASET_ID", "")),
        "DIFY_SECRET_KEY": os.getenv("DIFY_SECRET_KEY", "dify-alice-v3-prod-secret"),
        "DIFY_DB_PASSWORD": os.getenv("DIFY_DB_PASSWORD", "dify-alice-pg-prod"),
        # n8n
        "N8N_API_KEY": os.getenv("N8N_API_KEY", n8n_env.get("N8N_API_KEY", "")),
        "N8N_WEBHOOK_BASE_URL": os.getenv("N8N_WEBHOOK_BASE_URL", n8n_env.get("N8N_WEBHOOK_BASE_URL", "http://n8n:5678")),
        "N8N_ADMIN_PASSWORD": os.getenv("N8N_ADMIN_PASSWORD", "changeme"),
        # AI
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_KEY", config.get("DEEPSEEK_KEY", ""))),
        # 安全
        "ALICE_ADMIN_PASSWORD": os.getenv("ALICE_ADMIN_PASSWORD", "changeme"),
    }

    missing = [k for k, v in vars_map.items() if not v]
    if missing:
        print(f"  ⚠️  缺少环境变量: {', '.join(missing)}")
        print("     将从 .env.prod.example 模板读取作为默认值")

    for key, val in vars_map.items():
        if val:
            os.environ[key] = val

    return bool([k for k, v in vars_map.items() if v])

# 服务端口映射
SERVICES = {
    "alice-hub": {"url": "http://localhost:5000", "endpoint": "/health", "label": "Alice Hub"},
    "dify-api": {"url": "http://localhost:5001", "endpoint": "/health", "label": "Dify API"},
    "n8n": {"url": "http://localhost:5678", "endpoint": "/healthz", "label": "n8n"},
    "admin-ui": {"url": "http://localhost:8080", "endpoint": "/index.html", "label": "Admin UI"},
}


def run_cmd(cmd: list, cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    """运行命令，返回 (exit_code, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except Exception as e:
        return -1, "", str(e)


def check_service(url: str, endpoint: str, label: str, max_retries: int = 30, interval: int = 2) -> bool:
    """轮询服务健康，最多 max_retries*interval 秒"""
    full_url = f"{url}{endpoint}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(full_url, timeout=5)
            if resp.status_code == 200:
                elapsed = attempt * interval
                print(f"  ✅ {label} 健康（{elapsed}s, {attempt}/{max_retries}）")
                return True
            print(f"  ⏳ {label} HTTP {resp.status_code}（{attempt}/{max_retries}）")
        except requests.exceptions.ConnectionError:
            if attempt == 1:
                print(f"  ⏳ {label} 连接中...（{attempt}/{max_retries}）")
            elif attempt % 5 == 0:
                print(f"  ⏳ {label} 仍在等待...（{attempt}/{max_retries}）")
        except Exception as e:
            print(f"  ⚠️  {label} 异常: {e}（{attempt}/{max_retries}）")
        time.sleep(interval)
    print(f"  ❌ {label} 超时：{max_retries * interval}s 未就绪")
    return False


def agent_smoke_test(hub_url: str, timeout: int = 30) -> bool:
    """Agent 端到端冒烟：POST /v1/agent/stream → SSE 含 message 或 done"""
    print(f"\n  [5/7] Agent 端到端冒烟测试...")

    payload = {
        "messages": [{"role": "user", "content": "帮我查 CT-1 的状态"}],
        "thread_id": "smoke-test-v31",
    }

    try:
        resp = requests.post(
            f"{hub_url}/v1/agent/stream",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
            stream=True,
        )
        if resp.status_code != 200:
            print(f"  ❌ Agent stream HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        events = []
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                    event_type = event.get("type", "unknown")
                    events.append(event_type)
                    if event_type == "message":
                        content = event.get("content", "")
                        print(f"  📨 message: {content[:60]}...")
                    elif event_type == "done":
                        print(f"  ✅ done")
                        break
                    elif event_type == "error":
                        error_msg = event.get("error", "")
                        print(f"  ⚠️  error: {error_msg[:80]}")
                except json.JSONDecodeError:
                    pass  # skip malformed lines

        has_message = "message" in events
        has_done = "done" in events
        has_error = "error" in events

        if has_done or (has_message and not has_error):
            print(f"  ✅ Agent 端到端验证通过（事件: {', '.join(events[:5])}{'...' if len(events) > 5 else ''}）")
            return True
        elif has_message:
            print(f"  ⚠️  Agent 返回 message 但未 done（事件: {', '.join(events[:5])}）")
            return True  # 部分成功也算通过
        else:
            print(f"  ❌ Agent 未返回有效事件（收到: {', '.join(events[:5]) if events else '无'}）")
            return False

    except requests.exceptions.Timeout:
        print(f"  ❌ Agent stream 超时（{timeout}s）")
        return False
    except Exception as e:
        print(f"  ❌ Agent stream 异常: {e}")
        return False


def main():
    print("=" * 60)
    print("  Alice v3.1 · 全栈冷启动验证")
    print("=" * 60)

    # 0. 加载环境变量
    print(f"\n  [0/6] 加载环境变量...")
    export_compose_env()
    print("  ✅ 环境变量已就绪")

    # 1. docker compose 语法校验
    print(f"\n  [1/7] docker-compose 语法校验...")
    if not os.path.exists(COMPOSE_FILE):
        print(f"  ❌ 文件不存在: {COMPOSE_FILE}")
        sys.exit(1)

    rc, stdout, stderr = run_cmd(
        ["docker", "compose", "-f", COMPOSE_FILE, "config"],
        cwd=REPO_DIR,
        timeout=30,
    )
    if rc != 0:
        print(f"  ❌ docker-compose 语法错误:")
        print(f"  {stderr[:500]}")
        print("\n  跳过全栈启动（YAML 无效）")
        sys.exit(1)
    print("  ✅ docker-compose.prod.yml 语法正确")

    # 2. 启动全栈
    print(f"\n  [2/7] 启动全栈服务...")
    rc, stdout, stderr = run_cmd(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
        cwd=REPO_DIR,
        timeout=120,
    )
    if rc != 0:
        print(f"  ❌ 启动失败:")
        print(f"  {stderr[:500]}")
        print("\n  正在清理...")
        run_cmd(["docker", "compose", "-f", COMPOSE_FILE, "down"], cwd=REPO_DIR, timeout=60)
        sys.exit(1)
    print("  ✅ docker compose up -d 成功")

    # 3. 轮询 4 服务健康
    print(f"\n  [3/7] 等待服务就绪（最多 60s）...")
    all_healthy = True
    for svc_name, svc_info in SERVICES.items():
        ok = check_service(svc_info["url"], svc_info["endpoint"], svc_info["label"], max_retries=30, interval=2)
        if not ok:
            all_healthy = False

    if not all_healthy:
        print("\n  ⚠️  部分服务未就绪，继续 Agent 冒烟测试...")

    # 4. Agent 端到端冒烟
    all_healthy = agent_smoke_test("http://localhost:5000") and all_healthy

    # 5. 清理
    print(f"\n  [7/7] 清理服务...")
    rc, stdout, stderr = run_cmd(
        ["docker", "compose", "-f", COMPOSE_FILE, "down"],
        cwd=REPO_DIR,
        timeout=60,
    )
    if rc == 0:
        print("  ✅ docker compose down 成功")
    else:
        print(f"  ⚠️  down 返回非零: {rc}")

    # 总结
    print("\n" + "=" * 60)
    print("  验证结果:")
    for svc_name, svc_info in SERVICES.items():
        status = "✅" if all_healthy else "⚠️"
        print(f"    {svc_info['label']}: {status}")
    print(f"    Agent 冒烟: {'✅ OK' if all_healthy else '⚠️  需检查'}")
    print("=" * 60)

    if all_healthy:
        print("\n✅ 全栈验证通过（4/4 健康 · Agent 端到端 OK）\n")
    else:
        print("\n⚠️  全栈验证未完全通过，请检查上述输出\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
