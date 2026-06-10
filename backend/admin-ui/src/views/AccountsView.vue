<template>
  <div class="accounts-page">
    <div class="page-header">
      <h2>账号管理</h2>
      <div class="page-header-right">
        <el-input v-model="searchQuery" placeholder="搜索用户名..." clearable style="width: 220px;" class="search-input" />
        <el-button type="primary" @click="openCreateModal">+ 创建账号</el-button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">加载中...</div>
    <div v-else-if="fetchError" class="error-state">
      <p>加载失败：{{ fetchError }}</p>
      <el-button size="small" @click="loadAll">重试</el-button>
    </div>
    <div v-else class="accounts-table-wrap">
      <el-table :data="filteredAccounts" stripe class="accounts-table" v-loading="loading">
        <el-table-column prop="username" label="用户名" min-width="120">
          <template #default="scope">
            <span class="account-username">{{ scope.row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" label="显示名" min-width="120" />
        <el-table-column label="角色" min-width="180">
          <template #default="scope">
            <el-tag v-for="rid in scope.row.role_ids" :key="rid" size="small" style="margin-right:4px;">
              {{ roleNameMap[rid] || rid }}
            </el-tag>
            <span v-if="!scope.row.role_ids?.length" class="no-role">未分配</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <span class="status-pill" :class="scope.row.disabled ? 'status-disabled' : 'status-active'">
              {{ scope.row.disabled ? '已禁用' : '正常' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最近登录" width="160">
          <template #default="scope">
            {{ scope.row.last_login_at || '从未登录' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="openEditModal(scope.row)">编辑</el-button>
            <el-button size="small" :type="scope.row.disabled ? 'success' : 'warning'"
              @click="toggleDisable(scope.row)">
              {{ scope.row.disabled ? '启用' : '禁用' }}
            </el-button>
            <el-popconfirm title="确定删除此账号？" @confirm="doDelete(scope.row)" confirm-button-text="确定"
              cancel-button-text="取消">
              <template #reference>
                <el-button size="small" type="danger" link>删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 创建/编辑弹窗 -->
    <el-dialog v-model="showModal" :title="editing ? '编辑账号' : '创建账号'" width="480px"
      class="account-dialog">
      <el-form label-position="top">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="例如：zhangsan" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="form.display_name" placeholder="例如：张三" />
        </el-form-item>
        <el-form-item label="密码" :required="!editing">
          <el-input v-model="form.password" type="password" show-password
            :placeholder="editing ? '留空则不修改' : '请输入密码'" />
        </el-form-item>
        <el-form-item label="分配角色">
          <el-select v-model="form.role_ids" multiple placeholder="选择角色" style="width:100%">
            <el-option v-for="r in roleOptions" :key="r.id" :label="r.icon + ' ' + r.name" :value="r.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showModal = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAccount">
          {{ editing ? '保存修改' : '创建账号' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue';
import { ElMessage } from 'element-plus';
import { adminFetch } from '../api/adminApi.js';

const store = inject('adminStore');

const accounts = ref([]);
const loading = ref(true);
const fetchError = ref('');
const searchQuery = ref('');
const showModal = ref(false);
const editing = ref(null);
const saving = ref(false);
const form = reactive({ username: '', display_name: '', password: '', role_ids: [] });
const roleOptions = ref([]);
const roleNameMap = reactive({});

const filteredAccounts = computed(() => {
  const q = (searchQuery.value || '').trim().toLowerCase();
  if (!q) return accounts.value;
  return accounts.value.filter(a =>
    (a.username || '').toLowerCase().includes(q) ||
    (a.display_name || '').toLowerCase().includes(q)
  );
});

const fetchAccounts = async () => {
  try {
    const res = await adminFetch('/v1/admin/accounts');
    const data = await res.json();
    if (data.ok) accounts.value = data.accounts || [];
    else throw new Error(data.error || '加载失败');
  } catch (e) {
    fetchError.value = e.message || '加载账号失败';
  }
};

const fetchRoles = async () => {
  try {
    const res = await adminFetch('/v1/admin/roles');
    const data = await res.json();
    if (data.ok) {
      roleOptions.value = data.roles || [];
      roleOptions.value.forEach(r => { roleNameMap[r.id] = (r.icon || '') + ' ' + r.name; });
    }
  } catch { /* 静默忽略 */ }
};

const loadAll = async () => {
  loading.value = true;
  fetchError.value = '';
  await Promise.all([fetchAccounts(), fetchRoles()]);
  loading.value = false;
};

const openCreateModal = () => {
  editing.value = null;
  form.username = ''; form.display_name = ''; form.password = ''; form.role_ids = [];
  showModal.value = true;
};

const openEditModal = (account) => {
  editing.value = account;
  form.username = account.username;
  form.display_name = account.display_name || '';
  form.password = '';
  form.role_ids = [...(account.role_ids || [])];
  showModal.value = true;
};

const saveAccount = async () => {
  if (!(form.username || '').trim()) { ElMessage.error('请输入用户名'); return; }
  if (!editing.value && !form.password) { ElMessage.error('请输入密码'); return; }
  saving.value = true;
  try {
    const body = { username: form.username.trim(), display_name: form.display_name.trim() || form.username.trim(), role_ids: form.role_ids };
    if (form.password) body.password = form.password;
    let res;
    if (editing.value) {
      if (!form.password) delete body.password;
      res = await adminFetch('/v1/admin/accounts/' + editing.value.id, { method: 'PUT', body: JSON.stringify(body) });
    } else {
      res = await adminFetch('/v1/admin/accounts', { method: 'POST', body: JSON.stringify(body) });
    }
    const data = await res.json();
    if (data.ok) {
      ElMessage.success(editing.value ? '账号已更新' : '账号已创建');
      showModal.value = false;
      loadAll();
    } else ElMessage.error(data.error || '操作失败');
  } catch (e) { ElMessage.error('操作失败: ' + e.message); }
  saving.value = false;
};

const toggleDisable = async (account) => {
  try {
    const res = await adminFetch('/v1/admin/accounts/' + account.id, {
      method: 'PUT', body: JSON.stringify({ disabled: !account.disabled }),
    });
    const data = await res.json();
    if (data.ok) { account.disabled = !account.disabled; ElMessage.success(account.disabled ? '已禁用' : '已启用'); }
    else ElMessage.error(data.error || '操作失败');
  } catch (e) { ElMessage.error('操作失败'); }
};

const doDelete = async (account) => {
  try {
    const res = await adminFetch('/v1/admin/accounts/' + account.id, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) { accounts.value = accounts.value.filter(a => a.id !== account.id); ElMessage.success('账号已删除'); }
    else ElMessage.error(data.error || '删除失败');
  } catch (e) { ElMessage.error('删除失败'); }
};

onMounted(() => { loadAll(); });
</script>

<style scoped>
.accounts-page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--saas-text-primary); }
.page-header-right { display: flex; align-items: center; gap: 12px; }
.search-input { --el-input-border-radius: var(--saas-radius-md); }
.loading-state { text-align: center; padding: 48px 0; color: #94a3b8; }
.error-state { text-align: center; padding: 32px 0; color: #ae2a19; }
.accounts-table-wrap { background: var(--saas-bg-surface); border: 1px solid var(--saas-border); border-radius: var(--saas-radius-lg); overflow: hidden; box-shadow: var(--saas-shadow-sm); }
.account-username { font-weight: 600; color: var(--saas-text-primary); }
.no-role { font-size: 12px; color: var(--saas-text-tertiary); }
.status-pill { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.status-active { background: #dcfff1; color: #1f845a; }
.status-disabled { background: #fff3e0; color: #e56910; }
</style>
