<template>
  <div class="config-card" :class="{ 'is-editing': editing }">
    <div class="config-card__header">
      <div class="config-card__title">
        <span v-if="$slots.icon" class="config-card__icon">
          <slot name="icon" />
        </span>
        <span>{{ title }}</span>
        <slot name="status" />
      </div>
      <div class="config-card__actions card-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="config-card__body">
      <slot />
    </div>
    <Transition name="footer-slide">
      <div v-if="$slots.footer" class="config-card__footer">
        <slot name="footer" />
      </div>
    </Transition>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  editing: { type: Boolean, default: false },
});
</script>
