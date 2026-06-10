<template>
  <div class="perms-page">
    <div class="page-header">
      <h2>权限配置矩阵</h2>
      <span v-if="saveStatus.msg" :class="saveStatus.saving ? 'status-saving' : 'status-ok'">{{ saveStatus.msg }}</span>
    </div>

    <div v-if="fetchError" class="error-state">
      <p>加载失败：{{ fetchError }}</p>
      <el-button size="small" @click="fetchRoles">重试</el-button>
    </div>

    <div v-else class="matrix-card">
      <table class="matrix-table">
        <thead>
          <tr>
            <th class="role-col">角色</th>
            <th v-for="pg in permGroups" :key="pg.key" :colspan="pg.items.length"
              class="group-col">
              <el-button link size="small" @click="pg.collapsed = !pg.collapsed">
                {{ pg.collapsed ? '▶' : '▼' }} {{ pg.label }}
              </el-button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="role in roles" :key="'r-' + role.id" class="perm-row">
            <td class="role-cell">
              <span class="role-label">{{ role.icon }} {{ role.name }}</span>
              <span class="role-count">{{ role.member_count || (role.members || []).length || 0 }}成员</span>
            </td>
            <template v-for="pg in permGroups" :key="'pg-' + role.id + '-' + pg.key">
              <template v-if="!pg.collapsed">
                <td v-for="item in pg.items" :key="'pi-' + role.id + '-' + item.key" class="perm-cell">
                  <span v-if="role.id === 'admin'" class="check-admin">
                    🔒 <span class="check-admin-icon">☑</span>
                  </span>
                  <el-button v-else link
                    :class="role.permissions[item.key] ? 'check-on' : 'check-off'"
                    @click="togglePerm(role.id, item.key, !(role.permissions[item.key]))">
                    {{ role.permissions[item.key] ? '☑' : '☐' }}
                  </el-button>
                </td>
              </template>
            </template>
          </tr>
        </tbody>
      </table>
      <div class="matrix-footer">
        💡 勾选即保存。折叠/展开分组。管理员通配全部权限。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, inject } from 'vue';
import { ElMessage } from 'element-plus';
import { adminFetch } from '../api/adminApi.js';

const store = inject('adminStore');
const adminToken = store?.adminToken;

const roles = ref([]);
const fetchError = ref('');
const saveStatus = reactive({ msg: '', saving: false });
let _timer = null;

const permGroups = ref([
  { key: 'jira', label: '📁 Jira 操作', collapsed: false, items: [{ key: 'jira.read', label: '查阅' }, { key: 'jira.write_create', label: '创建' }, { key: 'jira.write_update', label: '修改' }, { key: 'jira.write_comment', label: '评论' }] },
  { key: 'kb', label: '📚 知识库', collapsed: true, items: [{ key: 'kb.read', label: '查阅' }, { key: 'kb.manage', label: '管理' }, { key: 'kb.rebuild_index', label: '索引重建' }, { key: 'kb.doc_crud', label: '文档增删' }] },
  { key: 'workspace', label: '💻 工作区', collapsed: true, items: [{ key: 'workspace.read_code', label: '阅读代码' }, { key: 'workspace.run_workflow', label: '运行工作流' }] },
  { key: 'audit', label: '📋 审计', collapsed: true, items: [{ key: 'audit.read', label: '查阅日志' }, { key: 'audit.manage', label: '管理审计' }] },
  { key: 'system', label: '⚙️ 系统', collapsed: true, items: [{ key: 'system.manage', label: '系统配置' }] },
]);

const fetchRoles = async () => {
  fetchError.value = '';
  try {
    const res = await adminFetch('/v1/admin/permissions');
    const data = await res.json();
    if (data.ok) roles.value = data.roles || [];
    else fetchError.value = data.error || '加载失败';
  } catch (e) {
    fetchError.value = e.message || '加载权限矩阵失败';
  }
};

const togglePerm = (roleId, permKey, value) => {
  const role = roles.value.find(r => r.id === roleId);
  if (!role) return;
  if (value) role.permissions[permKey] = true; else delete role.permissions[permKey];
  saveStatus.msg = '保存中...'; saveStatus.saving = true;
  clearTimeout(_timer);
  _timer = setTimeout(async () => {
    try {
      const res = await adminFetch('/v1/admin/permissions', { method: 'POST', body: JSON.stringify({ role_id: roleId, permission_key: permKey, value }) });
      const data = await res.json();
      if (data.ok) { saveStatus.msg = '已保存 ✅'; setTimeout(() => { saveStatus.msg = ''; saveStatus.saving = false; }, 1500); }
      else { saveStatus.msg = '保存失败 🔴'; saveStatus.saving = false; if (value) delete role.permissions[permKey]; else role.permissions[permKey] = true; ElMessage.error(data.error || '保存失败'); }
    } catch (e) { saveStatus.msg = '保存失败 🔴'; saveStatus.saving = false; if (value) delete role.permissions[permKey]; else role.permissions[permKey] = true; }
  }, 800);
};

fetchRoles();
</script>

<style scoped>
.perms-page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--saas-text-primary); }
.status-saving { font-size: 12px; color: #d97706; }
.status-ok { font-size: 12px; color: #059669; }
.error-state { text-align: center; padding: 32px 0; color: #ae2a19; }
.matrix-card { background: var(--saas-bg-surface); border: 1px solid var(--saas-border); border-radius: var(--saas-radius-lg); overflow: hidden; box-shadow: var(--saas-shadow-sm); }
.matrix-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.matrix-table th { background: var(--saas-bg-base); padding: 10px 8px; text-align: center; font-weight: 600; color: var(--saas-text-primary); border-bottom: 1px solid var(--saas-border); white-space: nowrap; }
.matrix-table .role-col { text-align: left; padding-left: 16px; min-width: 130px; }
.matrix-table .group-col { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--saas-text-secondary); }
.perm-row { border-bottom: 1px solid var(--saas-border); }
.perm-row:hover { background: var(--saas-bg-hover); transition: background var(--saas-duration-fast) ease; }
.role-cell { padding: 10px 8px 10px 16px; }
.role-label { font-weight: 600; color: var(--saas-text-primary); display: block; }
.role-count { font-size: 11px; color: var(--saas-text-tertiary); }
.perm-cell { text-align: center; padding: 10px 4px; }
.check-admin { color: var(--saas-text-tertiary); font-size: 13px; cursor: default; display: inline-flex; align-items: center; gap: 2px; }
.check-admin-icon { font-size: 16px; color: #9ca3af; }
.check-on { font-size: 18px; color: var(--saas-accent); cursor: pointer; }
.check-off { font-size: 18px; color: #d1d5db; cursor: pointer; }
.check-off:hover { color: #6366f1; }
.check-on:active {
  animation: checkbox-bounce 0.18s var(--saas-ease-bounce);
}
@keyframes checkbox-bounce {
  0% { transform: scale(0.9); }
  50% { transform: scale(1.1); }
  100% { transform: scale(1); }
}
.matrix-footer { padding: 10px 16px; background: #f9fafb; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; font-style: italic; }
</style>
