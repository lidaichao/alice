<template>
  <div class="view-wrap">
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
      title="尚未检测到可用的 Jira 连接。请先在系统集成页填写地址与 PAT 并测试连接，或保存已有 PAT 后再加载项目/字段。"
    />

    <el-card shadow="never" :class="{ 'card-editing': s.editLock.jiraPm }">
      <template #header>
        <div class="card-header">
          <span>Alice-Jira 查询配置</span>
          <el-button v-if="!s.editLock.jiraPm" size="small" type="primary" link @click="s.startEdit('jiraPm')">
            编辑配置
          </el-button>
        </div>
      </template>

      <template v-if="!s.editLock.jiraPm">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item
            v-for="(line, i) in s.jiraPmSummaryLines"
            :key="i"
            :label="i === 0 ? '摘要' : ''"
          >
            {{ line }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="mt-4">
          <h4 class="section-title">字段含义词典</h4>
          <GlossaryTable />
        </div>
      </template>

      <template v-else>
        <h4 class="section-title">A. 参与查询的 Jira 项目</h4>
        <div class="section-toolbar">
          <el-input
            v-model="s.jiraProjectFilter"
            placeholder="筛选项目"
            size="small"
            style="width: 200px"
            clearable
          />
          <el-button
            size="small"
            :loading="s.jiraProjectsLoading"
            @click="s.fetchJiraProjects"
          >
            从 Jira 加载项目列表
          </el-button>
        </div>
        <el-table
          :data="s.filteredJiraProjectOptions"
          max-height="220"
          size="small"
          class="mb-4"
        >
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
        <p class="hint">已选：{{ s.projectKeysText || '（无）' }}</p>

        <h4 class="section-title">B. 各项目截止时间字段</h4>
        <el-table :data="s.jiraPmForm.deadlineRows" size="small" class="mb-4">
          <el-table-column prop="projectKey" label="项目" width="100" />
          <el-table-column label="截止字段">
            <template #default="{ row }">
              <el-select
                v-model="row.fieldName"
                filterable
                allow-create
                placeholder="选择字段"
                style="width: 100%"
              >
                <el-option
                  v-for="f in s.filteredJiraFieldOptions"
                  :key="f.id"
                  :label="f.name"
                  :value="f.name"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="s.suggestDeadline(row)">
                自动推荐
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <h4 class="section-title">C. 额外人物字段（除经办人外）</h4>
        <el-form label-position="top" class="mb-4">
          <el-form-item label="可选：负责人 / 报告人等（经办人始终参与查询）">
            <el-select
              v-model="s.jiraPmForm.extraPersonField"
              filterable
              clearable
              placeholder="不选则仅经办人"
              style="width: 100%; max-width: 400px"
            >
              <el-option
                v-for="f in s.extraPersonFieldOptions"
                :key="f.id"
                :label="f.name"
                :value="f.name"
              />
            </el-select>
          </el-form-item>
        </el-form>

        <h4 class="section-title">D. 字段含义词典</h4>
        <GlossaryTable />

        <el-collapse v-model="advancedOpen" class="mt-4">
          <el-collapse-item title="高级：JSON 直编（技术人员）" name="json">
            <el-form label-position="top">
              <el-form-item label="JIRA_DEADLINE_FIELD_BY_PROJECT">
                <el-input
                  v-model="s.state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT"
                  type="textarea"
                  :rows="4"
                  @blur="s.syncPmFormFromJson"
                />
              </el-form-item>
              <el-form-item label="JIRA_FIELD_MAPPINGS">
                <el-input
                  v-model="s.state.jira.JIRA_FIELD_MAPPINGS"
                  type="textarea"
                  :rows="3"
                  @blur="s.syncPmFormFromJson"
                />
              </el-form-item>
              <el-form-item label="JIRA_PROJECT_CONFIG">
                <el-input
                  v-model="s.state.jira.JIRA_PROJECT_CONFIG"
                  type="textarea"
                  :rows="4"
                  @blur="s.syncPmFormFromJson"
                />
              </el-form-item>
              <el-form-item label="JIRA_FIELD_GLOSSARY">
                <el-input
                  v-model="s.state.jira.JIRA_FIELD_GLOSSARY"
                  type="textarea"
                  :rows="5"
                  @blur="s.syncGlossaryFromJson"
                />
              </el-form-item>
            </el-form>
          </el-collapse-item>
        </el-collapse>

        <div class="card-footer">
          <el-button @click="s.cancelEdit('jiraPm')">取消</el-button>
          <el-button type="primary" @click="s.saveEdit('jiraPm')">保存任务查询规则</el-button>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { inject, ref } from 'vue';
import GlossaryTable from '../components/GlossaryTable.vue';

const s = inject('adminStore');
const advancedOpen = ref([]);
</script>

<style scoped>
.view-wrap {
  max-width: 960px;
  margin: 0 auto;
}
.mb-4 {
  margin-bottom: 16px;
}
.mt-4 {
  margin-top: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
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
.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}
.section-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.hint {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 12px;
}
</style>
