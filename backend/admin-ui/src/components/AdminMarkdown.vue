<template>
  <div class="admin-markdown" v-html="html" />
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  source: { type: String, default: '' },
});

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineFormat(text) {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return s;
}

const html = computed(() => {
  const src = props.source || '';
  const lines = src.split('\n');
  const out = [];
  let inUl = false;

  const closeUl = () => {
    if (inUl) {
      out.push('</ul>');
      inUl = false;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      closeUl();
      continue;
    }
    if (line.startsWith('## ')) {
      closeUl();
      out.push(`<h2>${inlineFormat(line.slice(3))}</h2>`);
      continue;
    }
    if (line.startsWith('### ')) {
      closeUl();
      out.push(`<h3>${inlineFormat(line.slice(4))}</h3>`);
      continue;
    }
    if (line.startsWith('- ')) {
      if (!inUl) {
        out.push('<ul>');
        inUl = true;
      }
      out.push(`<li>${inlineFormat(line.slice(2))}</li>`);
      continue;
    }
    closeUl();
    out.push(`<p>${inlineFormat(line)}</p>`);
  }
  closeUl();
  return out.join('');
});
</script>

<style scoped>
.admin-markdown :deep(h2) {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  color: #1e3a5f;
}
.admin-markdown :deep(h3) {
  margin: 14px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}
.admin-markdown :deep(h3:first-child) {
  margin-top: 0;
}
.admin-markdown :deep(p) {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.65;
  color: #1e293b;
}
.admin-markdown :deep(ul) {
  margin: 0 0 10px;
  padding-left: 20px;
}
.admin-markdown :deep(li) {
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.6;
  color: #334155;
}
.admin-markdown :deep(code) {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  color: #1d4ed8;
}
.admin-markdown :deep(strong) {
  font-weight: 600;
  color: #0f172a;
}
</style>
