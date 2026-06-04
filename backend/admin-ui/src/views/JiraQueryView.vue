<template>
  <div class="page-wrap jira-query-page">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="mb-4"
      title="Jira 账号请在「系统集成配置」→ Jira 连接 中配置；本页仅配置 Alice 查询与周报规则。"
    />
    <el-alert
      v-if="!s.jiraCanUseFields"
      type="warning"
      :closable="false"
      show-icon
      class="mb-4"
      title="尚未检测到可用的 Jira 连接。请先在系统集成页填写地址与 PAT 并测试连接。"
    />

    <div class="jira-summary-panel mb-4">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        class="jira-summary-panel__alert"
        title="当前规则已生效，协调员查询将使用以下配置"
      />
      <div class="jira-summary-panel__body">
        <AdminMarkdown :source="s.jiraPmSummaryMarkdown" />
      </div>
    </div>

    <ConfigCard title="A. 参与查询的项目" :editing="s.editLock.jiraPmA">
      <template #actions>
        <el-button v-if="!s.editLock.jiraPmA" class="card-btn" type="primary" @click="s.startEdit('jiraPmA')">
          编辑
        </el-button>
      </template>

      <template v-if="!s.editLock.jiraPmA">
        <div class="readonly-tags">
          <el-tag v-for="k in s.jiraPmForm.selectedProjectKeys" :key="k">{{ k }}</el-tag>
          <span v-if="!s.jiraPmForm.selectedProjectKeys.length" class="text-muted">（未选择）</span>
        </div>
      </template>
      <template v-else>
        <p class="section-hint">勾选后自动同步到「B. 截止时间字段」。</p>
        <div class="section-toolbar">
          <el-input v-model="s.jiraProjectFilter" placeholder="筛选项目" size="small" style="width: 200px" clearable />
          <div class="test-action-group">
            <TestActionHint action-key="jiraProjects" />
            <el-button size="small" :loading="s.jiraProjectsLoading" :disabled="!s.jiraCanUseFields" @click="s.fetchJiraProjects">
              从 Jira 加载项目列表
            </el-button>
          </div>
        </div>
        <div v-if="s.jiraPmForm.selectedProjectKeys.length" class="selected-tags mb-2">
          <span class="text-muted">已选：</span>
          <el-tag
            v-for="k in s.jiraPmForm.selectedProjectKeys"
            :key="k"
            closable
            size="small"
            class="mr-1"
            @close="s.toggleProjectKey(k)"
          >
            {{ k }}
          </el-tag>
        </div>
        <el-table v-if="s.jiraProjectOptions.length" :data="s.filteredJiraProjectOptions" max-height="220" size="small">
          <el-table-column width="48">
            <template #default="{ row }">
              <el-checkbox
                :model-value="s.jiraPmForm.selectedProjectKeys.includes(row.key)"
                @change="s.toggleProjectKey(row.key)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="key" label="代号" width="80" />
          <el-table-column prop="name" label="名称" />
        </el-table>
      </template>

      <template v-if="s.editLock.jiraPmA" #footer>
        <el-button @click="s.cancelEdit('jiraPmA')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jiraPmA')">保存本块</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="B. 各项目截止时间字段" :editing="s.editLock.jiraPmB">
      <template #actions>
        <el-button v-if="!s.editLock.jiraPmB" class="card-btn" type="primary" @click="s.startEdit('jiraPmB')">
          编辑
        </el-button>
      </template>

      <template v-if="!s.editLock.jiraPmB">
        <el-table :data="s.jiraPmForm.deadlineRows" size="small">
          <el-table-column prop="projectKey" label="项目" width="100" />
          <el-table-column prop="fieldName" label="截止字段">
            <template #default="{ row }">
              {{ row.fieldName || '（Alice 自动识别）' }}
            </template>
          </el-table-column>
        </el-table>
        <p v-if="!s.jiraPmForm.deadlineRows.length" class="text-muted mt-2">（未配置）</p>
      </template>
      <template v-else>
        <p class="section-hint">每个项目单独映射截止字段。</p>
        <el-table :data="s.jiraPmForm.deadlineRows" size="small">
          <el-table-column label="项目" width="120">
            <template #default="{ row }">
              <el-input v-model="row.projectKey" placeholder="如 CT" class="uppercase" />
            </template>
          </el-table-column>
          <el-table-column label="截止字段">
            <template #default="{ row }">
              <el-select v-model="row.fieldName" filterable allow-create clearable placeholder="留空=自动识别" style="width: 100%">
                <el-option v-for="f in s.filteredJiraFieldOptions" :key="f.id" :label="f.name" :value="f.name" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="s.suggestDeadline(row)">自动推荐</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="mt-2" @click="s.addDeadlineRow">+ 添加项目</el-button>
      </template>

      <template v-if="s.editLock.jiraPmB" #footer>
        <el-button @click="s.cancelEdit('jiraPmB')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jiraPmB')">保存本块</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="C. 按人名查任务" :editing="s.editLock.jiraPmC">
      <template #actions>
        <el-button v-if="!s.editLock.jiraPmC" class="card-btn" type="primary" @click="s.startEdit('jiraPmC')">
          编辑
        </el-button>
      </template>

      <template v-if="!s.editLock.jiraPmC">
        <p class="readonly-line">
          始终查询「经办人」
          <template v-if="s.jiraPmForm.extraPersonField">
            ，额外字段：<strong>{{ s.jiraPmForm.extraPersonField }}</strong>
          </template>
          <template v-else>（无额外人物字段）</template>
        </p>
      </template>
      <template v-else>
        <el-select
          v-model="s.jiraPmForm.extraPersonField"
          filterable
          clearable
          placeholder="不选则仅经办人"
          style="width: 100%; max-width: 480px"
        >
          <el-option v-for="f in s.extraPersonFieldOptions" :key="f.id" :label="f.name" :value="f.name" />
        </el-select>
        <p class="section-hint mt-2">按人名查任务时，Alice <strong>始终</strong>会查经办人；此处为额外再查的自定义人物字段。</p>
      </template>

      <template v-if="s.editLock.jiraPmC" #footer>
        <el-button @click="s.cancelEdit('jiraPmC')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jiraPmC')">保存本块</el-button>
      </template>
    </ConfigCard>

    <ConfigCard title="D. 字段含义词典">
      <template #actions>
        <div class="card-actions-inner">
          <div class="test-action-group">
            <TestActionHint action-key="jiraFields" />
            <el-button
              class="card-btn"
              :loading="s.jiraFieldsLoading"
              :disabled="!s.jiraCanUseFields"
              @click="s.fetchJiraFieldOptions"
            >
              刷新 Jira 字段列表
            </el-button>
          </div>
        </div>
      </template>

      <GlossaryTable />
    </ConfigCard>

    <el-collapse v-model="advancedOpen" class="advanced-collapse">
      <el-collapse-item title="技术人员：查看原始 JSON" name="json">
        <el-form label-position="top">
          <el-form-item label="JIRA_DEADLINE_FIELD_BY_PROJECT">
            <el-input v-model="s.state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT" type="textarea" :rows="3" @blur="s.syncPmFormFromJson" />
          </el-form-item>
          <el-form-item label="JIRA_FIELD_MAPPINGS">
            <el-input v-model="s.state.jira.JIRA_FIELD_MAPPINGS" type="textarea" :rows="2" @blur="s.syncPmFormFromJson" />
          </el-form-item>
          <el-form-item label="JIRA_PROJECT_CONFIG">
            <el-input v-model="s.state.jira.JIRA_PROJECT_CONFIG" type="textarea" :rows="3" @blur="s.syncPmFormFromJson" />
          </el-form-item>
          <el-form-item label="JIRA_FIELD_GLOSSARY">
            <el-input v-model="s.state.jira.JIRA_FIELD_GLOSSARY" type="textarea" :rows="4" @blur="s.syncGlossaryFromJson" />
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useAdminInject } from '../composables/useAdminInject.js';
import ConfigCard from '../components/ConfigCard.vue';
import GlossaryTable from '../components/GlossaryTable.vue';
import TestActionHint from '../components/TestActionHint.vue';
import AdminMarkdown from '../components/AdminMarkdown.vue';

const s = useAdminInject();
const advancedOpen = ref([]);
</script>

<style scoped>
.jira-query-page :deep(.config-card) {
  margin-bottom: 16px;
}
.jira-summary-panel {
  border: 1px solid #bfdbfe;
  border-radius: var(--admin-radius-card, 12px);
  background: linear-gradient(180deg, #eff6ff 0%, #f8fafc 100%);
  overflow: hidden;
}
.jira-summary-panel__alert {
  border: none;
  border-radius: 0;
  background: #ecfdf5;
}
.jira-summary-panel__body {
  padding: 16px 20px 20px;
}
.readonly-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.readonly-line {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: #334155;
}
.mb-4 {
  margin-bottom: 16px;
}
.mb-2 {
  margin-bottom: 8px;
}
.mr-1 {
  margin-right: 6px;
}
.mt-2 {
  margin-top: 8px;
}
.section-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.selected-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.text-muted {
  font-size: 12px;
  color: var(--admin-text-secondary);
}
.uppercase :deep(input) {
  text-transform: uppercase;
}
.advanced-collapse {
  margin-top: -8px;
  margin-bottom: 16px;
}
</style>
