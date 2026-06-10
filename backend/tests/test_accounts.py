"""v2.0-wave1 Accounts 单元测试 — 7 条。"""
import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAccounts(unittest.TestCase):
    """测试 accounts.py 的账号存储、密码验证、Token 生成。"""

    @classmethod
    def setUpClass(cls):
        """用临时目录替换 data/ 避免污染真实数据。"""
        cls._tmpdir = tempfile.mkdtemp(prefix="test_accounts_")
        # 注入 _DATA_DIR 和 _ACCOUNTS_FILE
        import accounts
        cls._orig_data_dir = accounts._DATA_DIR
        cls._orig_accounts_file = accounts._ACCOUNTS_FILE
        cls._orig_loaded = accounts.load_accounts
        # 清除模块缓存，用 imp 重载
        import importlib
        accounts._DATA_DIR = cls._tmpdir
        accounts._ACCOUNTS_FILE = os.path.join(cls._tmpdir, "accounts.json")
        # 确保新文件不存在
        if os.path.exists(accounts._ACCOUNTS_FILE):
            os.remove(accounts._ACCOUNTS_FILE)

    @classmethod
    def tearDownClass(cls):
        import accounts
        accounts._DATA_DIR = cls._orig_data_dir
        accounts._ACCOUNTS_FILE = cls._orig_accounts_file
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        """每条测试前清理 accounts.json。"""
        import accounts
        if os.path.exists(accounts._ACCOUNTS_FILE):
            os.remove(accounts._ACCOUNTS_FILE)

    # ── 测试 1：首次加载自动创建 admin 账号 ──────────────────
    def test_1_first_load_creates_admin(self):
        from accounts import load_accounts, get_account_by_username
        accounts = load_accounts()
        self.assertTrue(len(accounts) > 0, "首次加载应有账号")
        admin = get_account_by_username("admin")
        self.assertIsNotNone(admin, "应有 admin 账号")
        self.assertEqual(admin["username"], "admin")
        self.assertFalse(admin["disabled"])
        self.assertIn("password_hash", admin)
        self.assertIn("salt", admin)

    # ── 测试 2：创建账号（含密码哈希 + salt）──────────────────
    def test_2_create_account_with_hash(self):
        from accounts import create_account, load_accounts
        from accounts import _hash_password as hash_pw
        account = create_account("jane", "简", "pass123", ["developer"])
        self.assertIn("password_hash", account)
        self.assertIn("salt", account)
        self.assertNotEqual(account["password_hash"], "pass123")
        self.assertEqual(account["role_ids"], ["developer"])
        # 验证 hash 一致性
        expected_hash = hash_pw("pass123", account["salt"])
        self.assertEqual(account["password_hash"], expected_hash)

    # ── 测试 3：验证密码通过/拒绝 ─────────────────────────────
    def test_3_verify_password_pass_and_reject(self):
        from accounts import create_account, verify_password
        create_account("bob", "鲍勃", "bob_secret", [])
        # 正确密码
        result = verify_password("bob", "bob_secret")
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "bob")
        # 错误密码
        result2 = verify_password("bob", "wrong")
        self.assertIsNone(result2)
        # 不存在的用户
        result3 = verify_password("noone", "x")
        self.assertIsNone(result3)

    # ── 测试 4：软删除（disabled=true，不是真删）───────────────
    def test_4_soft_delete_disabled(self):
        from accounts import create_account, delete_account, load_accounts
        create_account("carl", "卡尔", "carl_pass", [])
        accts = load_accounts()
        carl = [a for a in accts if a["username"] == "carl"][0]
        result = delete_account(carl["id"])
        self.assertTrue(result["disabled"])
        # 确认仍在列表中
        accts2 = load_accounts()
        self.assertTrue(any(a["username"] == "carl" for a in accts2), "软删除后账号仍在")

    # ── 测试 5：登录返回 token + permissions ─────────────────
    def test_5_login_returns_token_and_permissions(self):
        from accounts import create_account, login, verify_token
        account = create_account("dave", "戴夫", "dave_pass", ["admin"])
        result = login("dave", "dave_pass")
        self.assertIsNotNone(result)
        self.assertIn("token", result)
        self.assertIn("user", result)
        self.assertEqual(result["user"]["username"], "dave")
        self.assertIn("permissions", result)
        # 验证 token
        token_ok = verify_token(result["token"])
        self.assertEqual(token_ok, "dave")

    # ── 测试 6：重复用户名拒绝 ───────────────────────────────
    def test_6_duplicate_username_rejected(self):
        from accounts import create_account
        create_account("eve", "伊芙", "eve_pass", [])
        with self.assertRaises(ValueError) as ctx:
            create_account("eve", "伊芙2", "other", [])
        self.assertIn("已存在", str(ctx.exception))

    # ── 测试 7：编辑账号（改名/换角色）───────────────────────
    def test_7_edit_account_rename_and_role_change(self):
        from accounts import create_account, update_account, get_account_by_id
        account = create_account("frank", "弗兰克", "frank_pass", ["developer"])
        aid = account["id"]
        updated = update_account(aid, display_name="弗兰克·李", role_ids=["admin"])
        self.assertEqual(updated["display_name"], "弗兰克·李")
        self.assertEqual(updated["role_ids"], ["admin"])
        # 从文件重新读取验证
        reloaded = get_account_by_id(aid)
        self.assertEqual(reloaded["display_name"], "弗兰克·李")


if __name__ == "__main__":
    unittest.main()
