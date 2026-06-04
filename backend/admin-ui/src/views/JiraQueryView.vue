<template>
  <div class="page-wrap">
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

    <ConfigCard title="Alice-Jira 查询配置" :editing="s.editLock.jiraPm">
      <template #icon><el-icon><Search /></el-icon></template>
      <template #actions>
        <div class="card-actions-inner">
          <div v-if="s.editLock.jiraPm" class="test-action-group">
            <el-button
              size="small"
              :loading="s.jiraFieldsLoading"
              :disabled="!s.jiraCanUseFields"
              @click="s.fetchJiraFieldOptions"
            >
              刷新 Jira 字段列表
            </el-button>
            <TestActionHint action-key="jiraFields" />
          </div>
          <el-button v-if="!s.editLock.jiraPm" class="card-btn" type="primary" @click="s.startEdit('jiraPm')">
            编辑配置
          </el-button>
        </div>
      </template>

      <template v-if="!s.editLock.jiraPm">
        <el-alert type="success" :closable="false" show-icon class="mb-4" title="当前规则已生效，协调员查询将使用以下配置" />
        <div class="summary-box mb-4">
          <p v-for="(line, i) in s.jiraPmSummaryLines" :key="i">{{ line }}</p>
        </div>

        <h4 class="section-title">A. 参与查询的项目</h4>
        <div class="mb-4">
          <el-tag v-for="k in s.jiraPmForm.selectedProjectKeys" :key="k" class="mr-1">{{ k }}</el-tag>
          <span v-if="!s.jiraPmForm.selectedProjectKeys.length" class="text-muted">（未选择）</span>
        </div>

        <h4 class="section-title">B. 各项目截止时间字段</h4>
        <el-table :data="s.jiraPmForm.deadlineRows" size="small" class="mb-4">
          <el-table-column prop="projectKey" label="项目" width="100" />
          <el-table-column prop="fieldName" label="截止字段">
            <template #default="{ row }">
              {{ row.fieldName || '（Alice 自动识别）' }}
            </template>
          </el-table-column>
        </el-table>

        <h4 class="section-title">C. 按人名查任务</h4>
        <p class="section-hint mb-4">
          始终查询「经办人」
          <template v-if="s.jiraPmForm.extraPersonField">
            ，额外字段：<strong>{{ s.jiraPmForm.extraPersonField }}</strong>
          </template>
          <template v-else>（无额外人物字段）</template>
        </p>

        <h4 class="section-title">D. 字段含义词典</h4>
        <GlossaryTable />
      </template>

      <template v-else>
        <h4 class="section-title">A. 参与查询的 Jira 项目</h4>
        <p class="section-hint">勾选后自动同步到下方截止时间配置。</p>
        <div class="section-toolbar">
          <el-input v-model="s.jiraProjectFilter" placeholder="筛选项目" size="small" style="width: 200px" clearable />
          <div class="test-action-group">
            <el-button size="small" :loading="s.jiraProjectsLoading" :disabled="!s.jiraCanUseFields" @click="s.fetchJiraProjects">
              从 Jira 加载项目列表
            </el-button>
            <TestActionHint action-key="jiraProjects" />
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
        <el-table v-if="s.jiraProjectOptions.length" :data="s.filteredJiraProjectOptions" max-height="220" size="small" class="mb-4">
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

        <h4 class="section-title">B. 各项目截止时间字段</h4>
        <p class="section-hint">每个项目单独映射截止字段，与项目代号不是同一行绑定关系。</p>
        <el-table :data="s.jiraPmForm.deadlineRows" size="small" class="mb-4">
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
        <el-button size="small" class="mb-4" @click="s.addDeadlineRow">+ 添加项目</el-button>

        <h4 class="section-title">C. 额外人物字段（除经办人外）</h4>
        <el-select
          v-model="s.jiraPmForm.extraPersonField"
          filterable
          clearable
          placeholder="不选则仅经办人"
          style="width: 100%; max-width: 480px"
          class="mb-4"
        >
          <el-option v-for="f in s.extraPersonFieldOptions" :key="f.id" :label="f.name" :value="f.name" />
        </el-select>
        <p class="section-hint">按人名查任务时，Alice <strong>始终</strong>会查经办人；此处为额外再查的自定义人物字段。</p>

        <h4 class="section-title">D. 字段含义词典</h4>
        <GlossaryTable />

        <el-collapse v-model="advancedOpen" class="mt-4">
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
      </template>

      <template v-if="s.editLock.jiraPm" #footer>
        <el-button @click="s.cancelEdit('jiraPm')">取消</el-button>
        <el-button type="primary" @click="s.saveEdit('jiraPm')">保存任务查询规则</el-button>
      </template>
    </ConfigCard>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { Search } from '@element-plus/icons-vue';
import { useAdminInject } from '../composables/useAdminInject.js';
import ConfigCard from '../components/ConfigCard.vue';
import GlossaryTable from '../components/GlossaryTable.vue';
import TestActionHint from '../components/TestActionHint.vue';

const s = useAdminInject();
const advancedOpen = ref([]);
</script>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}
.mb-2 {
  margin-bottom: 8px;
}
.mr-1 {
  margin-right: 6px;
}
.mt-4 {
  margin-top: 16px;
}
.section-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
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
</style>
