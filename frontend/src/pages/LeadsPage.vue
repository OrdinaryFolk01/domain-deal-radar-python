<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { listLeads } from '../api/radar';
import type { Lead } from '../api/types';
import LeadDetailDrawer from '../components/LeadDetailDrawer.vue';
import LeadTable from '../components/LeadTable.vue';

type ToastTone = 'success' | 'error' | 'info';

interface LeadTableFilters {
  keyword: string;
  status: string;
  crawl_status: string;
  risk: string;
  min_score: string;
}

const emit = defineEmits<{
  loading: [value: boolean];
  toast: [message: string, tone?: ToastTone];
}>();

const leads = ref<Lead[]>([]);
const selectedLeadId = ref<number | null>(null);
const leadFilters = reactive<LeadTableFilters>({
  keyword: '',
  status: '',
  crawl_status: '',
  risk: '',
  min_score: '',
});

function forwardToast(message: string, tone?: ToastTone) {
  emit('toast', message, tone);
}

async function guarded(task: () => Promise<void>) {
  emit('loading', true);
  try {
    await task();
  } catch (error) {
    emit('toast', error instanceof Error ? error.message : '操作失败', 'error');
  } finally {
    emit('loading', false);
  }
}

async function refreshLeads() {
  await guarded(async () => {
    leads.value = await listLeads(leadFilters);
  });
}

function updateLeadFilters(next: LeadTableFilters) {
  Object.assign(leadFilters, next);
}

onMounted(refreshLeads);
defineExpose({ refresh: refreshLeads });
</script>

<template>
  <LeadTable
    :leads="leads"
    :filters="leadFilters"
    @refresh="refreshLeads"
    @update-filters="updateLeadFilters"
    @open-lead="selectedLeadId = $event"
  />

  <LeadDetailDrawer
    :lead-id="selectedLeadId"
    @close="selectedLeadId = null"
    @refresh="refreshLeads"
    @toast="forwardToast"
  />
</template>
