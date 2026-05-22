<script setup lang="ts">
import { RefreshCw } from '@lucide/vue';
import type { CrawlTask, DiscoveryTask } from '../api/types';
import { formatDateTime } from '../utils/format';
import StatusBadge from './StatusBadge.vue';

defineProps<{
  crawlTasks: CrawlTask[];
  discoveryTasks: DiscoveryTask[];
}>();

const emit = defineEmits<{ refresh: [] }>();

function tone(status: string) {
  if (status === 'SUCCESS' || status === 'SENT') return 'success';
  if (status === 'FAILED') return 'error';
  if (status === 'RUNNING') return 'info';
  return 'neutral';
}
</script>

<template>
  <div class="grid gap-4 xl:grid-cols-2">
    <section class="rounded-box border border-base-300 bg-base-100 shadow-sm">
      <div class="flex items-center justify-between border-b border-base-300 p-4">
        <div>
          <h2 class="text-base font-semibold">抓取任务</h2>
          <p class="text-sm text-base-content/60">查看站点抓取进度和异常。</p>
        </div>
        <button class="btn btn-outline btn-sm" @click="emit('refresh')">
          <RefreshCw class="h-4 w-4" />
          刷新
        </button>
      </div>
      <div class="overflow-x-auto">
        <table class="table table-sm min-w-[760px]">
          <thead>
            <tr>
              <th>批次</th>
              <th>域名</th>
              <th>状态</th>
              <th>页面</th>
              <th>错误</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!crawlTasks.length"><td colspan="6" class="py-8 text-center text-base-content/55">暂无抓取任务。</td></tr>
            <tr v-for="task in crawlTasks" :key="task.id">
              <td>{{ task.batch_id || '-' }}</td>
              <td>{{ task.domain || '-' }}</td>
              <td><StatusBadge :value="task.status" :tone="tone(task.status)" /></td>
              <td>{{ task.pages_done || 0 }}/{{ task.pages_total || 0 }}</td>
              <td><div class="max-w-52 truncate text-xs text-base-content/60">{{ task.error_message || '-' }}</div></td>
              <td class="text-xs text-base-content/60">{{ formatDateTime(task.finished_at || task.started_at || task.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="rounded-box border border-base-300 bg-base-100 shadow-sm">
      <div class="border-b border-base-300 p-4">
        <h2 class="text-base font-semibold">发现任务</h2>
        <p class="text-sm text-base-content/60">保留旧版关键词种子、搜索和外链发现记录。</p>
      </div>
      <div class="overflow-x-auto">
        <table class="table table-sm min-w-[760px]">
          <thead>
            <tr>
              <th>数据源</th>
              <th>类型</th>
              <th>状态</th>
              <th>新增/更新</th>
              <th>关键词</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!discoveryTasks.length"><td colspan="6" class="py-8 text-center text-base-content/55">暂无发现任务。</td></tr>
            <tr v-for="task in discoveryTasks" :key="task.id">
              <td>{{ task.provider_id }}</td>
              <td>{{ task.source_type }}</td>
              <td><StatusBadge :value="task.status" :tone="tone(task.status)" /></td>
              <td>{{ task.created_count }}/{{ task.updated_count }}</td>
              <td><div class="max-w-48 truncate text-xs text-base-content/60">{{ task.keyword || '-' }}</div></td>
              <td class="text-xs text-base-content/60">{{ formatDateTime(task.finished_at || task.started_at || task.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
