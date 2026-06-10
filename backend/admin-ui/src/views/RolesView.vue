<template>
  <div class="roles-page">
    <div class="page-header">
      <h2>角色管理</h2>
      <el-button type="primary" @click="openRoleModal()">+ 新建角色</el-button>
    </div>

    <div v-if="loading" class="loading-state">加载中…</div>
    <div v-else-if="fetchError" class="error-state">
      <p>加载失败：{{ fetchError }}</p>
      <el-button size="small" @click="fetchRoles">重试</el-button>
    </div>
    <div v-else class="roles-grid">
      <div v-for="role in roles" :key="role.id" class="role-card" :class="'role-' + role.id">
        <div class="role-left">
          <span class="role-icon">{{ role.icon }}</span>
          <div class="role-info">
            <h3 class="role-name">{{ role.name }}</h3>
            <p class="role-desc">{{ role.description || '无描述' }}</p>
            <el-tag size="small" type="info">{{ role.member_count || (role.members || []).length || 0 }} 名成员</el-tag>
          </div>
        </div>
        <div class="role-actions">
          <el-button size="small" @click="openMemberModal(role)">管理账号</el-button>
          <el-button size="small" @click="openRoleModal(role)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="deleteRole(role)">删除</el-button>
        </div>
      </div>
    </div>

    <!-- 角色编辑弹窗 -->
    <el-dialog v-model="showRoleModal" :title="editingRole ? '编辑角色' : '✨ 新建角色'" width="480px">
      <el-form label-position="top">
        <el-form-item label="角色名称">
          <el-input v-model="roleForm.name" placeholder="例如：测试主管" />
        </el-form-item>
        <el-form-item label="角色描述">
          <el-input v-model="roleForm.description" placeholder="简要描述角色职责" />
        </el-form-item>
        <el-form-item label="角色图标">
          <div class="icon-picker">
            <el-button v-for="icon in iconOptions" :key="icon" :type="roleForm.icon === icon ? 'primary' : ''"
              size="small" @click="roleForm.icon = icon" class="icon-btn">{{ icon }}</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="!editingRole" label="📋 权限预设">
          <el-select v-model="roleForm.copyFrom" placeholder="从空白开始" clearable style="width:100%">
            <el-option v-for="r in roles" :key="r.id" :label="'复制「' + r.name + '」的权限'" :value="r.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRoleModal = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存角色</el-button>
      </template>
    </el-dialog>

    <!-- 成员管理弹窗 -->
    <el-dialog v-model="showMemberModal" title="管理成员" width="520px">
      <div class="member-add-row">
        <el-input v-model="memberSearch" placeholder="输入用户ID，回车添加" @keyup.enter="addMember(memberSearch)" />
        <el-button type="primary" @click="addMember(memberSearch)">添加</el-button>
      </div>
      <div class="member-list">
        <div v-for="m in memberList" :key="m" class="member-item">
          <span>{{ m }}</span>
          <el-button size="small" type="danger" link @click="removeMember(m)">移除</el-button>
        </div>
        <div v-if="!memberList.length" class="empty-hint">暂无成员</div>
      </div>
      <template #footer>
        <el-button @click="showMemberModal = false">取消</el-button>
        <el-button type="primary" @click="saveMembers">保存成员</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, inject } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { adminFetch } from '../api/adminApi.js';

const store = inject('adminStore');

const iconOptions = ['🛡️', '👔', '💻', '👁️', '🔧', '📝', '🎨', '📊', '🧪'];

const roles = ref([]);
const loading = ref(true);
const fetchError = ref('');
const showRoleModal = ref(false);
const editingRole = ref(null);
const roleForm = reactive({ name: '', description: '', icon: '👤', copyFrom: '' });
const showMemberModal = ref(false);
const memberRoleId = ref('');
const memberSearch = ref('');
const memberList = ref([]);

const fetchRoles = async () => {
  loading.value = true;
  fetchError.value = '';
  try {
    const res = await adminFetch('/v1/admin/roles');
    const data = await res.json();
    if (data.ok) roles.value = data.roles || [];
    else fetchError.value = data.error || '加载失败';
  } catch (e) { fetchError.value = e.message || '加载角色失败'; }
  loading.value = false;
};

const openRoleModal = (role = null) => {
  editingRole.value = role;
  if (role) {
    roleForm.name = role.name; roleForm.description = role.description || '';
    roleForm.icon = role.icon || '👤'; roleForm.copyFrom = '';
  } else {
    roleForm.name = ''; roleForm.description = ''; roleForm.icon = '👤'; roleForm.copyFrom = '';
  }
  showRoleModal.value = true;
};

const saveRole = async () => {
  if (!(roleForm.name || '').trim()) { ElMessage.error('请输入角色名称'); return; }
  const all = [...(roles.value || [])];
  if (editingRole.value) {
    const idx = all.findIndex(r => r.id === editingRole.value.id);
    if (idx >= 0) { all[idx] = { ...all[idx], name: roleForm.name.trim(), description: (roleForm.description || '').trim(), icon: roleForm.icon }; }
  } else {
    let perms = {};
    if (roleForm.copyFrom) { const src = all.find(r => r.id === roleForm.copyFrom); if (src) perms = { ...(src.permissions || {}) }; }
    all.push({ id: 'custom-' + Date.now(), name: roleForm.name.trim(), description: (roleForm.description || '').trim(), icon: roleForm.icon, members: [], permissions: perms });
  }
  try {
    const res = await adminFetch('/v1/admin/roles', { method: 'POST', body: JSON.stringify({ roles: all }) });
    const data = await res.json();
    if (data.ok) { roles.value = all; showRoleModal.value = false; ElMessage.success('角色已保存'); }
    else ElMessage.error(data.error || '保存失败');
  } catch (e) { ElMessage.error('保存失败: ' + e.message); }
};

const deleteRole = async (role) => {
  try {
    await ElMessageBox.confirm(
      `确定删除角色「${role.name}」？${(role.member_count || 0) ? `⚠️ ${role.member_count} 名成员将失去权限` : ''}`,
      '删除角色', { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    );
    const res = await adminFetch('/v1/admin/roles/' + role.id, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) { roles.value = roles.value.filter(r => r.id !== role.id); ElMessage.success('角色已删除'); }
    else ElMessage.error(data.error || '删除失败');
  } catch { /* cancelled */ }
};

const openMemberModal = (role) => { memberRoleId.value = role.id; memberList.value = [...(role.members || [])]; showMemberModal.value = true; };
const addMember = (uid) => { const u = (uid || '').trim(); if (u && !memberList.value.includes(u)) memberList.value.push(u); memberSearch.value = ''; };
const removeMember = (uid) => { memberList.value = memberList.value.filter(m => m !== uid); };
const saveMembers = async () => {
  try {
    const res = await adminFetch('/v1/admin/roles/' + memberRoleId.value + '/members', { method: 'PUT', body: JSON.stringify({ members: memberList.value }) });
    const data = await res.json();
    if (data.ok) {
      const role = roles.value.find(r => r.id === memberRoleId.value);
      if (role) { role.members = memberList.value; role.member_count = memberList.value.length; }
      showMemberModal.value = false; ElMessage.success('成员已更新');
    } else ElMessage.error(data.error || '保存失败');
  } catch (e) { ElMessage.error('保存失败: ' + e.message); }
};

fetchRoles();
</script>

<style scoped>
.roles-page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--saas-text-primary); }
.loading-state { text-align: center; padding: 48px 0; color: #94a3b8; }
.roles-grid { display: flex; flex-direction: column; gap: 12px; }
.role-card {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--saas-bg-surface); border: 1px solid var(--saas-border);
  border-left: 3px solid var(--saas-border);
  border-radius: var(--saas-radius-lg); padding: 16px 20px; gap: 16px;
  box-shadow: var(--saas-shadow-sm);
  transition: box-shadow var(--saas-duration-normal) var(--saas-ease-standard),
              transform var(--saas-duration-normal) var(--saas-ease-standard);
}
.role-card:hover {
  box-shadow: var(--saas-shadow-md);
  transform: translateY(-0.5px);
}
/* ── 色彩左边框（卡罗尔 §3.2）── */
.role-card.role-admin { border-left-color: #8270db; }
.role-card.role-project_manager { border-left-color: #2897bd; }
.role-card.role-developer { border-left-color: #1f845a; }
.role-card.role-guest { border-left-color: var(--saas-border); }
.role-left { display: flex; align-items: flex-start; gap: 12px; flex: 1; min-width: 0; }
.role-icon { font-size: 24px; line-height: 1; }
.role-info { min-width: 0; }
.role-name { margin: 0; font-size: 15px; font-weight: 600; color: var(--saas-text-primary); }
.role-desc { margin: 4px 0 8px; font-size: 13px; color: var(--saas-text-secondary); }
.role-actions { display: flex; gap: 6px; flex-shrink: 0; }
.icon-picker { display: flex; flex-wrap: wrap; gap: 4px; }
.icon-btn { min-width: 36px; padding: 4px 8px; }
.member-add-row { display: flex; gap: 8px; margin-bottom: 12px; }
.member-add-row .el-input { flex: 1; }
.member-list { max-height: 260px; overflow-y: auto; }
.member-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: var(--saas-bg-base); border-radius: var(--saas-radius-sm); margin-bottom: 4px; font-size: 14px; }
.empty-hint { text-align: center; padding: 24px 0; color: var(--saas-text-tertiary); font-size: 14px; }
</style>
