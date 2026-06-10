/**
 * PermissionsView — 权限配置矩阵（Admin 后台「👥 成员与权限」Tab 2）
 * 对齐 Carroll PRD v1.0 §域 B（B1–B6）
 *
 * 矩阵布局：一行一个角色 / 一列一个权限项 / 勾选即保存
 */
const PermissionsView = {
  /**
   * 权限项定义（用于矩阵列）
   */
  PERMISSION_GROUPS: [
    {
      label: '📁 Jira 操作',
      key: 'jira',
      items: [
        { key: 'jira.read', label: '查阅' },
        { key: 'jira.write_create', label: '创建' },
        { key: 'jira.write_update', label: '修改' },
        { key: 'jira.write_comment', label: '评论' },
      ],
    },
    {
      label: '📚 知识库',
      key: 'kb',
      items: [
        { key: 'kb.read', label: '查阅' },
        { key: 'kb.manage', label: '管理' },
        { key: 'kb.rebuild_index', label: '索引重建' },
        { key: 'kb.doc_crud', label: '文档增删' },
      ],
    },
    {
      label: '💻 工作区',
      key: 'workspace',
      items: [
        { key: 'workspace.read_code', label: '阅读代码' },
        { key: 'workspace.run_workflow', label: '运行工作流' },
      ],
    },
    {
      label: '📋 审计',
      key: 'audit',
      items: [
        { key: 'audit.read', label: '查阅日志' },
        { key: 'audit.manage', label: '管理审计' },
      ],
    },
    {
      label: '⚙️ 系统',
      key: 'system',
      items: [
        { key: 'system.manage', label: '系统配置' },
      ],
    },
  ],

  /** isAdmin 通配 */
  isAdmin(role) {
    return role && role.permissions && role.permissions['*'] === true;
  },

  /**
   * 更新角色权限
   */
  async togglePermission(adminFetch, roles, roleId, permKey, value, saveStatus, toast) {
    const role = roles.find(r => r.id === roleId);
    if (!role) return;
    // 乐观 UI
    if (value) {
      role.permissions[permKey] = true;
    } else {
      delete role.permissions[permKey];
    }
    saveStatus.msg = '保存中...';
    saveStatus.saving = true;
    // debounce 800ms
    clearTimeout(saveStatus._timer);
    saveStatus._timer = setTimeout(async () => {
      try {
        const res = await adminFetch('/v1/admin/permissions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role_id: roleId, permission_key: permKey, value }),
        });
        const data = await res.json();
        if (data.ok) {
          saveStatus.msg = '已保存 ✅';
          setTimeout(() => { saveStatus.msg = ''; saveStatus.saving = false; }, 1500);
        } else {
          // 回滚
          saveStatus.msg = '保存失败 🔴';
          saveStatus.saving = false;
          if (value) delete role.permissions[permKey];
          else role.permissions[permKey] = true;
          toast(data.error || '保存失败', 'error');
        }
      } catch (e) {
        saveStatus.msg = '保存失败 🔴';
        saveStatus.saving = false;
        if (value) delete role.permissions[permKey];
        else role.permissions[permKey] = true;
        toast('保存失败: ' + e.message, 'error');
      }
    }, 800);
  },

  /**
   * 全选/取消该组
   */
  toggleGroup(adminFetch, roles, roleId, group, allOn, saveStatus, toast) {
    const role = roles.find(r => r.id === roleId);
    if (!role || this.isAdmin(role)) return;
    for (const item of group.items) {
      if (allOn) {
        role.permissions[item.key] = true;
      } else {
        delete role.permissions[item.key];
      }
    }
    // Save via batch (one permission at a time)
    // For simplicity, just save each
    for (const item of group.items) {
      this.togglePermission(adminFetch, roles, roleId, item.key, allOn, saveStatus, toast);
    }
  },
};

if (typeof module !== 'undefined' && module.exports) module.exports = PermissionsView;
