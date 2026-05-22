<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { listDiscoveryTasks, listTasks } from '../api/radar';
import type { CrawlTask, DiscoveryTask } from '../api/types';
import TaskTables from '../components/TaskTables.vue';

type ToastTone = 'success' | 'error' | 'info';

const emit = defineEmits<{
  loading: [value: boolean];
  toast: [message: string, tone?: ToastTone];
}>();

const crawlTasks = ref<CrawlTask[]>([]);
const discoveryTasks = ref<DiscoveryTask[]>([]);

async function refreshTasks() {
  emit('loading', true);
  try {
    const [crawlRows, discoveryRows] = await Promise.all([listTasks(), listDiscoveryTasks()]);
    crawlTasks.value = crawlRows;
    discoveryTasks.value = discoveryRows;
  } catch (error) {
    emit('toast', error instanceof Error ? error.message : '操作失败', 'error');
  } finally {
    emit('loading', false);
  }
}

onMounted(refreshTasks);
defineExpose({ refresh: refreshTasks });
</script>

<template>
  <TaskTables :crawl-tasks="crawlTasks" :discovery-tasks="discoveryTasks" @refresh="refreshTasks" />
</template>
