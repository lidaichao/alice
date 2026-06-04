<template>
  <div class="view-wrap">
    <el-card shadow="never" class="mb-4" :class="{ 'card-editing': s.editLock.notion }">
      <template #header>
        <div class="card-header">
          <span>📝 Notion 知识库</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="s.testing.notion"
              :disabled="s.editLock.notion"
              @click="s.testNotionSystem"
            >
              测试并拉取数据库
            </el-button>
            <el-button v-if="!s.editLock.notion" size="small" type="primary" link @click="s.startEdit('notion')">
              编辑配置
            </el-button>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Notion API Key">
              <el-input
                v-model="s.state.kb.NOTION_KEY"
                type="password"
                show-password
                :readonly="!s.editLock.notion"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Notion 数据库 ID">
              <el-input
                v-model="s.state.kb.NOTION_DATABASE_ID"
                :readonly="!s.editLock.notion"
                placeholder="粘贴链接自动剥离 ID"
                @blur="s.parseNotionUrl"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div v-if="s.notionDatabases.length" class="db-list">
        <p class="list-title">已发现的可用数据库：</p>
        <ul>
          <li v-for="db in s.notionDatabases" :key="db.id">
            {{ db.title }}
            <el-button
              v-if="s.editLock.notion"
              link
              type="primary"
              size="small"
              @click="s.state.kb.NOTION_DATABASE_ID = db.id.replace(/-/g, '')"
            >
              使用此 ID
            </el-button>
          </li>
        </ul>
      </div>
      <div v-if="s.editLock.notion" class="card-footer">
        <el-button @click="s.cancelEdit('notion')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('notion')">保存 Notion</el-button>
      </div>
    </el-card>

    <el-card shadow="never" :class="{ 'card-editing': s.editLock.gdrive }">
      <template #header>
        <div class="card-header">
          <span>📁 Google 云盘知识库</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="s.testing.gdrive"
              :disabled="s.editLock.gdrive"
              @click="s.testGDriveSystem"
            >
              测试网络可达性
            </el-button>
            <el-button v-if="!s.editLock.gdrive" size="small" type="primary" link @click="s.startEdit('gdrive')">
              编辑配置
            </el-button>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <el-form-item label="Google API Key (Service Account)">
          <el-input
            v-model="s.state.kb.GDRIVE_KEY"
            type="password"
            show-password
            :readonly="!s.editLock.gdrive"
          />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="局域网代理 IP">
              <el-input v-model="s.state.kb.GDRIVE_PROXY_IP" :readonly="!s.editLock.gdrive" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="代理端口">
              <el-input v-model="s.state.kb.GDRIVE_PROXY_PORT" :readonly="!s.editLock.gdrive" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="指定检索的 Folders">
          <div v-if="s.gdriveFoldersList.length" class="folder-tags">
            <el-tag
              v-for="folder in s.gdriveFoldersList"
              :key="folder"
              :closable="s.editLock.gdrive"
              :disable-transitions="false"
              @close="s.removeFolder(folder)"
            >
              {{ folder }}
            </el-tag>
          </div>
          <el-input
            v-if="s.editLock.gdrive"
            v-model="s.gdriveInput"
            placeholder="粘贴 GDrive 文件夹链接，回车添加"
            @keyup.enter="s.addGDriveFolder"
          />
        </el-form-item>
      </el-form>
      <div v-if="s.gdriveFiles.length" class="db-list">
        <p class="list-title">文件夹内容核对（{{ s.gdriveFiles.length }} 项）</p>
        <ul class="file-list">
          <li v-for="file in s.gdriveFiles" :key="file.id">{{ file.name }}</li>
        </ul>
      </div>
      <div v-if="s.editLock.gdrive" class="card-footer">
        <el-button @click="s.cancelEdit('gdrive')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('gdrive')">保存 GDrive</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { inject } from 'vue';

const s = inject('adminStore');
</script>

<style scoped>
.view-wrap {
  max-width: 960px;
  margin: 0 auto;
}
.mb-4 {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.card-actions {
  display: flex;
  gap: 8px;
}
.card-editing {
  outline: 2px solid var(--el-color-primary-light-5);
}
.card-footer {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.db-list {
  margin-top: 12px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 6px;
}
.list-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px;
}
.file-list {
  max-height: 200px;
  overflow-y: auto;
  font-size: 13px;
  margin: 0;
  padding-left: 20px;
}
.folder-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
