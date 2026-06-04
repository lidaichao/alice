<template>
  <div class="view-wrap">
    <el-card shadow="never" class="mb-4" :class="{ 'card-editing': s.editLock.ai }">
      <template #header>
        <div class="card-header">
          <span>🧠 AI 模型配置</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="s.testing.ai"
              :disabled="s.editLock.ai"
              @click="s.testAiSystem"
            >
              测试 API
            </el-button>
            <el-button v-if="!s.editLock.ai" size="small" type="primary" link @click="s.startEdit('ai')">
              编辑配置
            </el-button>
          </div>
        </div>
      </template>
      <el-form label-width="140px" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="DeepSeek API URL">
              <el-input v-model="s.state.ai.DEEPSEEK_URL" :readonly="!s.editLock.ai" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="DeepSeek API Key">
              <el-input
                v-model="s.state.ai.DEEPSEEK_KEY"
                type="password"
                show-password
                :readonly="!s.editLock.ai"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="默认模型">
              <el-select
                v-model="s.state.ai.DEEPSEEK_MODEL"
                filterable
                :loading="s.fetchingModels || s.savingModel"
                :disabled="s.hydratingModel"
                style="width: 100%"
                @change="s.onModelChange"
              >
                <el-option v-for="m in s.modelSelectOptions" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div v-if="s.editLock.ai" class="card-footer">
        <el-button @click="s.cancelEdit('ai')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('ai')">保存 API 配置</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="mb-4" :class="{ 'card-editing': s.editLock.jira }">
      <template #header>
        <div class="card-header">
          <span>🔗 Jira 连接</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="s.testing.jira"
              :disabled="s.editLock.jira"
              @click="s.testJiraSystem"
            >
              测试连接
            </el-button>
            <el-button
              size="small"
              :loading="s.jiraFieldsLoading"
              :disabled="!s.jiraCanUseFields || s.editLock.jira"
              @click="s.fetchJiraFieldOptions"
            >
              刷新 Jira 字段列表
            </el-button>
            <el-button v-if="!s.editLock.jira" size="small" type="primary" link @click="s.startEdit('jira')">
              编辑连接
            </el-button>
          </div>
        </div>
      </template>
      <el-form label-width="140px" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Jira Base URL">
              <el-input v-model="s.state.jira.JIRA_BASE_URL" :readonly="!s.editLock.jira" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="`Personal Access Token（${s.jiraPatDisplayLabel}）`">
              <el-input
                v-model="s.state.jira.JIRA_PAT"
                type="password"
                show-password
                :readonly="!s.editLock.jira"
                placeholder="留空表示不修改已保存的 PAT"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="FishEye URL（可选）">
              <el-input v-model="s.state.jira.FISHEYE_URL" :readonly="!s.editLock.jira" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div v-if="s.editLock.jira" class="card-footer">
        <el-button @click="s.cancelEdit('jira')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jira')">保存 Jira 连接</el-button>
      </div>
    </el-card>

    <el-card shadow="never" :class="{ 'card-editing': s.editLock.svn }">
      <template #header>
        <div class="card-header">
          <span>📦 SVN 配置</span>
          <div class="card-actions">
            <el-button
              size="small"
              :loading="s.testing.svn"
              :disabled="s.editLock.svn"
              @click="s.testSvnSystem"
            >
              测试 Checkout
            </el-button>
            <el-button v-if="!s.editLock.svn" size="small" type="primary" link @click="s.startEdit('svn')">
              编辑配置
            </el-button>
          </div>
        </div>
      </template>
      <el-form label-position="top">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="SVN URL">
              <el-input v-model="s.state.svn.SVN_URL" :readonly="!s.editLock.svn" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="用户名">
              <el-input v-model="s.state.svn.SVN_USERNAME" :readonly="!s.editLock.svn" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="密码">
              <el-input
                v-model="s.state.svn.SVN_PASSWORD"
                type="password"
                show-password
                :readonly="!s.editLock.svn"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div v-if="s.editLock.svn" class="card-footer">
        <el-button @click="s.cancelEdit('svn')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('svn')">保存 SVN</el-button>
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
  flex-wrap: wrap;
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
</style>
