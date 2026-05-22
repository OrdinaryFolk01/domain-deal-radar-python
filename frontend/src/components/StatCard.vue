<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  hint?: string;
}>();
</script>

<template>
  <div class="rounded-box border border-base-300 bg-base-100 p-4 shadow-sm">
    <div class="text-xs font-medium uppercase tracking-wide text-base-content/55">{{ label }}</div>
    <div class="mt-2 text-2xl font-semibold text-base-content">{{ value }}</div>
    <div v-if="hint" class="mt-1 text-xs text-base-content/55">{{ hint }}</div>
  </div>
</template>
