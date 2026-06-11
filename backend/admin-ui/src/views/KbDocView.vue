<template>
  <div class="page-wrap">
    <div class="page-header">
      <h2 class="page-title">知识库文档</h2>
      <p class="page-desc">管理 Dify 知识库中的文档，查看索引状态并重建索引</p>
    </div>

    <div class="toolbar">
      <el-button class="tb-btn" :loading="loading" @click="fetchDocs">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <span class="tb-total" v-if="!loading">共 {{ docs.length }} 篇文档</span>
    </div>

    <div v-if="error" class="error-bar">
      <el-alert :title="error" type="error" show-icon :closable="false" />
    </div>

    <el-empty v-if="!loading && !error && docs.length === 0" description="暂无文档，请先通过 Dify 控制台上传" :image-size="80" />

    <el-table v-if="docs.length" :data="docs" size="small" class="doc-table" stripe>
      <el-table-column prop="name" label="文档名" min-width="240" show-overflow-tooltip />
      <el-table-column label="索引状态" width="130">
        <template #default="{ row }">
          <el-tag
            :type="statusTagType(row.indexing_status)"
            size="small"
            effect="plain"
          >
            {{ statusLabel(row.indexing_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="文件大小" width="100">
        <template #default="{ row }">
          {{ formatSize(row.file_size) }}
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="180">
        <template #default="{ row }">
          {{ row.updated_at ? new Date(row.updated_at * 1000 || row.updated_at).toLocaleString('zh-CN') : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            :loading="reindexingId === row.document_id"
            @click="reindexDoc(row.document_id)"
          >
            重建索引
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { Refresh } from '@element-plus/icons-vue';
import { useAdminStore } from '../composables/useAdminStore.js';

const store = useAdminStore();
const docs = ref([]);
const loading = ref(false);
const error = ref('');
const reindexingId = ref('');

const ADMIN_TOKEN = () => store.adminToken || '';

function statusTagType(status) {
  switch (status) {
    case 'completed': return 'success';
    case 'parsing': case 'indexing': return 'warning';
    case 'error': return 'danger';
    default: return 'info';
  }
}

function statusLabel(status) {
  const map = {
    completed: '已完成',
    parsing: '解析中',
    indexing: '索引中',
    error: '索引失败',
    waiting: '等待中',
  };
  return map[status] || status || '未知';
}

function formatSize(bytes) {
  if (!bytes || bytes <= 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function fetchDocs() {
  loading.value = true;
  error.value = '';
  try {
    const resp = await fetch('/v1/admin/kb/documents?limit=50', {
      headers: { 'x-admin-token': ADMIN_TOKEN() },
    });
    const data = await resp.json();
    if (data.ok) {
      docs.value = data.documents || [];
    } else {
      error.value = data.error || '获取文档列表失败';
    }
  } catch (e) {
    error.value = '网络请求失败：' + (e.message || e);
  } finally {
    loading.value = false;
  }
}

async function reindexDoc(docId) {
  reindexingId.value = docId;
  try {
    const resp = await fetch(`/v1/admin/kb/documents/${docId}/reindex`, {
      method: 'POST',
      headers: { 'x-admin-token': ADMIN_TOKEN() },
    });
    const data = await resp.json();
    if (data.ok) {
      store.showToast('已提交重新索引');
    } else {
      store.showToast(data.error || '重建索引失败', 'error');
    }
  } catch (e) {
    store.showToast('网络请求失败', 'error');
  } finally {
    reindexingId.value = '';
  }
}

onMounted(() => {
  fetchDocs();
});
</script>

<style scoped>
.page-wrap {
  padding: 20px 28px;
  max-width: 1100px;
}
.page-header {
  margin-bottom: 16px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--saas-text-primary, #172b4d);
  margin: 0 0 4px;
}
.page-desc {
  font-size: 13px;
  color: var(--saas-text-secondary, #5e6c84);
  margin: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.tb-total {
  font-size: 13px;
  color: var(--saas-text-secondary, #5e6c84);
}
.error-bar {
  margin-bottom: 12px;
}
.doc-table {
  margin-top: 8px;
}
</style>
