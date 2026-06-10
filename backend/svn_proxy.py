"""
svn_proxy.py — SVN 安全代理（Phase 2.3）
v3.0：4 个只读端点 · 白名单过滤 · subprocess 安全封装
约束：#6（数据清洗）· 不违 C8 禁令（仅 subprocess，无 Redis/Temporal）
"""

import subprocess
import shlex
from pathlib import Path
from loguru import logger

from workspace_manager import is_path_allowed


def svn_log(repo_path: str, limit: int = 10, trace_id: str = "unknown") -> list[dict]:
    """
    查询 SVN 仓库日志（只读）。
    
    返回格式：[{"revision": "r12345", "author": "dev", "date": "2026-06-10",
                "message": "commit msg"}]
    """
    if not repo_path or not isinstance(repo_path, str):
        logger.error(f"[{trace_id}] svn_log: 路径参数非法")
        return []

    if not is_path_allowed(repo_path):
        logger.error(f"[{trace_id}] svn_log: 路径未授权 {repo_path}")
        return []

    limit = max(1, min(int(limit), 50))

    try:
        cmd = ["svn", "log", repo_path, "--limit", str(limit), "--xml"]
        logger.info(f"[{trace_id}] svn_log: {repo_path} limit={limit}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            logger.error(f"[{trace_id}] svn_log: SVN 命令失败 (exit={result.returncode}) {result.stderr[:200]}")
            return []

        return _parse_svn_xml(result.stdout, trace_id)
    except subprocess.TimeoutExpired:
        logger.error(f"[{trace_id}] svn_log: SVN 命令超时 >10s")
        return []
    except FileNotFoundError:
        logger.error(f"[{trace_id}] svn_log: SVN 客户端未安装")
        return []
    except Exception as e:
        logger.error(f"[{trace_id}] svn_log: 未知异常 {e}")
        return []


def _parse_svn_xml(xml_str: str, trace_id: str = "") -> list[dict]:
    """解析 SVN XML 日志输出为结构化列表"""
    import xml.etree.ElementTree as ET
    entries = []
    try:
        root = ET.fromstring(xml_str)
        for logentry in root.findall("logentry"):
            revision = logentry.get("revision", "")
            author = ""
            date = ""
            msg = ""
            author_el = logentry.find("author")
            if author_el is not None and author_el.text:
                author = author_el.text
            date_el = logentry.find("date")
            if date_el is not None and date_el.text:
                date = date_el.text
            msg_el = logentry.find("msg")
            if msg_el is not None and msg_el.text:
                msg = msg_el.text[:200]
            entries.append({
                "revision": f"r{revision}",
                "author": author,
                "date": date[:19] if date else "",
                "message": msg,
            })
    except ET.ParseError as e:
        logger.error(f"[{trace_id}] svn_log: XML 解析失败 {e}")
    return entries
