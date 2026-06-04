<template>
  <div class="page-wrap">
    <ConfigCard title="Notion 知识库" :editing="s.editLock.notion">
      <template #icon><el-icon><Notebook /></el-icon></template>
      <template #status>
        <StatusPill
          :variant="s.notionConnectionOk ? 'success' : 'muted'"
          :label="s.notionConnectionOk ? '已联通' : '未测试'"
          :pulse="s.statusPulse.notion"
        />
      </template>
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <TestActionHint action-key="notion" />
            <el-button class="card-btn" :loading="s.testing.notion" :disabled="s.editLock.notion" @click="s.testNotionSystem">
              测试并拉取数据库
            </el-button>
          </div>
          <el-button v-if="!s.editLock.notion" class="card-btn" type="primary" @click="s.startEdit('notion')">
            编辑配置
          </el-button>
        </div>
      </template>

      <FieldDisplay
        v-if="!s.editLock.notion"
        :fields="[
          { label: 'Notion API Key', value: s.state.kb.NOTION_KEY, secret: true },
          { label: 'Notion 数据库 ID', value: s.state.kb.NOTION_DATABASE_ID },
        ]"
      />
      <el-row v-else :gutter="16">
        <el-col :span="12">
          <el-form-item label="Notion API Key">
            <el-input v-model="s.state.kb.NOTION_KEY" type="password" show-password />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="Notion 数据库 ID">
            <el-input
              v-model="s.state.kb.NOTION_DATABASE_ID"
              placeholder="粘贴链接自动剥离 ID"
              @blur="s.parseNotionUrl"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-table v-if="s.notionDatabases.length" :data="s.notionDatabases" size="small" class="result-table">
        <el-table-column prop="title" label="数据库名称" min-width="200" />
        <el-table-column label="ID" width="140">
          <template #default="{ row }">{{ (row.id || '').slice(0, 8) }}…</template>
        </el-table-column>
        <el-table-column v-if="s.editLock.notion" label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="pickNotionDb(row)">选用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="点击上方「测试并拉取数据库」获取列表" :image-size="64" />

      <template v-if="s.editLock.notion" #footer>
        <el-button @click="s.cancelEdit('notion')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('notion')">保存 Notion</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="Google 云盘知识库" :editing="s.editLock.gdrive">
      <template #icon><el-icon><Folder /></el-icon></template>
      <template #status>
        <StatusPill
          :variant="s.gdriveConnectionOk ? 'success' : 'muted'"
          :label="s.gdriveConnectionOk ? '已联通' : '未测试'"
          :pulse="s.statusPulse.gdrive"
        />
      </template>
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <TestActionHint action-key="gdrive" />
            <el-button class="card-btn" :loading="s.testing.gdrive" :disabled="s.editLock.gdrive" @click="s.testGDriveSystem">
              测试并列出文件夹内容
            </el-button>
          </div>
          <el-button v-if="!s.editLock.gdrive" class="card-btn" type="primary" @click="s.startEdit('gdrive')">
            编辑配置
          </el-button>
        </div>
      </template>

      <FieldDisplay
        v-if="!s.editLock.gdrive"
        :fields="[
          { label: 'Google API Key (Service Account)', value: s.state.kb.GDRIVE_KEY, secret: true },
          { label: '局域网代理 IP', value: s.state.kb.GDRIVE_PROXY_IP },
          { label: '代理端口', value: s.state.kb.GDRIVE_PROXY_PORT },
          { label: '指定检索的 Folders', value: s.gdriveFoldersList.join('、') || '尚未配置' },
        ]"
      />
      <template v-else>
        <el-form-item label="Google API Key (Service Account)">
          <el-input v-model="s.state.kb.GDRIVE_KEY" type="password" show-password />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="局域网代理 IP">
              <el-input v-model="s.state.kb.GDRIVE_PROXY_IP" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="代理端口">
              <el-input v-model="s.state.kb.GDRIVE_PROXY_PORT" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="指定检索的 Folders">
          <div v-if="s.gdriveFoldersList.length" class="folder-tags mb-2">
            <el-tag v-for="folder in s.gdriveFoldersList" :key="folder" closable @close="s.removeFolder(folder)">
              {{ folder }}
            </el-tag>
          </div>
          <el-input
            v-model="s.gdriveInput"
            placeholder="粘贴 GDrive 文件夹链接，回车添加"
            @keyup.enter="s.addGDriveFolder"
          />
        </el-form-item>
      </template>

      <el-table v-if="s.gdriveFiles.length" :data="s.gdriveFiles" size="small" max-height="240" class="result-table">
        <el-table-column label="类型" width="56">
          <template #default="{ row }">
            <span v-if="(row.type || '').includes('folder')">📁</span>
            <span v-else-if="(row.type || '').includes('spreadsheet')">📊</span>
            <span v-else>📄</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" show-overflow-tooltip />
      </el-table>

      <template v-if="s.editLock.gdrive" #footer>
        <el-button @click="s.cancelEdit('gdrive')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('gdrive')">保存 GDrive</el-button>
      </template>
    </ConfigCard>
  </div>
</template>

<script setup>
import { Notebook, Folder } from '@element-plus/icons-vue';
import { useAdminInject } from '../composables/useAdminInject.js';
import ConfigCard from '../components/ConfigCard.vue';
import StatusPill from '../components/StatusPill.vue';
import FieldDisplay from '../components/FieldDisplay.vue';
import TestActionHint from '../components/TestActionHint.vue';

const s = useAdminInject();

function pickNotionDb(row) {
  s.state.kb.NOTION_DATABASE_ID = (row.id || '').replace(/-/g, '');
  s.setActionHint('notion', '已选用数据库 ID，请记得保存配置');
}
</script>

<style scoped>
.result-table {
  margin-top: 12px;
}
.folder-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mb-2 {
  margin-bottom: 8px;
}
</style>
