<template>
  <span class="status-pill" :class="`status-pill--${variant}`">
    <span class="status-pill__dot" :class="{ 'is-pulse': pulse }" />
    <span class="status-pill__text">{{ label }}</span>
  </span>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'muted' },
  label: { type: String, default: '未测试' },
  pulse: { type: Boolean, default: false },
});
</script>

<style scoped>
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}
.status-pill--success {
  background: var(--admin-success-soft);
  color: #15803d;
}
.status-pill--warning {
  background: #fffbeb;
  color: #b45309;
}
.status-pill--danger {
  background: #fef2f2;
  color: #b91c1c;
}
.status-pill--muted {
  background: #f1f5f9;
  color: #64748b;
}
.status-pill__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-pill--success .status-pill__dot {
  background: var(--admin-success);
}
.status-pill--warning .status-pill__dot {
  background: var(--admin-warning);
}
.status-pill--danger .status-pill__dot {
  background: var(--admin-danger);
}
.status-pill--muted .status-pill__dot {
  background: #94a3b8;
}
</style>
