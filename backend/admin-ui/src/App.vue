<template>
  <LoginView v-if="!authenticated" />
  <el-container v-else class="admin-layout">
    <el-aside width="224px" class="admin-aside">
      <div class="brand">
        <span class="brand-mark">A</span>
        <div>
          <div class="brand-title">Alice Admin</div>
        </div>
      </div>
      <el-menu :key="menuActive" :default-active="menuActive" class="admin-menu" @select="store.onMenuSelect">
        <el-menu-item v-for="m in store.menus" :key="m.id" :index="m.id">
          <el-icon v-if="m.icon"><component :is="m.icon" /></el-icon>
          <span>{{ m.name }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header" height="56px">
        <div>
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-desc">{{ pageDesc }}</p>
        </div>
        <div v-if="store.healthSummary" class="health-strip">
          <span class="health-hub" :class="'hub-' + (store.healthSummary.status || 'ok')">
            Hub {{ store.healthSummary.status === 'degraded' ? '降级' : '正常' }}
          </span>
          <span v-for="key in ['jira', 'model', 'kb']" :key="key" class="health-pill"
            :title="store.healthSummary.integrations?.[key]?.detail">
            {{ key === 'jira' ? 'Jira' : key === 'model' ? '模型' : '知识库' }}：
            {{ store.integrationLabel(store.healthSummary.integrations?.[key]) }}
          </span>
          <el-button link type="primary" :loading="store.healthLoading" @click="store.fetchHealth">刷新探活</el-button>
        </div>
      </el-header>
      <el-main class="admin-main">
        <Transition name="page-fade" mode="out-in">
          <div :key="menuActive">
            <SettingsView v-show="menuActive === 'settings'" />
            <JiraQueryView v-show="menuActive === 'jiraQuery'" />
            <KnowledgeView v-show="menuActive === 'kb'" />
            <div v-show="menuActive === 'roles'" class="roles-tabs">
              <el-tabs v-model="rbacTab" class="rbac-tabs">
                <el-tab-pane label="账号管理" name="accounts"><AccountsView /></el-tab-pane>
                <el-tab-pane label="角色管理" name="roles"><RolesView /></el-tab-pane>
                <el-tab-pane label="权限配置" name="permissions"><PermissionsView /></el-tab-pane>
              </el-tabs>
            </div>
          </div>
        </Transition>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { provide, computed, ref, onMounted, onUnmounted } from 'vue';
import { useAdminStore } from './composables/useAdminStore.js';
import LoginView from './views/LoginView.vue';
import SettingsView from './views/SettingsView.vue';
import JiraQueryView from './views/JiraQueryView.vue';
import KnowledgeView from './views/KnowledgeView.vue';
import AccountsView from './views/AccountsView.vue';
import RolesView from './views/RolesView.vue';
import PermissionsView from './views/PermissionsView.vue';

const store = useAdminStore();
provide('adminStore', store);

const authenticated = ref(store.isAuthenticated());

// Phase 4.2: AbortController 生命周期（约束#15）
let abortCtrl = null;

onMounted(() => {
  abortCtrl = new AbortController();
  if (authenticated.value) {
    store.fetchHealth();
  }
});

onUnmounted(() => {
  if (abortCtrl) {
    abortCtrl.abort();
    abortCtrl = null;
  }
});

const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);
const menuActive = computed(() => unwrap(store.activeMenu));
const pageTitle = computed(() => unwrap(store.currentMenuName));

const pageDescMap = {
  settings: '管理 AI 接入、Jira 连接与 SVN',
  jiraQuery: '配置 Alice 协调员 Jira 查询与字段词典',
  kb: '配置 Notion 与 Google 云盘知识库源',
  roles: '管理账号、角色与权限配置矩阵',
};
const pageDesc = computed(() => pageDescMap[menuActive.value] || '');

const rbacTab = ref('accounts');
</script>

<style>
/* ── 设计令牌全局引用 ── */
@import './styles/design-tokens.css';

html, body, #app {
  margin: 0; height: 100%;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, sans-serif;
  background: var(--saas-bg-base);
}

.admin-layout { height: 100vh; }

/* ── 侧边栏：Jira 浅灰蓝 ── */
.admin-aside {
  background: var(--saas-sidebar-bg) !important;
  color: var(--saas-text-primary);
  display: flex; flex-direction: column;
  border-right: 1px solid var(--saas-border);
}

.brand {
  display: flex; gap: 12px; padding: 20px 16px;
  border-bottom: 1px solid var(--saas-border);
  align-items: center;
}
.brand-mark {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, #0c66e4, #0855c2);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 18px; color: #fff;
}
.brand-title {
  font-weight: 700; font-size: 15px; color: var(--saas-text-primary);
}

/* ── 菜单 ── */
.admin-menu {
  border-right: none !important; background: transparent !important; flex: 1; padding: 8px 0;
}
.admin-menu .el-menu-item {
  color: var(--saas-text-primary) !important;
  height: 40px; line-height: 40px; margin: 2px 8px;
  border-radius: var(--saas-radius-md);
  transition: background var(--saas-duration-fast) var(--saas-ease-standard);
  position: relative;
  font-size: 14px;
}
.admin-menu .el-menu-item:hover {
  background: var(--saas-sidebar-active) !important; color: var(--saas-text-primary) !important;
}
.admin-menu .el-menu-item.is-active {
  background: var(--saas-sidebar-active) !important;
  color: var(--saas-accent) !important;
  font-weight: 600;
}
/* 左侧指示条 */
.admin-menu .el-menu-item.is-active::before {
  content: '';
  position: absolute; left: 0; top: 8px; bottom: 8px;
  width: 3px; background: var(--saas-accent);
  border-radius: 0 2px 2px 0;
  animation: menu-indicator-in 0.2s var(--saas-ease-standard) forwards;
  transform-origin: center;
}
@keyframes menu-indicator-in {
  from { transform: scaleY(0); }
  to { transform: scaleY(1); }
}

.health-strip {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12px;
}
.health-hub { font-weight: 600; padding: 2px 8px; border-radius: 6px; background: #ecfdf5; color: #047857; }
.health-hub.hub-degraded { background: #fff7ed; color: #c2410c; }
.health-pill { padding: 2px 8px; border-radius: 6px; background: #f1f5f9; color: #475569; }

/* ── Header ── */
.admin-header {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  border-bottom: 1px solid var(--saas-border);
  background: rgba(255,255,255,0.92); backdrop-filter: blur(8px);
  box-shadow: var(--saas-shadow-sm); padding: 0 24px;
}
.page-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--saas-text-primary); }
.page-desc { margin: 4px 0 0; font-size: 12px; color: var(--saas-text-secondary); }
.admin-main { background: var(--saas-bg-base); overflow-y: auto; }

.roles-tabs { padding: 0; }
.rbac-tabs { --el-tabs-header-height: 40px; }

/* ── 全局 Element Plus 主题覆盖 ── */
:root {
  --el-color-primary: #0c66e4;
  --el-color-primary-light-3: #3b82f6;
  --el-color-primary-light-5: #60a5fa;
  --el-color-primary-light-7: #93c5fd;
  --el-color-primary-light-8: #bfdbfe;
  --el-color-primary-light-9: #dbeafe;
}

/* ── 按钮全局动画（卡罗尔 §3.6.1/3.6.2）── */
.el-button {
  transition: all var(--saas-duration-normal) var(--saas-ease-standard) !important;
}
.el-button--primary {
  background: var(--saas-accent) !important; border-color: var(--saas-accent) !important;
  box-shadow: var(--saas-shadow-sm);
}
.el-button--primary:hover {
  background: var(--saas-accent-hover) !important;
  box-shadow: var(--saas-shadow-md);
  transform: translateY(-1px);
}
.el-button--primary:active {
  transform: scale(0.98);
  box-shadow: var(--saas-shadow-sm);
}

/* ── 输入框全局覆盖（卡罗尔 §3.4）── */
.el-input__wrapper {
  border-color: var(--saas-border) !important;
  transition: border-color var(--saas-duration-fast) var(--saas-ease-standard),
              box-shadow var(--saas-duration-fast) var(--saas-ease-standard) !important;
}
.el-input.is-focus .el-input__wrapper {
  border-color: var(--saas-border-focus) !important;
  box-shadow: 0 0 0 3px rgba(12, 102, 228, 0.12) !important;
}

/* ── 卡片全局样式（卡罗尔 §3.4）── */
.config-card, .role-card {
  background: var(--saas-bg-surface); border: 1px solid var(--saas-border);
  border-radius: var(--saas-radius-xl); box-shadow: var(--saas-shadow-sm);
  transition: box-shadow var(--saas-duration-normal) var(--saas-ease-standard),
              transform var(--saas-duration-normal) var(--saas-ease-standard);
}
.config-card:hover, .role-card:hover {
  box-shadow: var(--saas-shadow-md);
  transform: translateY(-0.5px);
}

/* ── 弹窗动画（卡罗尔 §3.6.4）── */
.el-overlay { transition: opacity 0.15s ease; }

.el-dialog {
  border-radius: var(--saas-radius-xl) !important;
  box-shadow: var(--saas-shadow-lg) !important;
}
.el-dialog-enter-active {
  transition: all var(--saas-duration-normal) var(--saas-ease-standard) !important;
}
.el-dialog-enter-from {
  opacity: 0; transform: scale(0.95) translateY(8px);
}

/* ── 表格行 hover（卡罗尔 §3.6.8）── */
.el-table .el-table__body tr:hover > td {
  background: var(--saas-bg-hover) !important;
  transition: background var(--saas-duration-fast) ease;
}

/* ── 页面切换动画 ── */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity var(--saas-duration-normal) var(--saas-ease-standard),
              transform var(--saas-duration-normal) var(--saas-ease-standard);
}
.page-fade-enter-from { opacity: 0; transform: translateY(4px); }
.page-fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* ── Toast 通知系统（卡罗尔 §3.6.7）── */
.el-message {
  border-radius: var(--saas-radius-md) !important;
  box-shadow: var(--saas-shadow-md) !important;
  animation: toast-slide-in 0.25s var(--saas-ease-standard) forwards !important;
}
@keyframes toast-slide-in {
  from { opacity: 0; transform: translateX(100%); }
  to { opacity: 1; transform: translateX(0); }
}
</style>
