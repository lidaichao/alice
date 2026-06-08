"""P1-4: Workspace 只读工具执行器（独立于 ai_bridge，遵守 E1.3）"""
import json
import os
import subprocess
from workspace_manager import is_path_allowed


def _exec_read_file(args: dict, **kwargs) -> str:
    """工具: 读取工作区文件内容（只读 + 白名单检查）"""
    path = args.get("path", "").strip()
    if not path:
        return json.dumps({"status": "error", "result": "缺少 path 参数"})
    max_lines = int(args.get("max_lines", 0) or 200)
    try:
        if not is_path_allowed(path):
            return json.dumps({"status": "error", "result": f"路径未授权或越权: {path}"})
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = []
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
        content = "\n".join(lines)
        truncated = len(lines) >= max_lines
        return json.dumps({
            "status": "ok",
            "result": {
                "path": path,
                "lines": len(lines),
                "truncated": truncated,
                "content": content,
            }
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"读取文件失败: {str(e)[:200]}"})


def _exec_search_code(args: dict, **kwargs) -> str:
    """工具: ripgrep 代码搜索（只读 + 白名单检查）"""
    pattern = args.get("pattern", "").strip()
    if not pattern:
        return json.dumps({"status": "error", "result": "缺少 pattern 参数"})
    search_path = args.get("path", "").strip() or os.getcwd()
    glob_filter = args.get("glob", "").strip()
    try:
        if not is_path_allowed(search_path):
            return json.dumps({"status": "error", "result": f"路径未授权或越权: {search_path}"})
        cmd = ["rg", "--no-heading", "-n", "--color", "never", "--max-count", "50", pattern, search_path]
        if glob_filter:
            cmd.insert(-2, "-g")
            cmd.insert(-2, glob_filter)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        output = result.stdout.strip()
        if not output:
            return json.dumps({"status": "ok", "result": {"matches": 0, "output": "未找到匹配结果"}})
        return json.dumps({
            "status": "ok",
            "result": {
                "matches": len(output.split("\n")),
                "output": output[:8000],
                "truncated": len(output) > 8000,
            }
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"代码搜索失败: {str(e)[:200]}"})


def _exec_svn_log(args: dict, **kwargs) -> str:
    """工具: SVN 提交日志（只读 + 白名单检查）"""
    path = args.get("path", "").strip()
    if not path:
        return json.dumps({"status": "error", "result": "缺少 path 参数"})
    limit = int(args.get("limit", 0) or 20)
    try:
        if not is_path_allowed(path):
            return json.dumps({"status": "error", "result": f"路径未授权或越权: {path}"})
        cmd = ["svn", "log", "--limit", str(limit), "-v", path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        output = result.stdout.strip()
        if not output:
            return json.dumps({"status": "ok", "result": "该路径暂无 SVN 提交记录"})
        return json.dumps({
            "status": "ok",
            "result": {"output": output[:8000], "truncated": len(output) > 8000},
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"SVN 日志查询失败: {str(e)[:200]}"})


def _exec_list_directory(args: dict, **kwargs) -> str:
    """工具: 列出目录结构（只读 + 白名单检查）"""
    path = args.get("path", "").strip()
    if not path:
        return json.dumps({"status": "error", "result": "缺少 path 参数"})
    try:
        if not is_path_allowed(path):
            return json.dumps({"status": "error", "result": f"路径未授权或越权: {path}"})
        entries = []
        for name in sorted(os.listdir(path))[:200]:
            full = os.path.join(path, name)
            entries.append({
                "name": name,
                "type": "dir" if os.path.isdir(full) else "file",
            })
        return json.dumps({
            "status": "ok",
            "result": {
                "path": path,
                "count": len(entries),
                "truncated": len(os.listdir(path)) > 200,
                "entries": entries,
            }
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "result": f"列目录失败: {str(e)[:200]}"})
