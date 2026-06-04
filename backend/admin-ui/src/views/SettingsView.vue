<template>
  <div class="page-wrap">
    <ConfigCard title="AI 模型配置" :editing="s.editLock.ai">
      <template #icon><el-icon><Cpu /></el-icon></template>
      <template #status>
        <StatusPill
          :variant="s.aiConnectionOk ? 'success' : 'muted'"
          :label="s.aiConnectionOk ? 'API 可达' : '未测试'"
          :pulse="s.statusPulse.ai"
        />
      </template>
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <el-button class="card-btn" :loading="s.testing.ai" :disabled="s.editLock.ai" @click="s.testAiSystem">
              测试 API
            </el-button>
            <TestActionHint action-key="ai" />
          </div>
          <el-button v-if="!s.editLock.ai" class="card-btn" type="primary" @click="s.startEdit('ai')">
            编辑配置
          </el-button>
        </div>
      </template>

      <FieldDisplay
        v-if="!s.editLock.ai"
        :fields="[
          { label: 'DeepSeek API URL', value: s.state.ai.DEEPSEEK_URL },
          { label: 'DeepSeek API Key', value: s.state.ai.DEEPSEEK_KEY, secret: true, hint: '已配置密钥' },
          { label: '默认模型', value: s.state.ai.DEEPSEEK_MODEL || s.lastSavedModel },
        ]"
      />
      <el-form v-else label-position="top">
        <el-form-item label="DeepSeek API URL">
          <el-input v-model="s.state.ai.DEEPSEEK_URL" />
        </el-form-item>
        <el-form-item label="DeepSeek API Key">
          <el-input v-model="s.state.ai.DEEPSEEK_KEY" type="password" show-password />
        </el-form-item>
        <el-form-item label="默认模型">
          <div class="model-row">
            <el-select
              v-model="s.state.ai.DEEPSEEK_MODEL"
              filterable
              class="model-select"
              :loading="s.fetchingModels || s.savingModel"
              :disabled="s.savingModel"
              @change="s.onModelChange"
            >
              <el-option v-for="m in s.modelSelectOptions" :key="m" :label="m" :value="m" />
            </el-select>
            <div class="test-action-group">
              <el-button :loading="s.fetchingModels" :disabled="s.savingModel" @click="s.fetchAiModels()">
                刷新模型列表
              </el-button>
              <TestActionHint action-key="aiModels" />
            </div>
          </div>
          <p class="field-hint">
            从 API /models 自动获取；切换即保存，Alice 全局默认使用该模型。
            <span v-if="s.savingModel" class="saving-hint">保存中…</span>
            <span v-else-if="s.lastSavedModel">当前生效：{{ s.lastSavedModel }}</span>
          </p>
        </el-form-item>
      </el-form>

      <template v-if="s.editLock.ai" #footer>
        <el-button @click="s.cancelEdit('ai')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('ai')">保存 API 配置</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="Jira 连接" :editing="s.editLock.jira">
      <template #icon><el-icon><Link /></el-icon></template>
      <template #status>
        <StatusPill
          :variant="s.jiraConnectionOk ? 'success' : s.jiraPatOnServer ? 'warning' : 'muted'"
          :label="s.jiraConnectionOk ? '已连通' : s.jiraPatOnServer ? '已保存凭据' : '未测试'"
          :pulse="s.statusPulse.jira"
        />
      </template>
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <el-button class="card-btn" :loading="s.testing.jira" @click="s.testJiraSystem">测试连接</el-button>
            <TestActionHint action-key="jira" />
          </div>
          <div class="test-action-group">
            <el-button
              class="card-btn"
              :loading="s.jiraFieldsLoading"
              :disabled="!s.jiraCanUseFields"
              @click="s.fetchJiraFieldOptions"
            >
              刷新字段列表
            </el-button>
            <TestActionHint action-key="jiraFields" />
          </div>
          <el-button v-if="!s.editLock.jira" class="card-btn" type="primary" @click="s.startEdit('jira')">
            编辑连接
          </el-button>
        </div>
      </template>

      <p class="section-hint">
        PAT 保存后无需每次重填；仅更换令牌时在编辑中粘贴新 PAT。任务查询规则在「Alice-Jira查询配置」页签。
      </p>

      <FieldDisplay
        v-if="!s.editLock.jira"
        :fields="[
          { label: 'Jira Base URL', value: s.state.jira.JIRA_BASE_URL },
          { label: 'Personal Access Token', value: s.jiraPatDisplayLabel },
          { label: 'FishEye URL（可选）', value: s.state.jira.FISHEYE_URL },
        ]"
      />
      <el-form v-else label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Jira Base URL">
              <el-input v-model="s.state.jira.JIRA_BASE_URL" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Personal Access Token">
              <el-input
                v-model="s.state.jira.JIRA_PAT"
                type="password"
                show-password
                :placeholder="s.jiraPatOnServer ? '留空表示不修改已保存的 PAT' : '粘贴 PAT'"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="FishEye URL（可选）">
              <el-input v-model="s.state.jira.FISHEYE_URL" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <template v-if="s.editLock.jira" #footer>
        <el-button @click="s.cancelEdit('jira')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jira')">保存 Jira 连接</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="SVN 配置" :editing="s.editLock.svn">
      <template #icon><el-icon><Box /></el-icon></template>
      <template #status>
        <StatusPill
          :variant="s.svnConnectionOk ? 'success' : 'muted'"
          :label="s.svnConnectionOk ? '校验通过' : '未测试'"
          :pulse="s.statusPulse.svn"
        />
      </template>
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <el-button class="card-btn" :loading="s.testing.svn" :disabled="s.editLock.svn" @click="s.testSvnSystem">
              测试 Checkout
            </el-button>
            <TestActionHint action-key="svn" />
          </div>
          <el-button v-if="!s.editLock.svn" class="card-btn" type="primary" @click="s.startEdit('svn')">
            编辑配置
          </el-button>
        </div>
      </template>

      <FieldDisplay
        v-if="!s.editLock.svn"
        :fields="[
          { label: 'SVN URL', value: s.state.svn.SVN_URL },
          { label: '用户名', value: s.state.svn.SVN_USERNAME },
          { label: '密码', value: s.state.svn.SVN_PASSWORD, secret: true },
        ]"
      />
      <el-row v-else :gutter="16">
        <el-col :span="8">
          <el-form-item label="SVN URL">
            <el-input v-model="s.state.svn.SVN_URL" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="用户名">
            <el-input v-model="s.state.svn.SVN_USERNAME" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="密码">
            <el-input v-model="s.state.svn.SVN_PASSWORD" type="password" show-password />
          </el-form-item>
        </el-col>
      </el-row>

      <template v-if="s.editLock.svn" #footer>
        <el-button @click="s.cancelEdit('svn')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('svn')">保存 SVN</el-button>
      </template>
    </ConfigCard>
  </div>
</template>

<script setup>
import { Cpu, Link, Box } from '@element-plus/icons-vue';
import { useAdminInject } from '../composables/useAdminInject.js';
import ConfigCard from '../components/ConfigCard.vue';
import StatusPill from '../components/StatusPill.vue';
import FieldDisplay from '../components/FieldDisplay.vue';
import TestActionHint from '../components/TestActionHint.vue';

const s = useAdminInject();
</script>

<style scoped>
.model-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.model-select {
  flex: 1;
}
.field-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--admin-text-secondary);
  line-height: 1.5;
}
.saving-hint {
  color: var(--admin-primary);
  margin-left: 8px;
}
</style>
