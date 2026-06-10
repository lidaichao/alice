#!/usr/bin/env python3
"""
check_dify.py — Dify 健康检查脚本
v3.1 w2 · 集成收官

功能：
 ① 检查 Dify 可达（GET /health）
 ② 读 .env.dify 的 DIFY_DATASET_API_KEY
 ③ 若为空 → 输出提示
 ④ 若不为空 → GET /v1/datasets/{DIFY_DATASET_ID} 验证权限
 ⑤ 输出状态报告

用法：python backend/scripts/check_dify.py
"""

import os
import sys
import requests

# ═══ 路径解析 ═══
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)

DIFY_DOTENV_PATH = os.path.join(BACKEND_DIR, ".env.dify")


def load_dotenv(path: str) -> dict:
    env = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
    return env


def check_dify_health(base_url: str) -> bool:
    """检查 Dify 可达"""
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✅ Dify 服务正常（版本: {data.get('version', 'unknown')}）")
            return True
        print(f"  ⚠️  Dify /health HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"  ❌ 无法连接到 Dify ({base_url})")
    except Exception as e:
        print(f"  ❌ Dify 连接异常: {e}")
    return False


def check_dataset_access(base_url: str, api_key: str, dataset_id: str) -> dict:
    """验证数据集访问权限，返回状态 dict"""
    result = {"ok": False, "status_code": 0, "error": ""}

    if not api_key:
        result["error"] = "DIFY_DATASET_API_KEY 未配置"
        return result

    try:
        # 尝试检索来验证权限
        resp = requests.post(
            f"{base_url}/v1/datasets/{dataset_id}/retrieve",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": "healthcheck",
                "retrieval_model": {
                    "search_method": "hybrid_search",
                    "reranking_enable": False,
                    "top_k": 1,
                },
            },
            timeout=10,
        )
        result["status_code"] = resp.status_code

        if resp.status_code == 200:
            result["ok"] = True
        elif resp.status_code == 401:
            result["error"] = "Key 无效（401 Unauthorized）——请检查 DIFY_DATASET_API_KEY"
        elif resp.status_code == 404:
            result["error"] = f"数据集 {dataset_id} 不存在（404）——请检查 DIFY_DATASET_ID"
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    print("=" * 60)
    print("  Alice v3.1 · Dify 健康检查")
    print("=" * 60)

    # 1. 读取配置
    env = load_dotenv(DIFY_DOTENV_PATH)

    base_url = os.getenv("DIFY_BASE_URL", env.get("DIFY_BASE_URL", "http://localhost:5001"))
    app_key = os.getenv("DIFY_API_KEY", env.get("DIFY_API_KEY", ""))
    dataset_key = os.getenv("DIFY_DATASET_API_KEY", env.get("DIFY_DATASET_API_KEY", ""))
    dataset_id = os.getenv("DIFY_DATASET_ID", env.get("DIFY_DATASET_ID", ""))

    print(f"\n  配置:")
    print(f"    Dify URL: {base_url}")
    print(f"    DIFY_API_KEY (app-*): {'已配置' if app_key else '❌ 未配置'}")
    print(f"    DIFY_DATASET_API_KEY (dataset-*): {'已配置' if dataset_key else '❌ 未配置'}")
    print(f"    DIFY_DATASET_ID: {dataset_id or '❌ 未配置'}")

    # 2. 检查 Dify 可达
    print(f"\n  [1/3] 检查 Dify 服务...")
    if not check_dify_health(base_url):
        print("\n  ❌ Dify 服务不可达，请确认 Docker 容器已启动")
        sys.exit(1)

    # 3. 检查 Dataset Key
    print(f"\n  [2/3] 检查 Dataset Key 状态...")
    if not dataset_key:
        print("  ⚠️  DIFY_DATASET_API_KEY 未配置")
        print("     → 知识库 RAG 检索需要 dataset-* 开头的 Key")
        print("     → 当前仅使用 DIFY_API_KEY（app-*），数据集 API 可能会返回 401")
        print("     → 获取方式：Dify 控制台 → 知识库 → API 管理 → 创建 Dataset Key")
        key_status = "missing"
    else:
        if not dataset_key.startswith("dataset-"):
            print(f"  ⚠️  DIFY_DATASET_API_KEY 不以 'dataset-' 开头：{dataset_key[:20]}...")
            print("     → Dify 数据集 API 需要 dataset-* 格式的 Key")
            key_status = "invalid_format"
        else:
            print(f"  ✅ DIFY_DATASET_API_KEY 已配置（格式正确）")
            key_status = "valid"

    # 4. 验证权限（仅当 Key 存在时）
    print(f"\n  [3/3] 验证数据集访问权限...")
    if dataset_key and dataset_id:
        result = check_dataset_access(base_url, dataset_key, dataset_id)
        if result["ok"]:
            print("  ✅ 数据集访问权限正常")
        else:
            print(f"  ❌ 数据集不可用：{result['error']}")
            print("     → 请检查 DIFY_DATASET_API_KEY 和 DIFY_DATASET_ID 是否正确")
    elif dataset_id:
        print(f"  ⚠️  跳过（Dataset Key 未配置，无法验证）")
    else:
        print(f"  ❌ DIFY_DATASET_ID 未配置")

    # 总结
    print("\n" + "=" * 60)
    print("  检查结果:")
    print(f"    Dify 服务: ✅ 正常")
    print(f"    App Key: {'✅ 已配置' if app_key else '❌ 未配置'}")
    print(f"    Dataset Key: {dataset_key[:20]}...{'✅ 已配置' if key_status == 'valid' else '⚠️  需配置'}")
    print(f"    Dataset ID: {'✅' if dataset_id else '❌ 未配置'}")
    print("=" * 60)

    if key_status == "valid":
        print("\n✅ Dify 双 Key 状态正常\n")
    else:
        print(f"\n⚠️  Dify Dataset Key 状态：{key_status}（知识库 RAG 功能受限）\n")


if __name__ == "__main__":
    main()
