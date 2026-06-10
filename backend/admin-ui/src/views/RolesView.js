/**
 * RolesView — 角色管理（Admin 后台「👥 成员与权限」Tab 1）
 * 对齐 Carroll PRD v1.0 §域 A（A1–A6）
 *
 * 用法：嵌入 admin.html Vue 实例的 rbacRoles 响应式中
 */
const RolesView = {
  // ══════════════════════════════════════════════
  //  角色图标预设
  // ══════════════════════════════════════════════
  ICON_OPTIONS: ["🛡️", "👔", "💻", "👁️", "🔧", "📝", "🎨", "📊", "🧪", "🗂️"],

  /**
   * 初始化 rbacRoles reactive 状态
   * @param {object} adminFetch - admin.html 的 fetch 包装函数
   */
  initState(adminFetch) {
    return {
      // roles 列表
      roles: [],
      loading: true,
      activeTab: 'roles', // 'roles' | 'permissions'
      // 新建/编辑弹窗
      showRoleModal: false,
      editingRole: null, // null=新建，obj=编辑
      roleForm: { name: '', description: '', icon: '👤', copyFrom: '' },
      // 成员管理弹窗
      showMemberModal: false,
      memberRoleId: '',
      memberSearch: '',
      memberList: [],
      memberAllUsers: [],
    };
  },

  /**
   * 加载角色列表
   */
  async fetchRoles(adminFetch, state) {
    state.loading = true;
    try {
      const res = await adminFetch('/v1/admin/roles');
      const data = await res.json();
      if (data.ok) {
        state.roles = data.roles || [];
        state.permissions = data.permission_defs || [];
      }
    } catch (e) { console.error('RolesView fetchRoles:', e); }
    state.loading = false;
  },

  /**
   * 保存角色
   */
  async saveRole(adminFetch, state, toast) {
    const form = state.roleForm;
    if (!(form.name || '').trim()) {
      toast('请输入角色名称', 'error');
      return;
    }
    const roles = [...(state.roles || [])];
    if (state.editingRole) {
      const idx = roles.findIndex(r => r.id === state.editingRole.id);
      if (idx >= 0) {
        roles[idx] = {
          ...roles[idx],
          name: form.name.trim(),
          description: (form.description || '').trim(),
          icon: form.icon,
        };
      }
    } else {
      const id = 'custom-' + Date.now();
      let perms = {};
      if (form.copyFrom) {
        const src = roles.find(r => r.id === form.copyFrom);
        if (src) perms = { ...(src.permissions || {}) };
      }
      roles.push({
        id,
        name: form.name.trim(),
        description: (form.description || '').trim(),
        icon: form.icon,
        members: [],
        permissions: perms,
      });
    }
    try {
      const res = await adminFetch('/v1/admin/roles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roles }),
      });
      const data = await res.json();
      if (data.ok) {
        state.roles = roles;
        state.showRoleModal = false;
        toast('角色已保存');
      } else {
        toast(data.error || '保存失败', 'error');
      }
    } catch (e) { toast('保存失败: ' + e.message, 'error'); }
  },

  /**
   * 删除角色
   */
  async deleteRole(adminFetch, state, role, toast) {
    if (!confirm(`确定删除角色「${role.name}」？${role.member_count ? `⚠️ ${role.member_count} 名成员将失去权限` : ''}`)) return;
    try {
      const res = await adminFetch(`/v1/admin/roles/${role.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.ok) {
        state.roles = state.roles.filter(r => r.id !== role.id);
        toast('角色已删除');
      } else {
        toast(data.error || '删除失败', 'error');
      }
    } catch (e) { toast('删除失败: ' + e.message, 'error'); }
  },

  /**
   * 打开角色编辑弹窗
   */
  openRoleModal(state, role = null) {
    state.editingRole = role;
    if (role) {
      state.roleForm = {
        name: role.name,
        description: role.description || '',
        icon: role.icon || '👤',
        copyFrom: '',
      };
    } else {
      state.roleForm = { name: '', description: '', icon: '👤', copyFrom: '' };
    }
    state.showRoleModal = true;
  },

  /**
   * 打开成员管理弹窗
   */
  async openMemberModal(adminFetch, state, role) {
    state.memberRoleId = role.id;
    state.memberList = role.members || [];
    state.showMemberModal = true;
  },

  /**
   * 保存成员变更
   */
  async saveMembers(adminFetch, state, toast) {
    try {
      const res = await adminFetch(`/v1/admin/roles/${state.memberRoleId}/members`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ members: state.memberList }),
      });
      const data = await res.json();
      if (data.ok) {
        const role = state.roles.find(r => r.id === state.memberRoleId);
        if (role) { role.members = state.memberList; role.member_count = state.memberList.length; }
        state.showMemberModal = false;
        toast('成员已更新');
      } else {
        toast(data.error || '保存失败', 'error');
      }
    } catch (e) { toast('保存失败: ' + e.message, 'error'); }
  },

  /**
   * 添加成员
   */
  addMember(state, userId) {
    const uid = (userId || '').trim();
    if (!uid) return;
    if (!state.memberList.includes(uid)) {
      state.memberList.push(uid);
    }
    state.memberSearch = '';
  },

  /**
   * 移除成员
   */
  removeMember(state, userId) {
    state.memberList = state.memberList.filter(m => m !== userId);
  },
};

if (typeof module !== 'undefined' && module.exports) module.exports = RolesView;
