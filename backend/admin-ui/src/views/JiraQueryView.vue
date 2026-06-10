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

    <ConfigCard title="参与查询的项目" :editing="s.editLock.jiraPmA">
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

    <ConfigCard title="各项目截止时间字段" :editing="s.editLock.jiraPmB">
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

    <ConfigCard title="按人名查任务" :editing="s.editLock.jiraPmC">
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

    <ConfigCard title="字段含义词典">
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

    <ConfigCard title="问题类型配置">
      <p class="section-hint">按项目配置可创建的问题类型，用于 agent 模糊匹配。支持从 Jira 自动加载或手动填写。</p>
      <div class="section-toolbar mt-2">
        <el-select v-model="s.issuetypeActiveProject" placeholder="选择项目" size="small" style="width: 160px" clearable @change="s.onIssuetypeProjectChange(s.issuetypeActiveProject)">
          <el-option v-for="k in s.jiraPmForm.selectedProjectKeys" :key="k" :label="k" :value="k" />
        </el-select>
        <div class="test-action-group">
          <TestActionHint action-key="issuetypes" />
          <el-button size="small" :loading="s.issuetypesLoading" :disabled="!s.issuetypeActiveProject || !s.jiraCanUseFields" @click="s.fetchIssuetypes">
            从 Jira 加载
          </el-button>
          <el-button size="small" type="primary" :disabled="!s.issuetypeActiveProject" @click="s.saveIssuetypes()">
            保存
          </el-button>
          <span v-if="s.issuetypeSaveMessage" class="issuetype-save-msg" :class="{ 'issuetype-save-msg--ok': s.issuetypeSaveMessage.includes('成功') }">
            {{ s.issuetypeSaveMessage }}
          </span>
        </div>
      </div>

      <div v-if="s.issuetypeActiveProject" class="issuetype-editor mt-3">
        <div class="issuetype-project-name">
          <span class="issuetype-project-label">{{ s.issuetypeActiveProject }}</span>
        </div>

        <el-table
          :data="s.issuetypeItems[s.issuetypeActiveProject] || []"
          size="small"
          class="issuetype-table"
          row-class-name="issuetype-table-row"
        >
          <el-table-column label="图标" width="56" align="center">
            <template #default="{ row }">
              <el-avatar v-if="row.iconUrl" :src="row.iconUrl" :size="24" shape="square" />
              <span v-else class="issuetype-icon-plain">—</span>
            </template>
          </el-table-column>

          <el-table-column label="名称" min-width="140">
            <template #default="{ row, $index }">
              <template v-if="!row.editing">
                <span class="issuetype-cell-name">{{ row.name }}</span>
              </template>
              <el-input
                v-else
                v-model="row.draftName"
                size="small"
                placeholder="输入名称"
                @keyup.enter="s.saveIssuetypeItem(s.issuetypeActiveProject, $index)"
              />
            </template>
          </el-table-column>

          <el-table-column label="类型" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.type === '子任务' ? 'warning' : ''" effect="plain">
                {{ row.type || '标准' }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="描述" min-width="180">
            <template #default="{ row }">
              <span class="issuetype-cell-desc">{{ row.description || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="150" align="center" fixed="right">
            <template #default="{ row, $index }">
              <template v-if="!row.editing">
                <el-button link type="primary" size="small" @click="s.startEditIssuetypeItem(s.issuetypeActiveProject, $index)">编辑</el-button>
                <el-button link type="danger" size="small" @click="s.removeIssuetypeItem(s.issuetypeActiveProject, $index)">删除</el-button>
              </template>
              <template v-else>
                <el-button link type="success" size="small" @click="s.saveIssuetypeItem(s.issuetypeActiveProject, $index)">保存</el-button>
                <el-button link type="info" size="small" @click="s.cancelEditIssuetypeItem(s.issuetypeActiveProject, $index)">取消</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>

        <div class="issuetype-add-row mt-2">
          <el-button size="small" @click="s.addIssuetypeItem(s.issuetypeActiveProject)">+ 添加</el-button>
        </div>

        <p v-if="!(s.issuetypeItems[s.issuetypeActiveProject] || []).length" class="text-muted mt-3">
          暂无条目，点击「从 Jira 加载」或下方「+ 添加」开始配置
        </p>
      </div>
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
.issuetype-group {
  margin-bottom: 12px;
}
.issuetype-project-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--admin-text-primary);
  margin-bottom: 6px;
}
.issuetype-project-name.with-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.issuetype-project-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--admin-text-primary);
}
.issuetype-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.issuetype-editor {
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  padding: 16px;
  background: #f8fafc;
}
.issuetype-table {
  margin-top: 4px;
}
.issuetype-table :deep(.el-table__header th) {
  background: #f1f5f9;
  font-weight: 600;
  font-size: 12px;
  color: #475569;
  border-bottom: 1px solid #e2e8f0;
}
.issuetype-table :deep(.el-table__body td) {
  border-bottom: 1px solid #f1f5f9;
  padding: 8px 0;
}
.issuetype-table-row:hover > td {
  background: #f8fafc !important;
}
.issuetype-cell-name {
  font-weight: 500;
  font-size: 13px;
  color: var(--admin-text-primary);
}
.issuetype-cell-desc {
  font-size: 12px;
  color: #64748b;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.issuetype-icon-plain {
  font-size: 12px;
  color: #94a3b8;
}
.issuetype-textarea {
  margin-top: 8px;
}
.issuetype-add-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
}
.issuetype-save-msg {
  font-size: 12px;
  color: var(--el-color-danger, #f56c6c);
  margin-left: 4px;
  white-space: nowrap;
}
.issuetype-save-msg--ok {
  color: var(--el-color-success, #67c23a);
}
</style>
