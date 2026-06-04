<template>
  <div>
    <div class="section-toolbar">
      <el-button type="primary" size="small" :disabled="!s.editLock.jiraPm" @click="openAdd">
        添加含义说明
      </el-button>
      <el-button size="small" :disabled="!s.jiraCanUseFields" :loading="s.jiraFieldsLoading" @click="s.fetchJiraFieldOptions">
        刷新字段列表
      </el-button>
    </div>

    <el-table
      v-if="s.glossaryTableRows.length"
      :data="s.glossaryTableRows"
      stripe
      class="mb-3"
      size="small"
    >
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
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            :disabled="!s.editLock.jiraPm"
            @click="openEdit(row)"
          >
            编辑
          </el-button>
          <el-button
            link
            type="danger"
            size="small"
            :disabled="!s.editLock.jiraPm"
            @click="onRemove(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无词典条目，点击「添加含义说明」" :image-size="64" />

    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="560px"
      destroy-on-close
      @closed="onDialogClosed"
    >
      <el-form v-if="editRow" label-position="top">
        <el-form-item label="Jira 字段" required>
          <el-select
            v-model="editRow.fieldName"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入字段名"
            style="width: 100%"
            @change="s.onGlossaryFieldPick(editRow)"
          >
            <el-option
              v-for="f in s.filteredJiraFieldOptions"
              :key="f.id"
              :label="f.name"
              :value="f.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="含义说明">
          <el-input v-model="editRow.meaning" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="口语别名（回车添加）">
          <div class="alias-wrap">
            <el-tag
              v-for="(a, i) in editRow.aliases"
              :key="i"
              closable
              size="small"
              @close="s.removeAliasTag(editRow, i)"
            >
              {{ a }}
            </el-tag>
            <el-input
              v-model="editRow.aliasDraft"
              size="small"
              class="alias-input"
              placeholder="输入后回车"
              @keyup.enter="s.commitAliasDraft(editRow)"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="onCancel">取消</el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="onSave"
        >
          保存本条
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { inject, ref, computed } from 'vue';

const s = inject('adminStore');
const dialogVisible = ref(false);
const editIdx = ref(-1);
const saving = ref(false);

const editRow = computed(() =>
  editIdx.value >= 0 ? s.jiraPmForm.glossaryRows[editIdx.value] : null
);

const dialogTitle = computed(() =>
  editIdx.value >= 0 && !(editRow.value?.fieldName || '').trim()
    ? '添加字段含义'
    : '编辑字段含义'
);

function rowIndex(row) {
  return s.jiraPmForm.glossaryRows.indexOf(row);
}

function openAdd() {
  const idx = s.addGlossaryRow();
  editIdx.value = idx;
  dialogVisible.value = true;
}

function openEdit(row) {
  const idx = rowIndex(row);
  if (idx < 0) return;
  s.startEditGlossaryRow(idx);
  editIdx.value = idx;
  dialogVisible.value = true;
}

function onRemove(row) {
  const idx = rowIndex(row);
  if (idx >= 0) s.removeGlossaryRow(idx);
}

function onCancel() {
  if (editIdx.value >= 0) s.cancelEditGlossaryRow(editIdx.value);
  dialogVisible.value = false;
}

async function onSave() {
  if (editIdx.value < 0) return;
  saving.value = true;
  try {
    await s.saveGlossaryRow(editIdx.value);
    dialogVisible.value = false;
  } finally {
    saving.value = false;
  }
}

function onDialogClosed() {
  if (editIdx.value >= 0 && s.jiraPmForm.glossaryRows[editIdx.value]?.editing) {
    s.cancelEditGlossaryRow(editIdx.value);
  }
  editIdx.value = -1;
}
</script>

<style scoped>
.section-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.alias-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}
.alias-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  width: 100%;
}
.alias-input {
  width: 140px;
}
.text-muted {
  color: #94a3b8;
  font-size: 12px;
}
.mb-3 {
  margin-bottom: 12px;
}
</style>
