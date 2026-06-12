#!/usr/bin/env python3
"""
setup_n8n.py — n8n 自动化导入脚本
v3.1 w2 · 集成收官

功能：
 ① 检查 n8n 可达（GET /healthz）
 ② 读 .env.n8n 的 N8N_API_KEY + global_config.json 的 JIRA_PAT/JIRA_URL
 ③ 创建 Jira 凭据（POST /api/v1/credentials），已存在则跳过
 ④ 导入 n8n_workflows/jira_search.json → POST /api/v1/workflows → 激活
 ⑤ 导入 n8n_workflows/jira_create.json → 同上
 ⑥ 输出状态报告

用法：python backend/scripts/setup_n8n.py
"""

import json
import os
import sys
import time
import requests

# ═══ 路径解析 ═══
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
REPO_DIR = os.path.dirname(BACKEND_DIR)

N8N_DOTENV_PATH = os.path.join(BACKEND_DIR, ".env.n8n")
GLOBAL_CONFIG_PATH = os.path.join(BACKEND_DIR, "global_config.json")
JIRA_SEARCH_WF = os.path.join(BACKEND_DIR, "n8n_workflows", "jira_search.json")
JIRA_CREATE_WF = os.path.join(BACKEND_DIR, "n8n_workflows", "jira_create.json")


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


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def check_n8n_health(base_url: str) -> bool:
    """检查 n8n 可达"""
    try:
        resp = requests.get(f"{base_url}/healthz", timeout=5)
        if resp.status_code == 200:
            return True
        print(f"  n8n /healthz HTTP {resp.status_code}: {resp.text[:200]}")
    except requests.exceptions.ConnectionError:
        print(f"  ❌ 无法连接到 n8n ({base_url})")
    except Exception as e:
        print(f"  ❌ n8n 连接异常: {e}")
    return False


def load_api_key(env: dict) -> str:
    """从 env 或 os.environ 读取 N8N_API_KEY"""
    key = os.getenv("N8N_API_KEY", "").strip()
    if not key:
        key = env.get("N8N_API_KEY", "").strip()
    if not key:
        # 尝试从 .env.n8n 的完整内容读取（Phase 3 修复后的 Key）
        raw_key = env.get("N8N_API_KEY", "")
        # 确保不是截断的 Key
        if len(raw_key) < 30:
            print(f"  ⚠️  N8N_API_KEY 太短 ({len(raw_key)} 字符)，可能被截断")
    return key


def create_jira_credential(base_url: str, api_key: str, jira_pat: str, jira_url: str, jira_email: str) -> str | None:
    """创建 n8n Jira Software API 凭据，返回 credential_id"""

    # 先检查是否已存在同名凭据
    try:
        resp = requests.get(
            f"{base_url}/api/v1/credentials",
            headers={"X-N8N-API-KEY": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            creds = resp.json().get("data", [])
            for cred in creds:
                if cred.get("name") == "Alice Jira PAT":
                    print(f"  ✅ Jira 凭据已存在（ID: {cred['id']}），跳过创建")
                    return cred["id"]
    except Exception as e:
        print(f"  ⚠️  查询凭据列表失败: {e}")

    # 创建新凭据（per n8n_api.md §一：Jira 用 jiraSoftwareApi 类型）
    payload = {
        "name": "Alice Jira PAT",
        "type": "jiraSoftwareApi",
        "data": {
            "url": jira_url,
            "email": jira_email,
            "apiToken": jira_pat,
        },
    }
    try:
        resp = requests.post(
            f"{base_url}/api/v1/credentials",
            headers={
                "X-N8N-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        if resp.status_code in (200, 201):
            cred_id = resp.json().get("id", "")
            print(f"  ✅ Jira 凭据已创建（ID: {cred_id}）")
            return cred_id
        else:
            print(f"  ❌ 创建凭据失败: HTTP {resp.status_code} {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ 创建凭据异常: {e}")
        return None


def import_or_update_workflow(base_url: str, api_key: str, wf_path: str, wf_name: str, credential_id: str | None = None) -> bool:
    """导入或更新 n8n 工作流并激活"""

    if not os.path.exists(wf_path):
        print(f"  ❌ 工作流文件不存在: {wf_path}")
        return False

    with open(wf_path, "r", encoding="utf-8") as f:
        workflow_json = json.load(f)

    # 如果提供了 credential_id，注入到 Jira 节点
    if credential_id and "nodes" in workflow_json:
        for node in workflow_json["nodes"]:
            if node.get("type") == "n8n-nodes-base.jira" and "credentials" in node:
                node["credentials"]["jiraSoftwareApi"] = {"id": credential_id, "name": "Alice Jira PAT"}

    # 先查是否已存在
    try:
        resp = requests.get(
            f"{base_url}/api/v1/workflows",
            headers={"X-N8N-API-KEY": api_key},
            timeout=10,
        )
        existing_id = None
        if resp.status_code == 200:
            for wf in resp.json().get("data", []):
                if wf.get("name") == wf_name:
                    existing_id = wf["id"]
                    existing_active = wf.get("active", False)
                    break
    except Exception:
        existing_id = None

    if existing_id:
        # 更新已有工作流
        try:
            resp = requests.patch(
                f"{base_url}/api/v1/workflows/{existing_id}",
                headers={
                    "X-N8N-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"name": wf_name, "nodes": workflow_json.get("nodes", []),
                      "connections": workflow_json.get("connections", {}),
                      "settings": workflow_json.get("settings", {})},
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                print(f"  ⚠️  更新工作流失败: HTTP {resp.status_code} {resp.text[:200]}")
                return False
            print(f"  ✅ 工作流已更新（ID: {existing_id}）")
        except Exception as e:
            print(f"  ⚠️  更新工作流异常: {e}")
            return False
    else:
        # 创建新工作流
        try:
            resp = requests.post(
                f"{base_url}/api/v1/workflows",
                headers={
                    "X-N8N-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"name": wf_name, "nodes": workflow_json.get("nodes", []),
                      "connections": workflow_json.get("connections", {}),
                      "settings": workflow_json.get("settings", {})},
                timeout=15,
            )
            if resp.status_code not in (200, 201):
                print(f"  ❌ 创建工作流失败: HTTP {resp.status_code} {resp.text[:200]}")
                return False
            existing_id = resp.json().get("id", "")
            print(f"  ✅ 工作流已创建（ID: {existing_id}）")
        except Exception as e:
            print(f"  ❌ 创建工作流异常: {e}")
            return False

    if not existing_id:
        return False

    # 激活工作流
    try:
        resp = requests.post(
            f"{base_url}/api/v1/workflows/{existing_id}/activate",
            headers={"X-N8N-API-KEY": api_key},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            print(f"    ↳ 已激活")
            return True
        else:
            print(f"    ⚠️  激活失败: HTTP {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"    ⚠️  激活异常: {e}")
        return False


def main():
    print("=" * 60)
    print("  Alice v3.1 · n8n 自动化配置")
    print("=" * 60)

    # 1. 读取配置
    env = load_dotenv(N8N_DOTENV_PATH)
    config = load_json(GLOBAL_CONFIG_PATH)

    base_url = os.getenv("N8N_BASE_URL", env.get("N8N_BASE_URL", "http://localhost:5678"))
    api_key = load_api_key(env)
    jira_pat = os.getenv("JIRA_PAT", config.get("JIRA_PAT", ""))
    jira_url = os.getenv("JIRA_BASE_URL", config.get("JIRA_BASE_URL", "http://ctjira1.lmdgame.com:8080"))
    jira_email = os.getenv("JIRA_EMAIL", config.get("JIRA_EMAIL", "squirtle@lmdgame.com"))

    print(f"\n  配置:")
    print(f"    n8n URL: {base_url}")
    print(f"    API Key: {'已配置' if api_key else '❌ 未配置'}")
    print(f"    Jira PAT: {'已配置' if jira_pat else '❌ 未配置'}")
    print(f"    Jira URL: {jira_url}")
    print(f"    Jira Email: {jira_email}")

    if not api_key:
        print("\n  ❌ N8N_API_KEY 未配置，请在 .env.n8n 中设置后重试")
        sys.exit(1)

    # 2. 检查 n8n 可达
    print(f"\n  [1/4] 检查 n8n 服务...")
    if not check_n8n_health(base_url):
        print("\n  ❌ n8n 服务不可达，请确认 Docker 容器已启动")
        sys.exit(1)
    print("  ✅ n8n 服务正常运行")

    # 3. 创建凭据
    print(f"\n  [2/4] 配置 Jira 凭据...")
    credential_id = None
    if jira_pat:
        credential_id = create_jira_credential(base_url, api_key, jira_pat, jira_url, jira_email)
    else:
        print("  ⚠️  JIRA_PAT 未配置，跳过凭据创建")

    # 4. 导入 jira_search 工作流
    print(f"\n  [3/4] 导入 jira_search 工作流...")
    ok_search = import_or_update_workflow(base_url, api_key, JIRA_SEARCH_WF, "Alice Jira Search")

    # 5. 导入 jira_create 工作流
    print(f"\n  [4/4] 导入 jira_create 工作流...")
    ok_create = import_or_update_workflow(base_url, api_key, JIRA_CREATE_WF, "Alice Jira Create", credential_id)

    # 总结
    print("\n" + "=" * 60)
    print("  配置结果:")
    print(f"    n8n 服务: ✅ 正常")
    print(f"    Jira 凭据: {'✅ 已配置' if credential_id else '⚠️  跳过'}")
    print(f"    jira_search: {'✅ 已激活' if ok_search else '❌ 失败'}")
    print(f"    jira_create: {'✅ 已激活' if ok_create else '❌ 失败'}")
    print("=" * 60)

    if ok_search and ok_create:
        print("\n✅ n8n 配置完成（凭据×1, 工作流×2 已激活）\n")
    else:
        print("\n⚠️  部分配置未完成，请检查上述错误\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
