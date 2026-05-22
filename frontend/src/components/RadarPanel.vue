<script setup lang="ts">
import { AlertTriangle, ChevronDown, Radar, RefreshCw, Search } from '@lucide/vue';
import { computed, onMounted, ref } from 'vue';
import { batchQualifyCandidates, listSearchEngines, startRadarDiscovery } from '../api/radar';
import type { RadarDiscoveryResult, SearchEngine } from '../api/types';

const props = defineProps<{
  candidateStatus: string;
  candidateKeyword: string;
}>();

const emit = defineEmits<{
  refresh: [];
  discoveryComplete: [result: RadarDiscoveryResult];
  updateEngines: [engines: string[]];
  toast: [message: string, tone?: 'success' | 'error' | 'info'];
}>();

const engines = ref<SearchEngine[]>([]);
const selectedEngines = ref<string[]>([]);
const keywordMode = ref('manual');
const keywords = ref('');
const limit = ref(10);
const busy = ref(false);
const batchBusy = ref(false);
const lastDiscoveryErrors = ref<string[]>([]);

const activeEngines = computed(() => selectedEngines.value);
const hasDiscoveryErrors = computed(() => lastDiscoveryErrors.value.length > 0);
const selectedEngineNames = computed(() =>
  engines.value.filter((engine) => selectedEngines.value.includes(engine.provider_id)).map((engine) => engine.name),
);
const visibleDiscoveryErrors = computed(() => lastDiscoveryErrors.value.slice(0, 6));
const hiddenDiscoveryErrorCount = computed(() => Math.max(0, lastDiscoveryErrors.value.length - visibleDiscoveryErrors.value.length));
const engineSummary = computed(() => {
  if (!engines.value.length) return '加载中';
  if (selectedEngines.value.length === engines.value.length) return '全部搜索引擎';
  if (selectedEngineNames.value.length === 1) return selectedEngineNames.value[0];
  return `${selectedEngineNames.value.length} 个搜索引擎`;
});

onMounted(async () => {
  engines.value = await listSearchEngines();
  const enabledEngines = engines.value.filter((item) => item.enabled).map((item) => item.provider_id);
  selectedEngines.value = enabledEngines.length ? enabledEngines : engines.value.map((item) => item.provider_id);
  emit('updateEngines', selectedEngines.value);
});

function toggleEngine(engineId: string) {
  const next = selectedEngines.value.includes(engineId)
    ? selectedEngines.value.filter((id) => id !== engineId)
    : [...selectedEngines.value, engineId];
  if (!next.length) {
    emit('toast', '请至少选择一个搜索引擎', 'error');
    return;
  }
  selectedEngines.value = next;
  emit('updateEngines', selectedEngines.value);
}

async function discover() {
  if (keywordMode.value === 'manual' && !keywords.value.trim()) {
    emit('toast', '请输入关键词，或切换到随机词库', 'error');
    return;
  }
  busy.value = true;
  lastDiscoveryErrors.value = [];
  try {
    const result = await startRadarDiscovery({
      keywords: keywords.value,
      keyword_mode: keywordMode.value,
      search_engines: activeEngines.value,
      limit: limit.value,
      auto_qualify: false,
    });
    lastDiscoveryErrors.value = result.errors || [];
    const summary = `雷达搜索完成：新增 ${result.created}，更新 ${result.updated}，过滤 ${result.rejected}`;
    if (lastDiscoveryErrors.value.length) {
      const firstError = lastDiscoveryErrors.value[0];
      const tone = result.created + result.updated + result.rejected > 0 ? 'info' : 'error';
      emit('toast', `${summary}，提示 ${lastDiscoveryErrors.value.length} 条：${firstError}`, tone);
    } else {
      emit('toast', summary, 'success');
    }
    emit('discoveryComplete', result);
  } finally {
    busy.value = false;
  }
}

async function batchQualify() {
  batchBusy.value = true;
  try {
    const result = await batchQualifyCandidates({
      status: props.candidateStatus,
      keyword: props.candidateKeyword,
      limit: 20,
      site_index_engines: activeEngines.value,
    });
    emit('toast', `预筛完成：合格 ${result.qualified}，淘汰 ${result.rejected}，待补权重 ${result.need_weight}`, 'success');
    emit('refresh');
  } finally {
    batchBusy.value = false;
  }
}
</script>

<template>
  <section class="rounded-box border border-base-300 bg-base-100 p-4 shadow-sm">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <div class="flex items-center gap-2 text-lg font-semibold">
          <Radar class="h-5 w-5 text-primary" />
          雷达发现
        </div>
        <p class="mt-1 text-sm text-base-content/60">搜索结果先进入候选池，通过 site 索引、权重和网站性质后再入库。</p>
      </div>

      <div class="flex flex-wrap items-end gap-2">
        <div class="form-control w-44">
          <span class="label-text">搜索引擎</span>
          <div class="dropdown dropdown-bottom w-full">
            <button type="button" tabindex="0" class="select select-bordered select-sm flex w-full items-center justify-between gap-2 font-normal">
              <span class="truncate">{{ engineSummary }}</span>
            </button>
            <ul tabindex="0" class="dropdown-content menu z-20 mt-1 w-56 rounded-box border border-base-300 bg-base-100 p-2 shadow-lg">
              <li v-for="engine in engines" :key="engine.provider_id">
                <label class="flex cursor-pointer items-center gap-2 rounded-btn px-2 py-2">
                  <input
                    :checked="selectedEngines.includes(engine.provider_id)"
                    type="checkbox"
                    class="checkbox checkbox-primary checkbox-sm"
                    @change="toggleEngine(engine.provider_id)"
                  />
                  <span class="label-text">{{ engine.name }}</span>
                </label>
              </li>
            </ul>
          </div>
        </div>
        <label class="form-control w-40">
          <span class="label-text">关键词模式</span>
          <select v-model="keywordMode" class="select select-bordered select-sm">
            <option value="manual">手动关键词</option>
            <option value="random">随机词库</option>
          </select>
        </label>
        <label class="form-control min-w-64 flex-1">
          <span class="label-text">关键词</span>
          <input v-model="keywords" class="input input-bordered input-sm" placeholder="考研资料, 图片压缩" />
        </label>
        <label class="form-control w-28">
          <span class="label-text">数量</span>
          <input v-model.number="limit" type="number" min="1" max="50" class="input input-bordered input-sm" />
        </label>

        <button class="btn btn-primary btn-sm" :disabled="busy" @click="discover">
          <Search class="h-4 w-4" />
          {{ busy ? '搜索中' : '雷达搜索' }}
        </button>
        <button class="btn btn-outline btn-sm" :disabled="batchBusy" @click="batchQualify">
          <RefreshCw class="h-4 w-4" />
          {{ batchBusy ? '预筛中' : '批量预筛' }}
        </button>
      </div>
    </div>

    <div v-if="hasDiscoveryErrors" class="alert alert-warning mt-3 items-start">
      <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0" />
      <div class="min-w-0">
        <div class="font-medium">部分搜索引擎本轮被跳过</div>
        <p class="mt-1 text-sm">通常是搜索平台验证码或安全验证，系统已继续尝试其他引擎。</p>
        <ul class="mt-1 list-disc space-y-1 pl-5 text-sm">
          <li v-for="error in visibleDiscoveryErrors" :key="error" class="break-words">{{ error }}</li>
        </ul>
        <div v-if="hiddenDiscoveryErrorCount" class="mt-1 text-sm">还有 {{ hiddenDiscoveryErrorCount }} 条同类提示已折叠。</div>
      </div>
    </div>
  </section>
</template>
