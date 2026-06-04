<template>
  <el-container class="admin-layout">
    <el-aside width="240px" class="admin-aside">
      <div class="brand">
        <span class="brand-mark">A</span>
        <div>
          <div class="brand-title">爱丽丝 AI Gateway</div>
          <div class="brand-sub">后台管理系统</div>
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
      </el-header>
      <el-main class="admin-main">
        <Transition name="page-fade" mode="out-in">
          <div :key="menuActive">
            <SettingsView v-show="menuActive === 'settings'" />
            <JiraQueryView v-show="menuActive === 'jiraQuery'" />
            <KnowledgeView v-show="menuActive === 'kb'" />
          </div>
        </Transition>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { provide, computed } from 'vue';
import { useAdminStore } from './composables/useAdminStore.js';
import SettingsView from './views/SettingsView.vue';
import JiraQueryView from './views/JiraQueryView.vue';
import KnowledgeView from './views/KnowledgeView.vue';

const store = useAdminStore();
provide('adminStore', store);

const unwrap = (v) => (v && typeof v === 'object' && 'value' in v ? v.value : v);
const menuActive = computed(() => unwrap(store.activeMenu));
const pageTitle = computed(() => unwrap(store.currentMenuName));

const pageDescMap = {
  settings: '管理 AI 接入、Jira 连接与 SVN',
  jiraQuery: '配置 Alice 协调员 Jira 查询与字段词典',
  kb: '配置 Notion 与 Google 云盘知识库源',
};
const pageDesc = computed(() => pageDescMap[menuActive.value] || '');
</script>

<style>
html,
body,
#app {
  margin: 0;
  height: 100%;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
}

.admin-layout {
  height: 100vh;
}

.admin-aside {
  background: linear-gradient(180deg, #1e3a5f 0%, #1e293b 100%);
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  gap: 12px;
  padding: 20px 16px;
  border-bottom: 1px solid #334155;
  align-items: center;
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1 0%, #2563eb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
}

.brand-title {
  font-weight: 700;
  font-size: 15px;
  color: #f8fafc;
}

.brand-sub {
  font-size: 12px;
  color: #94a3b8;
}

.admin-menu {
  border-right: none;
  background: transparent;
  flex: 1;
}

.admin-menu .el-menu-item {
  color: #cbd5e1;
}

.admin-menu .el-menu-item.is-active {
  background: rgb(255 255 255 / 8%);
  color: #fff;
  border-left: 3px solid #60a5fa;
}

.admin-header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--admin-border);
  background: rgb(255 255 255 / 92%);
  backdrop-filter: blur(8px);
  box-shadow: var(--shadow-1);
  padding: 0 24px;
}

.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--admin-text-primary);
}

.page-desc {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--admin-text-secondary);
}

.admin-main {
  background: var(--admin-bg-page);
  overflow-y: auto;
}
</style>
