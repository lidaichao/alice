<template>
  <span
    v-if="entry.show && entry.msg"
    class="test-action-hint"
    :class="entry.isError ? 'test-action-hint--error' : 'test-action-hint--ok'"
  >
    {{ entry.msg }}
  </span>
</template>

<script setup>
import { computed } from 'vue';
import { useAdminInject } from '../composables/useAdminInject.js';

const props = defineProps({
  actionKey: { type: String, required: true },
});

const s = useAdminInject();
const entry = computed(() => s.testResult[props.actionKey] || { show: false, msg: '', isError: false });
</script>

<style scoped>
.test-action-hint {
  display: inline-block;
  font-size: 13px;
  line-height: 1.45;
  max-width: 320px;
  white-space: normal;
  padding: 6px 12px;
  border-radius: 8px;
}
.test-action-hint--ok {
  color: #15803d;
  background: #ecfdf5;
  border: 1px solid #bbf7d0;
}
.test-action-hint--error {
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
}
</style>
