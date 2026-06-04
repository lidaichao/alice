<template>
  <div>
    <div class="section-toolbar">
      <el-button type="primary" size="small" :disabled="!s.editLock.jiraPm" @click="addRow">
        添加含义说明
      </el-button>
      <el-button size="small" :disabled="!s.jiraCanUseFields" :loading="s.jiraFieldsLoading" @click="s.fetchJiraFieldOptions">
        刷新字段列表
      </el-button>
      <el-input
        v-if="s.editLock.jiraPm"
        v-model="s.jiraFieldFilter"
        size="small"
        placeholder="筛选字段名称"
        clearable
        style="width: 200px"
      />
    </div>

    <el-table
      v-if="displayRows.length"
      :data="displayRows"
      stripe
      row-key="rowKey"
      :expand-row-keys="expandedKeys"
      @expand-change="onExpandChange"
    >
      <el-table-column v-if="s.editLock.jiraPm" type="expand">
        <template #default="{ row }">
          <div v-if="row._gidx >= 0" class="expand-form">
            <el-form label-position="top">
              <el-form-item label="Jira 字段" required>
                <el-select
                  v-model="s.jiraPmForm.glossaryRows[row._gidx].fieldName"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="选择或输入字段名"
                  style="width: 100%"
                  @change="s.onGlossaryFieldPick(s.jiraPmForm.glossaryRows[row._gidx])"
                >
                  <el-option
                    v-for="f in s.filteredJiraFieldOptions"
                    :key="f.id"
                    :label="f.name"
                    :value="f.name"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="Alice 应如何理解这个字段">
                <el-input
                  v-model="s.jiraPmForm.glossaryRows[row._gidx].meaning"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：策划排期的业务完成日"
                />
              </el-form-item>
              <el-form-item label="口语别名（回车添加）">
                <div class="alias-wrap">
                  <el-tag
                    v-for="(a, i) in s.jiraPmForm.glossaryRows[row._gidx].aliases"
                    :key="i"
                    closable
                    size="small"
                    @close="s.removeAliasTag(s.jiraPmForm.glossaryRows[row._gidx], i)"
                  >
                    {{ a }}
                  </el-tag>
                  <el-input
                    v-model="s.jiraPmForm.glossaryRows[row._gidx].aliasDraft"
                    size="small"
                    class="alias-input"
                    placeholder="输入后回车"
                    @keyup.enter="s.commitAliasDraft(s.jiraPmForm.glossaryRows[row._gidx])"
                  />
                </div>
              </el-form-item>
              <div class="expand-actions">
                <el-button size="small" @click="cancelRow(row._gidx)">取消</el-button>
                <el-button
                  type="primary"
                  size="small"
                  :loading="s.savingGlossaryIdx === row._gidx"
                  @click="saveRow(row._gidx)"
                >
                  保存本条
                </el-button>
              </div>
            </el-form>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="fieldName" label="Jira 字段" min-width="140" />
      <el-table-column prop="meaning" label="含义说明" min-width="200" show-overflow-tooltip />
      <el-table-column label="口语别名" min-width="160">
        <template #default="{ row }">
          <el-tag
            v-for="(a, i) in s.normalizeAliasTags(row.aliases)"
            :key="i"
            size="small"
            class="alias-tag"
          >
            {{ a }}
          </el-tag>
          <span v-if="!s.normalizeAliasTags(row.aliases).length" class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column v-if="s.editLock.jiraPm" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editRow(row._gidx)">编辑</el-button>
          <el-button link type="danger" size="small" @click="s.removeGlossaryRow(row._gidx)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无词典条目" :image-size="64" />

    <el-button
      v-if="s.editLock.jiraPm && displayRows.length"
      class="add-more"
      size="small"
      @click="addRow"
    >
      + 继续添加
    </el-button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useAdminInject } from '../composables/useAdminInject.js';

const s = useAdminInject();
const expandedKeys = ref([]);

const displayRows = computed(() =>
  (s.jiraPmForm.glossaryRows || [])
    .map((r, gidx) => ({
      ...r,
      _gidx: gidx,
      rowKey: `gl-${gidx}-${r.fieldId || r.fieldName || 'new'}`,
    }))
    .filter((r) => (r.fieldName || '').trim() || r.editing)
);

function editRow(gidx) {
  s.startEditGlossaryRow(gidx);
  const key = displayRows.value.find((r) => r._gidx === gidx)?.rowKey;
  if (key && !expandedKeys.value.includes(key)) {
    expandedKeys.value = [...expandedKeys.value, key];
  }
}

function addRow() {
  const gidx = s.addGlossaryRow();
  const row = s.jiraPmForm.glossaryRows[gidx];
  const key = `gl-${gidx}-new`;
  row.rowKey = key;
  expandedKeys.value = [key];
}

async function saveRow(gidx) {
  await s.saveGlossaryRow(gidx);
  expandedKeys.value = expandedKeys.value.filter((k) => k !== `gl-${gidx}-new` && !k.startsWith(`gl-${gidx}-`));
  const row = s.jiraPmForm.glossaryRows[gidx];
  if (row?.fieldName) {
    expandedKeys.value = expandedKeys.value.filter((k) => k !== `gl-${gidx}-${row.fieldId || row.fieldName}`);
  }
}

function cancelRow(gidx) {
  s.cancelEditGlossaryRow(gidx);
  expandedKeys.value = [];
}

function onExpandChange(row, expanded) {
  if (!expanded && row._gidx >= 0 && s.jiraPmForm.glossaryRows[row._gidx]?.editing) {
    s.cancelEditGlossaryRow(row._gidx);
  }
}
</script>

<style scoped>
.section-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.expand-form {
  padding: 12px 16px 8px;
  background: var(--admin-bg-readonly);
  border-radius: var(--admin-radius-control);
}
.expand-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.alias-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  width: 100%;
}
.alias-input {
  width: 160px;
}
.alias-tag {
  margin-right: 4px;
}
.text-muted {
  color: #94a3b8;
  font-size: 12px;
}
.add-more {
  margin-top: 8px;
}
</style>
