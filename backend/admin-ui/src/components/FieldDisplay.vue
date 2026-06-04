<template>
  <div class="field-display">
    <div v-for="item in fields" :key="item.label" class="field-display__row">
      <div class="field-display__label">{{ item.label }}</div>
      <div class="field-display__value">
        <template v-if="item.secret && item.value">
          <span class="field-display__secret">••••••••</span>
          <span v-if="item.hint" class="field-display__hint">{{ item.hint }}</span>
        </template>
        <template v-else>{{ item.value || '—' }}</template>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  fields: {
    type: Array,
    default: () => [],
    // { label, value, secret?, hint? }
  },
});
</script>

<style scoped>
.field-display {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.field-display__label {
  font-size: 12px;
  font-weight: 500;
  color: var(--admin-text-secondary);
  margin-bottom: 4px;
}
.field-display__value {
  font-size: 14px;
  color: #0f172a;
  line-height: 1.6;
  word-break: break-all;
}
.field-display__secret {
  letter-spacing: 2px;
  color: #475569;
}
.field-display__hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--admin-text-secondary);
}
</style>
