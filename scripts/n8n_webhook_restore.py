#!/usr/bin/env python3
"""
n8n Webhook 恢复脚本 (AL-71)
--------------------------
用途：n8n 容器重启后，Webhook 路由可能因注册表丢失返回 404。
      本脚本通过 n8n REST API 验证并恢复 Webhook 注册。

原理：n8n 在启动时会为所有 active workflow 注册 webhook 路由。
      如果容器重启后 webhook 仍 404 → 调用 deactivate/activate 循环，
      然后重启容器让 n8n 在启动时重新注册。
"""
import os
import sys
import time
import requests
import subprocess

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY", "")
CONTAINER_NAME = os.getenv("N8N_CONTAINER_NAME", "alice-n8n")
WEBHOOK_PATHS = [
    "alice-jira-create",
    "alice-jira-search",
    "alice-hub-callback",
]


def check_webhooks() -> dict[str, bool]:
    """检查每个 webhook 是否可达（不要求业务成功，只要求不是 404）。"""
    results = {}
    for path in WEBHOOK_PATHS:
        try:
            r = requests.post(
                f"{N8N_BASE_URL}/webhook/{path}",
                json={"health_check": True},
                timeout=5,
            )
            # 404 = 路由未注册；其他状态码（含超时）= 已注册
            results[path] = r.status_code != 404
        except requests.exceptions.ReadTimeout:
            # Webhook 已注册但后端处理超时 → 正常
            results[path] = True
        except requests.exceptions.ConnectionError:
            # n8n 未启动
            results[path] = False
    return results


def get_active_workflows() -> list[dict]:
    """通过 REST API 获取所有 workflow。"""
    if not N8N_API_KEY:
        print("⚠️ N8N_API_KEY 未设置，跳过 REST API 恢复")
        return []
    headers = {"X-N8N-API-KEY": N8N_API_KEY}
    try:
        r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception as e:
        print(f"⚠️ 获取 workflow 列表失败: {e}")
    return []


def reactivate_workflows(workflows: list[dict]) -> int:
    """对所有 workflow 执行 deactivate → activate 循环。"""
    headers = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}
    count = 0
    for wf in workflows:
        wf_id = wf["id"]
        name = wf.get("name", wf_id)
        try:
            # Deactivate
            r = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/deactivate", headers=headers, timeout=10)
            time.sleep(1)
            # Activate
            r = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=headers, timeout=10)
            print(f"  ✅ {name}: reactivated")
            count += 1
        except Exception as e:
            print(f"  ❌ {name}: reactivate 失败 - {e}")
    return count


def restart_container() -> bool:
    """Docker 重启 n8n 容器。"""
    try:
        subprocess.run(
            ["docker", "restart", CONTAINER_NAME],
            capture_output=True, text=True, timeout=30,
        )
        print(f"  🔄 容器 {CONTAINER_NAME} 已重启")
        return True
    except Exception as e:
        print(f"  ❌ 容器重启失败: {e}")
        return False


def wait_for_n8n(timeout: int = 30) -> bool:
    """等待 n8n 就绪。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{N8N_BASE_URL}/healthz", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main():
    print("=" * 50)
    print("n8n Webhook 恢复检查")
    print(f"  n8n URL: {N8N_BASE_URL}")
    print(f"  容器名:  {CONTAINER_NAME}")
    print("=" * 50)

    # Phase 1: 检查当前状态
    print("\n📡 检查 Webhook 状态...")
    results = check_webhooks()
    all_ok = all(results.values())

    for path, ok in results.items():
        status = "✅ OK" if ok else "❌ 404"
        print(f"  /webhook/{path}: {status}")

    if all_ok:
        print("\n✅ 所有 Webhook 正常，无需恢复。")
        return 0

    # Phase 2: REST API 恢复
    print("\n🔧 尝试 REST API 恢复...")
    workflows = get_active_workflows()

    if workflows:
        print(f"  找到 {len(workflows)} 个 workflow")
        reactivated = reactivate_workflows(workflows)
    else:
        print("  ⚠️ 无法通过 REST API 获取 workflow（API Key 未配置或 n8n 未就绪）")
        print("  → 直接重启容器触发 webhook 注册")
        reactivated = 0

    # Phase 3: 重启容器
    print("\n🔄 重启 n8n 容器...")
    if not restart_container():
        print("❌ 容器重启失败，放弃恢复")
        return 2

    print("⏳ 等待 n8n 就绪...")
    if not wait_for_n8n():
        print("❌ n8n 启动超时")
        return 3

    time.sleep(5)  # 额外等待 webhook 注册

    # Phase 4: 最终验证
    print("\n📡 最终验证 Webhook 状态...")
    results = check_webhooks()
    for path, ok in results.items():
        status = "✅ OK" if ok else "❌ 404"
        print(f"  /webhook/{path}: {status}")

    if all(results.values()):
        print("\n✅ Webhook 恢复成功！")
        return 0
    else:
        print("\n⚠️ 部分 Webhook 仍不可达，请检查 n8n 容器日志")
        return 4


if __name__ == "__main__":
    sys.exit(main())
