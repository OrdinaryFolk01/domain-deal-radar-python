<script setup lang="ts">
const props = defineProps<{
  value: string;
  label?: string;
  tone?: 'neutral' | 'success' | 'warning' | 'error' | 'info';
}>();

const toneClass: Record<string, string> = {
  neutral: 'badge-neutral',
  success: 'badge-success',
  warning: 'badge-warning',
  error: 'badge-error',
  info: 'badge-info',
};
</script>

<template>
  <span class="badge badge-sm whitespace-nowrap" :class="toneClass[props.tone || 'neutral']">
    {{ props.label || props.value || '-' }}
  </span>
</template>
