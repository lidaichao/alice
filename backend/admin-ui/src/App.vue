<template>
  <el-container class="admin-layout">
    <el-aside width="240px" class="admin-aside">
      <div class="brand">
        <span class="brand-icon">🤖</span>
        <div>
          <div class="brand-title">爱丽丝 AI Gateway</div>
          <div class="brand-sub">后台管理系统</div>
        </div>
      </div>
      <el-menu
        :default-active="menuActive"
        class="admin-menu"
        @select="store.onMenuSelect"
      >
        <el-menu-item v-for="m in store.menus" :key="m.id" :index="m.id">
          <el-icon v-if="m.icon"><component :is="m.icon" /></el-icon>
          <span>{{ m.name }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header" height="56px">
        <h1 class="page-title">{{ store.currentMenuName }}</h1>
      </el-header>
      <el-main class="admin-main">
        <SettingsView v-show="store.activeMenu === 'settings'" />
        <JiraQueryView v-show="store.activeMenu === 'jiraQuery'" />
        <KnowledgeView v-show="store.activeMenu === 'kb'" />
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
const menuActive = computed(() => store.activeMenu.value ?? store.activeMenu);
provide('adminStore', store);
</script>

<style>
html,
body,
#app {
  margin: 0;
  height: 100%;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.admin-layout {
  height: 100vh;
}
.admin-aside {
  background: #1e293b;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  gap: 12px;
  padding: 20px 16px;
  border-bottom: 1px solid #334155;
}
.brand-icon {
  font-size: 28px;
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
  background: #334155;
  color: #fff;
}
.admin-header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}
.admin-main {
  background: #f1f5f9;
  overflow-y: auto;
}
</style>
