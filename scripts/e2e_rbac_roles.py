"""v1.10-rbac E2E — 角色权限管理全链路测试"""
import http.client
import json
import sys
import time

BASE = "127.0.0.1:9099"
HEADERS = {"Authorization": "Bearer admin-admin", "Content-Type": "application/json"}

OK = 0
FAIL = 0

def req(method, path, body=None):
    conn = http.client.HTTPConnection(BASE, timeout=10)
    conn.request(method, path, json.dumps(body) if body else None, HEADERS)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()
    return r.status, data

def check(label, condition, detail=""):
    global OK, FAIL
    if condition:
        OK += 1
        print(f"OK  {label}")
    else:
        FAIL += 1
        print(f"FAIL {label} {detail}")

# --- 1. 初始化预设角色 ---
status, data = req("GET", "/v1/admin/roles")
check("GET /v1/admin/roles", data.get("ok"), str(status))
roles = data.get("roles", [])
check("roles count >= 4", len(roles) >= 4, f"got {len(roles)}")
admin_role = next((r for r in roles if r.get("id") == "admin"), None)
check("admin role exists", admin_role is not None)

# --- 2. 新增自定义角色 ---
custom_role = {
    "id": "e2e-test-" + str(int(time.time())),
    "name": "E2E测试角色",
    "icon": "🧪",
    "description": "自动化测试",
    "members": ["testuser1", "testuser2"],
    "permissions": {"jira.read": True, "kb.read": True},
}
roles.append(custom_role)
status, data = req("POST", "/v1/admin/roles", {"roles": roles})
check("POST roles (create)", data.get("ok"), str(status))

# --- 3. 验证已保存 ---
status, data = req("GET", "/v1/admin/roles")
check("GET roles after save", data.get("ok"), str(status))
saved_roles = data.get("roles", [])
saved_custom = next((r for r in saved_roles if r.get("id") == custom_role["id"]), None)
check("custom role saved", saved_custom is not None)
check("custom role 2 members", saved_custom and len(saved_custom.get("members", [])) == 2)

# --- 4. 更新成员 ---
rid = custom_role["id"]
status, data = req("PUT", f"/v1/admin/roles/{rid}/members", {"members": ["userA", "userB", "userC"]})
check("PUT members", data.get("ok"), str(status))
check("members count = 3", len(data.get("members", [])) == 3, f"got {len(data.get('members', []))}")

# --- 5. 权限矩阵 ---
status, data = req("GET", "/v1/admin/permissions")
check("GET permissions", data.get("ok"), str(status))
perms = data.get("permissions", [])
check("permission defs exist", len(perms) > 0, f"got {len(perms)}")

# --- 6. 更新权限项 ---
status, data = req("POST", "/v1/admin/permissions", {
    "role_id": rid,
    "permission_key": "jira.write_create",
    "value": True,
})
check("POST toggle perm on", data.get("ok"), str(status))

# --- 7. 用户权限查询 ---
status, data = req("GET", "/v1/user/permissions?user_id=userA")
check("GET user perm", data.get("ok"), str(status))
check("userA has jira.write_create", "jira.write_create" in data.get("permissions", []),
      f"perms: {data.get('permissions')}")

# --- 8. 删除角色（有成员，应拒绝） ---
status, data = req("DELETE", f"/v1/admin/roles/{rid}")
check("DELETE role 409 (has members)", status == 409, f"status={status}")

# --- 9. 清空成员后删除 ---
req("PUT", f"/v1/admin/roles/{rid}/members", {"members": []})
status, data = req("DELETE", f"/v1/admin/roles/{rid}")
check("DELETE role OK", data.get("ok"), str(status))

# --- 10. 未配置用户无权限 ---
status, data = req("GET", "/v1/user/permissions?user_id=unknown_user_xyz")
check("unknown user no role", not data.get("role"), str(data.get("role")))
check("unknown user no perms", data.get("permissions", []) == [], str(data.get("permissions")))

# --- Summary ---
print(f"\n{'='*40}")
print(f"E2E_RBAC_ROLES_OK ({OK} passed, {FAIL} failed)")
sys.exit(0 if FAIL == 0 else 1)
