"""P1-4 受控代码分析 — workspace_manager 单元测试（4 条）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workspace_manager import (
    authorize_workspace,
    revoke_workspace,
    is_path_allowed,
    list_workspaces,
    _WORKSPACES_FILE,
    _save_workspaces,
)


class TestWorkspaceManager(unittest.TestCase):
    """测试工作区授权与路径安全检查"""

    def setUp(self):
        """每个测试前清空工作区文件"""
        _save_workspaces([])

    def test_authorize_valid_path_writes_to_file(self):
        """授权合法路径 → 写入 workspaces.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = authorize_workspace(tmpdir, "test-workspace")
            self.assertTrue(result["ok"])
            self.assertEqual(result["workspace"]["name"], "test-workspace")

            # 验证持久化
            with open(_WORKSPACES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "test-workspace")

            # 验证白名单通过
            test_file = os.path.join(tmpdir, "hello.py")
            with open(test_file, "w") as f:
                f.write("print('ok')")
            self.assertTrue(is_path_allowed(test_file))

    def test_revoke_blocks_path(self):
        """revoke 后 is_path_allowed → False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            authorize_workspace(tmpdir, "temp-ws")
            test_file = os.path.join(tmpdir, "data.txt")
            with open(test_file, "w") as f:
                f.write("data")
            self.assertTrue(is_path_allowed(test_file))

            # 获取 ID 并撤销
            ws_list = list_workspaces()
            revoke_workspace(ws_list[0]["id"])

            # 撤销后应不再允许
            self.assertFalse(is_path_allowed(test_file))

    def test_path_traversal_blocked(self):
        """路径穿越 → is_path_allowed=False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            authorize_workspace(tmpdir, "ws")
            traversal = os.path.join(tmpdir, "..", "..", "etc", "passwd")
            self.assertFalse(is_path_allowed(traversal))

    def test_sensitive_filename_blocked(self):
        """敏感文件名 .env → is_path_allowed=False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            authorize_workspace(tmpdir, "ws")
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("SECRET=xxx")
            self.assertFalse(is_path_allowed(env_file))

    def tearDown(self):
        """清理"""
        _save_workspaces([])


if __name__ == "__main__":
    unittest.main()
