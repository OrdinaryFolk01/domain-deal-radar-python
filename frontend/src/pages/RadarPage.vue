<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { listCandidates, listLeads } from '../api/radar';
import type { DomainCandidate, Lead, RadarDiscoveryResult, RadarSearchHistoryEntry } from '../api/types';
import CandidateTable from '../components/CandidateTable.vue';
import RadarPanel from '../components/RadarPanel.vue';
import StatCard from '../components/StatCard.vue';

type ToastTone = 'success' | 'error' | 'info';
const SEARCH_HISTORY_STORAGE_KEY = 'domain-deal-radar.searchHistory.v1';

const emit = defineEmits<{
  loading: [value: boolean];
  toast: [message: string, tone?: ToastTone];
}>();

const leads = ref<Lead[]>([]);
const candidates = ref<DomainCandidate[]>([]);
const candidateEngines = ref(['baidu', 'bing']);
const searchHistory = ref<RadarSearchHistoryEntry[]>(loadSearchHistory());
const activeHistoryId = ref(searchHistory.value[0]?.id || '');

const leadFilters = reactive({
  keyword: '',
  status: '',
  crawl_status: '',
  risk: '',
  min_score: '',
});

const candidateFilters = reactive({
  status: '',
  keyword: '',
  sources: [] as string[],
});

const highPriorityCount = computed(() => leads.value.filter((lead) => lead.score >= 85).length);
const qualifiedCandidates = computed(() => candidates.value.filter((item) => item.status === 'QUALIFIED').length);
const followUpDueCount = computed(() => leads.value.filter((lead) => lead.next_follow_up_at && new Date(lead.next_follow_up_at).getTime() <= Date.now()).length);
const activeHistory = computed(() => searchHistory.value.find((entry) => entry.id === activeHistoryId.value) || null);
const activeCandidateIds = computed(() => activeHistory.value?.candidateIds || []);

function loadSearchHistory(): RadarSearchHistoryEntry[] {
  try {
    const raw = window.localStorage.getItem(SEARCH_HISTORY_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as RadarSearchHistoryEntry[]) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((entry) => entry && typeof entry.id === 'string' && Array.isArray(entry.candidateIds))
      .map((entry) => ({
        id: entry.id,
        searchedAt: typeof entry.searchedAt === 'string' ? entry.searchedAt : '',
        keywords: Array.isArray(entry.keywords) ? entry.keywords : [],
        searchEngines: Array.isArray(entry.searchEngines) ? entry.searchEngines : [],
        candidateIds: entry.candidateIds,
        created: Number(entry.created || 0),
        updated: Number(entry.updated || 0),
        rejected: Number(entry.rejected || 0),
        errorsCount: Number(entry.errorsCount || 0),
      }))
      .slice(0, 20);
  } catch {
    return [];
  }
}

function persistSearchHistory(entries: RadarSearchHistoryEntry[]) {
  try {
    window.localStorage.setItem(SEARCH_HISTORY_STORAGE_KEY, JSON.stringify(entries.slice(0, 20)));
  } catch {
    // Browser storage may be unavailable; the in-memory history still works for this session.
  }
}

function buildSearchHistoryEntry(result: RadarDiscoveryResult): RadarSearchHistoryEntry {
  const candidateIds = Array.from(new Set((result.candidate_ids || []).map((id) => Number(id)).filter((id) => Number.isFinite(id))));
  return {
    id: `${Date.now()}-${candidateIds.join('-') || 'empty'}`,
    searchedAt: new Date().toISOString(),
    keywords: result.keywords || [],
    searchEngines: result.search_engines || [],
    candidateIds,
    created: result.created,
    updated: result.updated,
    rejected: result.rejected,
    errorsCount: (result.errors || []).length,
  };
}

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
  leads.value = await listLeads(leadFilters);
}

async function refreshCandidates() {
  const history = activeHistory.value;
  const ids = activeCandidateIds.value;
  if (history && !ids.length) {
    candidates.value = [];
    return;
  }
  candidates.value = await listCandidates({
    status: candidateFilters.status,
    keyword: candidateFilters.keyword,
    sources: candidateFilters.sources.join(','),
    ids: history ? ids.join(',') : undefined,
    limit: history ? Math.min(1000, Math.max(500, ids.length)) : 500,
  });
}

async function handleDiscoveryComplete(result: RadarDiscoveryResult) {
  const entry = buildSearchHistoryEntry(result);
  searchHistory.value = [entry, ...searchHistory.value.filter((item) => item.id !== entry.id)].slice(0, 20);
  persistSearchHistory(searchHistory.value);
  activeHistoryId.value = entry.id;
  candidateFilters.status = '';
  candidateFilters.keyword = '';
  candidateFilters.sources = [];
  await refreshCandidates();
}

async function selectSearchHistory(historyId: string) {
  activeHistoryId.value = historyId;
  await refreshCandidates();
}

async function refreshAll() {
  await guarded(async () => {
    await Promise.all([refreshLeads(), refreshCandidates()]);
  });
}

onMounted(refreshAll);
defineExpose({ refresh: refreshAll });
</script>

<template>
  <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
    <StatCard label="正式线索" :value="leads.length" hint="可直接跟进" />
    <StatCard label="高优先级" :value="highPriorityCount" hint="评分 85+" />
    <StatCard label="候选池" :value="candidates.length" hint="待预筛" />
    <StatCard label="合格候选" :value="qualifiedCandidates" hint="可转入线索库" />
    <StatCard label="待跟进" :value="followUpDueCount" hint="需要处理" />
  </section>

  <RadarPanel
    :candidate-status="candidateFilters.status"
    :candidate-keyword="candidateFilters.keyword"
    @discovery-complete="handleDiscoveryComplete"
    @refresh="refreshCandidates"
    @update-engines="candidateEngines = $event"
    @toast="forwardToast"
  />

  <CandidateTable
    :candidates="candidates"
    :selected-engines="candidateEngines"
    :status="candidateFilters.status"
    :keyword="candidateFilters.keyword"
    :source-filter="candidateFilters.sources"
    :search-history="searchHistory"
    :active-history-id="activeHistoryId"
    @update-status="candidateFilters.status = $event"
    @update-keyword="candidateFilters.keyword = $event"
    @update-source-filter="candidateFilters.sources = $event"
    @select-history="selectSearchHistory"
    @refresh="refreshCandidates"
    @toast="forwardToast"
  />
</template>
