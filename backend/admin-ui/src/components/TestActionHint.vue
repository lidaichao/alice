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
  font-size: 13px;
  line-height: 1.45;
  max-width: 320px;
  white-space: normal;
}
.test-action-hint--ok {
  color: #15803d;
}
.test-action-hint--error {
  color: #b91c1c;
}
</style>
