"""
eval/config.py — 评估引擎配置中心
读取 ../backend/global_config.json，导出 API Key
"""
import os, json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend', 'global_config.json')

_config = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        _config = json.load(f)
    print(f"[config] Loaded from {CONFIG_PATH}")

# 导出全局变量，优先 JSON，退而求其次读环境变量
NOTION_KEY = _config.get("NOTION_KEY") or os.getenv("NOTION_KEY", "")
DEEPSEEK_KEY = _config.get("DEEPSEEK_KEY") or os.getenv("DEEPSEEK_KEY", "")
GDRIVE_KEY = _config.get("GDRIVE_KEY") or os.getenv("GDRIVE_KEY", "")
NOTION_DATABASE_ID = _config.get("NOTION_DATABASE_ID") or os.getenv("NOTION_DATABASE_ID", "")

if NOTION_KEY:
    print(f"[config] NOTION_KEY: {NOTION_KEY[:8]}...")
else:
    print("[config] WARNING: NOTION_KEY not found")
if DEEPSEEK_KEY:
    print(f"[config] DEEPSEEK_KEY: {DEEPSEEK_KEY[:8]}...")
