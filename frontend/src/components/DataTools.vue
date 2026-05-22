<script setup lang="ts">
import { Download, FileInput, Plus, RotateCcw, Wrench } from '@lucide/vue';
import { onBeforeUnmount, onMounted, ref } from 'vue';
import { createManualLeads, importProviderCsv, listProviders } from '../api/radar';

const emit = defineEmits<{
  refresh: [];
  toast: [message: string, tone?: 'success' | 'error' | 'info'];
}>();

const providers = ref<Array<{ provider_id: string; name: string }>>([]);
const providerId = ref('aizhan_rank_manual_csv');
const dropdownRef = ref<HTMLElement | null>(null);
const toolsOpen = ref(false);
const manualOpen = ref(false);
const domains = ref('');
const title = ref('');
const remark = ref('');
const autoCrawl = ref(false);
const autoAnalyze = ref(false);

onMounted(async () => {
  document.addEventListener('pointerdown', handleDocumentPointerDown);
  document.addEventListener('keydown', handleDocumentKeydown);
  providers.value = await listProviders();
  if (!providers.value.some((item) => item.provider_id === providerId.value)) {
    providerId.value = providers.value[0]?.provider_id || 'generic_csv';
  }
});

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown);
  document.removeEventListener('keydown', handleDocumentKeydown);
});

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target;
  if (target instanceof Node && dropdownRef.value?.contains(target)) return;
  toolsOpen.value = false;
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return;
  if (manualOpen.value) {
    closeManual();
    return;
  }
  toolsOpen.value = false;
}

function toggleTools() {
  toolsOpen.value = !toolsOpen.value;
}

function closeTools() {
  toolsOpen.value = false;
}

function openManual() {
  manualOpen.value = true;
  closeTools();
}

function closeManual() {
  manualOpen.value = false;
}

async function handleCsv(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  (event.target as HTMLInputElement).value = '';
  if (!file) return;
  closeTools();
  const result = await importProviderCsv(providerId.value, file);
  emit('toast', `导入完成：新增 ${result.created}，更新 ${result.updated}`, 'success');
  emit('refresh');
}

async function submitManual() {
  const result = await createManualLeads({
    domains: domains.value,
    title: title.value,
    remark: remark.value,
    auto_crawl: autoCrawl.value,
    auto_analyze: autoAnalyze.value,
  });
  emit('toast', `手动新增完成：新增 ${result.created}，更新 ${result.updated}`, 'success');
  domains.value = '';
  title.value = '';
  remark.value = '';
  closeManual();
  emit('refresh');
}
</script>

<template>
  <div ref="dropdownRef" class="dropdown dropdown-end" :class="{ 'dropdown-open': toolsOpen }">
    <button
      type="button"
      class="btn btn-outline btn-sm"
      aria-haspopup="menu"
      :aria-expanded="toolsOpen"
      @click.stop="toggleTools"
    >
      <Wrench class="h-4 w-4" />
      数据工具
    </button>

    <div
      class="dropdown-content z-40 mt-2 w-72 rounded-box border border-base-300 bg-base-100 p-3 shadow-lg"
      role="menu"
      @click.stop
    >
      <div class="space-y-2">
        <select v-model="providerId" class="select select-bordered select-sm w-full">
          <option v-for="provider in providers" :key="provider.provider_id" :value="provider.provider_id">
            {{ provider.name }}
          </option>
        </select>

        <button class="btn btn-primary btn-sm w-full justify-start" @click="openManual">
          <Plus class="h-4 w-4" />
          手动新增
        </button>

        <label class="btn btn-ghost btn-sm w-full justify-start">
          <FileInput class="h-4 w-4" />
          导入 CSV
          <input type="file" accept=".csv,.txt,text/csv,text/plain" class="hidden" @change="handleCsv" />
        </label>

        <div class="divider my-1"></div>

        <a class="btn btn-ghost btn-sm w-full justify-start" href="/api/export/csv" @click="closeTools">
          <Download class="h-4 w-4" />
          导出 CSV
        </a>
        <a class="btn btn-ghost btn-sm w-full justify-start" href="/api/export/json" @click="closeTools">
          <RotateCcw class="h-4 w-4" />
          备份 JSON
        </a>
      </div>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="manualOpen" class="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="manual-leads-title">
      <div class="modal-box max-w-2xl">
        <h3 id="manual-leads-title" class="text-lg font-semibold">手动新增域名</h3>
        <div class="mt-4 space-y-4">
          <label class="form-control">
            <span class="label-text">域名 / URL</span>
            <textarea v-model="domains" class="textarea textarea-bordered min-h-36" placeholder="example.com&#10;https://demo.cn/contact"></textarea>
          </label>
          <div class="grid gap-3 md:grid-cols-2">
            <label class="form-control">
              <span class="label-text">默认标题</span>
              <input v-model="title" class="input input-bordered" placeholder="可不填" />
            </label>
            <label class="form-control">
              <span class="label-text">备注</span>
              <input v-model="remark" class="input input-bordered" placeholder="来源或判断" />
            </label>
          </div>
          <div class="flex flex-wrap gap-4">
            <label class="label cursor-pointer gap-2">
              <input v-model="autoCrawl" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span class="label-text">新增后抓联系方式</span>
            </label>
            <label class="label cursor-pointer gap-2">
              <input v-model="autoAnalyze" type="checkbox" class="checkbox checkbox-primary checkbox-sm" />
              <span class="label-text">新增后增强分析</span>
            </label>
          </div>
        </div>
        <div class="modal-action">
          <button class="btn btn-ghost" @click="closeManual">取消</button>
          <button class="btn btn-primary" :disabled="!domains.trim()" @click="submitManual">提交</button>
        </div>
      </div>
      <div class="modal-backdrop bg-neutral/40" @click="closeManual"></div>
    </div>
  </Teleport>
</template>
