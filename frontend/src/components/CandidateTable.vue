<script setup lang="ts">
import {
  AlertCircle,
  CheckCircle2,
  Copy,
  Database,
  ExternalLink,
  PencilLine,
  RefreshCw,
  Search,
  ShieldCheck,
  SignalHigh,
  X,
} from '@lucide/vue';
import { computed, reactive, ref, watch } from 'vue';
import { promoteCandidate, qualifyCandidate, refreshCandidateIntel, updateCandidateWeight } from '../api/radar';
import type { DomainCandidate, RadarSearchHistoryEntry } from '../api/types';
import { formatDateTime, numberText, parseJson } from '../utils/format';
import StatusBadge from './StatusBadge.vue';

const props = defineProps<{
  candidates: DomainCandidate[];
  selectedEngines: string[];
  status: string;
  keyword: string;
  sourceFilter: string[];
  searchHistory: RadarSearchHistoryEntry[];
  activeHistoryId: string;
}>();

const emit = defineEmits<{
  refresh: [];
  updateStatus: [value: string];
  updateKeyword: [value: string];
  updateSourceFilter: [value: string[]];
  selectHistory: [value: string];
  toast: [message: string, tone?: 'success' | 'error' | 'info'];
}>();

const busyId = ref<number | null>(null);
const currentPage = ref(1);
const pageSize = ref(20);
const weightModalCandidate = ref<DomainCandidate | null>(null);
const weightLookupState = ref<'idle' | 'loading' | 'success' | 'failed'>('idle');
const weightLookupError = ref('');
const showManualFallback = ref(false);

const statusLabel: Record<string, string> = {
  DISCOVERED: '已发现',
  REJECTED: '已淘汰',
  NEED_WEIGHT: '待补权重',
  NEED_SITE_INDEX: '待补索引',
  QUALIFIED: '已合格',
  PROMOTED: '已入库',
};

const sourceOptions = [
  { id: 'baidu', label: '百度' },
  { id: 'sogou', label: '搜狗' },
  { id: '360', label: '360' },
  { id: 'bing', label: 'Bing' },
  { id: 'toutiao', label: '头条' },
  { id: 'google', label: '谷歌' },
];

const weightFields = [
  { key: 'baidu_pc_weight', label: '百度 PC' },
  { key: 'baidu_mobile_weight', label: '百度移动' },
  { key: 'sogou_weight', label: '搜狗' },
  { key: 'so_weight', label: '360' },
  { key: 'sm_weight', label: '神马' },
  { key: 'toutiao_weight', label: '头条' },
  { key: 'bing_weight', label: '必应' },
] as const;

const indexedFields = [
  { key: 'indexed_count', label: '百度收录' },
  { key: 'sogou_indexed_count', label: '搜狗收录' },
  { key: 'so_indexed_count', label: '360收录' },
  { key: 'sm_indexed_count', label: '神马收录' },
  { key: 'toutiao_indexed_count', label: '头条收录' },
  { key: 'bing_indexed_count', label: '必应收录' },
] as const;

type WeightKey = (typeof weightFields)[number]['key'];
type IndexedKey = (typeof indexedFields)[number]['key'];
type NumberFieldKey = WeightKey | IndexedKey;

type WeightSnapshot = {
  checked_at?: string;
  source?: string;
  source_url?: string;
  status?: string;
  weights?: Partial<Record<WeightKey, number>>;
  indexed_counts?: Partial<Record<IndexedKey, number>>;
  site_nature?: string;
  metadata?: Record<string, string | number>;
  error?: string;
};

type WhoisIntelItem = {
  registrar?: string;
  registrar_email?: string;
  registrar_phone?: string;
  dns_servers?: string[];
};

type WhoisSnapshot = {
  results?: WhoisIntelItem[];
};

const weightForm = reactive<Record<NumberFieldKey, number> & { site_nature: string }>({
  baidu_pc_weight: 0,
  baidu_mobile_weight: 0,
  sogou_weight: 0,
  so_weight: 0,
  sm_weight: 0,
  toutiao_weight: 0,
  bing_weight: 0,
  indexed_count: 0,
  sogou_indexed_count: 0,
  so_indexed_count: 0,
  sm_indexed_count: 0,
  toutiao_indexed_count: 0,
  bing_indexed_count: 0,
  site_nature: '',
});

function statusTone(status: string) {
  if (status === 'QUALIFIED' || status === 'PROMOTED') return 'success';
  if (status === 'REJECTED') return 'error';
  if (status === 'NEED_WEIGHT' || status === 'NEED_SITE_INDEX') return 'warning';
  return 'neutral';
}

function getWeightSnapshot(candidate: DomainCandidate | null) {
  return parseJson<WeightSnapshot>(candidate?.weight_snapshot || '', {});
}

function siteIndexSummary(candidate: DomainCandidate) {
  const snapshot = parseJson<{ results?: Array<{ engine: string; count: number | null }> }>(candidate.site_index_snapshot, {});
  if (!snapshot.results?.length) return '-';
  return snapshot.results.map((item) => `${item.engine}:${Number.isInteger(item.count) ? numberText(item.count || 0) : '异常'}`).join(' / ');
}

function hasWeightData(snapshot: WeightSnapshot) {
  const weights = snapshot.weights || {};
  return snapshot.status === 'SUCCESS' && (Object.values(weights).some((value) => Number(value || 0) > 0) || Boolean(snapshot.site_nature));
}

function weightSourceLabel(source?: string) {
  if (source === 'aizhan_public') return '爱站';
  if (source === 'manual_after_aizhan_failure' || source === 'manual') return '手动';
  return source || '未查询';
}

function weightStatusText(candidate: DomainCandidate) {
  const snapshot = getWeightSnapshot(candidate);
  if (!snapshot.status) return '-';
  if (snapshot.status === 'ERROR' || snapshot.status === 'MISSING') return '爱站获取失败，待手动补充';
  return `${weightSourceLabel(snapshot.source)} / ${snapshot.site_nature || '-'}`;
}

function intelSummary(candidate: DomainCandidate) {
  const whois = parseJson<WhoisSnapshot>(candidate.whois_snapshot, {});
  const ip = parseJson<{ isp?: string; org?: string; country?: string; is_domestic?: boolean }>(candidate.ip_snapshot, {});
  const registrar = whois.results?.find((item) => item.registrar)?.registrar || '-';
  const isp = ip.isp || ip.org || '-';
  return `${registrar} / ${isp}${ip.is_domestic ? ' / 国内' : ip.country ? ` / ${ip.country}` : ''}`;
}

function auxiliaryWhoisContact(candidate: DomainCandidate) {
  const whois = parseJson<WhoisSnapshot>(candidate.whois_snapshot, {});
  const item = whois.results?.find((result) => result.registrar_email || result.registrar_phone || result.dns_servers?.length);
  if (!item) return '';
  if (item.registrar_email) return item.registrar_email;
  if (item.registrar_phone) return item.registrar_phone;
  return item.dns_servers?.[0] || '';
}

function sourceSummary(candidate: DomainCandidate) {
  const engines = parseJson<string[]>(candidate.search_engines, []);
  const keywords = parseJson<string[]>(candidate.keywords, []);
  return {
    engines: engines.join(' / ') || candidate.search_engine || '-',
    keywords: keywords.join('，') || candidate.keyword || '-',
  };
}

const emptyText = computed(() => (props.keyword || props.status || props.sourceFilter.length ? '当前筛选下没有候选。' : '暂无候选，请先执行雷达搜索。'));
const activeWeightSnapshot = computed(() => getWeightSnapshot(weightModalCandidate.value));
const activeHistoryEntry = computed(() => props.searchHistory.find((entry) => entry.id === props.activeHistoryId) || null);
const manualFallbackVisible = computed(
  () => showManualFallback.value || weightLookupState.value === 'failed' || activeWeightSnapshot.value.status === 'ERROR' || activeWeightSnapshot.value.status === 'MISSING',
);
const manualFallbackDisabled = computed(() => weightLookupState.value === 'loading');
const totalPages = computed(() => Math.max(1, Math.ceil(props.candidates.length / pageSize.value)));
const pageStart = computed(() => (currentPage.value - 1) * pageSize.value);
const pagedCandidates = computed(() => props.candidates.slice(pageStart.value, pageStart.value + pageSize.value));
const candidateScopeText = computed(() => {
  if (activeHistoryEntry.value) {
    return `当前显示 ${formatDateTime(activeHistoryEntry.value.searchedAt)} 的搜索结果，按最近更新时间排序。`;
  }
  return '当前显示全部历史候选，按最近更新时间排序。';
});
const sourceSummaryText = computed(() => {
  if (!props.sourceFilter.length) return '全部来源';
  const names = sourceOptions.filter((item) => props.sourceFilter.includes(item.id)).map((item) => item.label);
  return names.length === 1 ? names[0] : `${names.length} 个来源`;
});
const visibleRangeText = computed(() => {
  if (!props.candidates.length) return '0 / 0';
  const end = Math.min(pageStart.value + pageSize.value, props.candidates.length);
  return `${pageStart.value + 1}-${end} / ${props.candidates.length}`;
});

watch(
  () => [props.candidates.length, props.status, props.keyword, props.sourceFilter.join(','), props.activeHistoryId, pageSize.value],
  () => {
    currentPage.value = 1;
  },
);

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

function snapshotNumber(snapshot: WeightSnapshot, key: NumberFieldKey) {
  if (key in (snapshot.weights || {})) return Number(snapshot.weights?.[key as WeightKey] || 0);
  return Number(snapshot.indexed_counts?.[key as IndexedKey] || 0);
}

function setNumberField(key: NumberFieldKey, value: string) {
  weightForm[key] = Number(value || 0);
}

function toggleSourceFilter(sourceId: string) {
  const next = props.sourceFilter.includes(sourceId) ? props.sourceFilter.filter((id) => id !== sourceId) : [...props.sourceFilter, sourceId];
  emit('updateSourceFilter', next);
  emit('refresh');
}

function clearSourceFilter() {
  emit('updateSourceFilter', []);
  emit('refresh');
}

function goPage(page: number) {
  currentPage.value = Math.min(Math.max(page, 1), totalPages.value);
}

function searchHistoryLabel(entry: RadarSearchHistoryEntry) {
  const keywordText = entry.keywords.filter(Boolean).slice(0, 2).join(' / ') || '随机词库';
  const hiddenKeywordCount = Math.max(0, entry.keywords.length - 2);
  const suffix = hiddenKeywordCount ? ` +${hiddenKeywordCount}` : '';
  return `${formatDateTime(entry.searchedAt)} · ${keywordText}${suffix} · ${entry.candidateIds.length} 条`;
}

function seedWeightForm(candidate: DomainCandidate | null) {
  const snapshot = getWeightSnapshot(candidate);
  for (const field of weightFields) {
    weightForm[field.key] = Number(snapshot.weights?.[field.key] || 0);
  }
  for (const field of indexedFields) {
    weightForm[field.key] = Number(snapshot.indexed_counts?.[field.key] || 0);
  }
  weightForm.site_nature = snapshot.site_nature || '';
}

function fallbackCopyText(text: string) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.top = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(textarea);
  if (!copied) throw new Error('copy failed');
}

async function copyDomain(candidate: DomainCandidate) {
  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(candidate.domain);
    } else {
      fallbackCopyText(candidate.domain);
    }
    emit('toast', `已复制域名：${candidate.domain}`, 'success');
  } catch {
    emit('toast', `复制失败，请手动复制：${candidate.domain}`, 'error');
  }
}

async function runQualify(candidate: DomainCandidate) {
  busyId.value = candidate.id;
  try {
    await qualifyCandidate(candidate.id, props.selectedEngines);
    emit('toast', '候选预筛已执行', 'success');
    emit('refresh');
  } finally {
    busyId.value = null;
  }
}

function openWeightModal(candidate: DomainCandidate) {
  weightModalCandidate.value = candidate;
  weightLookupError.value = '';
  showManualFallback.value = false;
  seedWeightForm(candidate);
  weightLookupState.value = hasWeightData(getWeightSnapshot(candidate)) ? 'success' : 'idle';
  if (weightLookupState.value === 'idle') {
    void lookupAizhanWeight();
  }
}

function closeWeightModal() {
  if (weightLookupState.value === 'loading') return;
  weightModalCandidate.value = null;
  weightLookupError.value = '';
  showManualFallback.value = false;
}

async function lookupAizhanWeight() {
  const candidate = weightModalCandidate.value;
  if (!candidate) return;
  busyId.value = candidate.id;
  weightLookupState.value = 'loading';
  weightLookupError.value = '';
  showManualFallback.value = false;
  try {
    const updated = await updateCandidateWeight(candidate.id, {});
    weightModalCandidate.value = updated;
    seedWeightForm(updated);
    const snapshot = getWeightSnapshot(updated);
    if (hasWeightData(snapshot)) {
      weightLookupState.value = 'success';
      emit('toast', '已从爱站获取权重/网站性质并重新预筛', 'success');
      emit('refresh');
      return;
    }
    weightLookupState.value = 'failed';
    weightLookupError.value = snapshot.error || '爱站未返回可用权重或网站性质数据';
    showManualFallback.value = true;
  } catch (error) {
    weightLookupState.value = 'failed';
    weightLookupError.value = error instanceof Error ? error.message : '爱站查询失败';
    showManualFallback.value = true;
  } finally {
    busyId.value = null;
  }
}

async function submitManualWeight() {
  const candidate = weightModalCandidate.value;
  if (!candidate) return;
  busyId.value = candidate.id;
  weightLookupState.value = 'loading';
  try {
    const updated = await updateCandidateWeight(candidate.id, { ...weightForm });
    weightModalCandidate.value = updated;
    seedWeightForm(updated);
    weightLookupState.value = 'success';
    showManualFallback.value = false;
    emit('toast', '手动补充已保存并重新预筛', 'success');
    emit('refresh');
  } catch (error) {
    weightLookupState.value = 'failed';
    weightLookupError.value = error instanceof Error ? error.message : '手动补充保存失败';
  } finally {
    busyId.value = null;
  }
}

async function refreshIntel(candidate: DomainCandidate) {
  busyId.value = candidate.id;
  try {
    await refreshCandidateIntel(candidate.id);
    emit('toast', 'Whois/IP 情报已刷新', 'success');
    emit('refresh');
  } finally {
    busyId.value = null;
  }
}

async function promote(candidate: DomainCandidate) {
  if (!window.confirm(`确认将 ${candidate.domain} 转入正式线索库？`)) return;
  busyId.value = candidate.id;
  try {
    await promoteCandidate(candidate.id, true);
    emit('toast', '已转入正式线索库', 'success');
    emit('refresh');
  } finally {
    busyId.value = null;
  }
}
</script>

<template>
  <section class="rounded-box border border-base-300 bg-base-100 shadow-sm">
    <div class="flex flex-col gap-3 border-b border-base-300 p-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h2 class="text-base font-semibold">候选池</h2>
        <p class="text-sm text-base-content/60">候选不会污染正式线索库，合格后再入库跟进。</p>
        <p class="mt-1 text-xs text-base-content/50">{{ candidateScopeText }}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <select :value="activeHistoryId" class="select select-bordered select-sm w-64" title="查看历史记录" @change="emit('selectHistory', ($event.target as HTMLSelectElement).value)">
          <option value="">全部历史候选</option>
          <option v-for="entry in searchHistory" :key="entry.id" :value="entry.id">{{ searchHistoryLabel(entry) }}</option>
        </select>
        <input
          :value="keyword"
          class="input input-bordered input-sm w-64"
          placeholder="筛选域名 / 关键词 / 原因"
          @input="emit('updateKeyword', ($event.target as HTMLInputElement).value)"
          @keydown.enter="emit('refresh')"
        />
        <select :value="status" class="select select-bordered select-sm w-40" @change="emit('updateStatus', ($event.target as HTMLSelectElement).value)">
          <option value="">全部状态</option>
          <option value="DISCOVERED">已发现</option>
          <option value="NEED_SITE_INDEX">待补索引</option>
          <option value="NEED_WEIGHT">待补权重</option>
          <option value="QUALIFIED">已合格</option>
          <option value="REJECTED">已淘汰</option>
          <option value="PROMOTED">已入库</option>
        </select>
        <div class="dropdown dropdown-bottom">
          <button type="button" tabindex="0" class="select select-bordered select-sm flex w-36 items-center justify-between gap-2 font-normal">
            <span class="truncate">{{ sourceSummaryText }}</span>
          </button>
          <ul tabindex="0" class="dropdown-content menu z-20 mt-1 w-52 rounded-box border border-base-300 bg-base-100 p-2 shadow-lg">
            <li>
              <button type="button" class="text-xs" @click="clearSourceFilter">全部来源</button>
            </li>
            <li v-for="source in sourceOptions" :key="source.id">
              <label class="flex cursor-pointer items-center gap-2 rounded-btn px-2 py-2">
                <input
                  :checked="sourceFilter.includes(source.id)"
                  type="checkbox"
                  class="checkbox checkbox-primary checkbox-sm"
                  @change="toggleSourceFilter(source.id)"
                />
                <span class="label-text">{{ source.label }}</span>
              </label>
            </li>
          </ul>
        </div>
        <button class="btn btn-outline btn-sm" @click="emit('refresh')">
          <RefreshCw class="h-4 w-4" />
          刷新
        </button>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="table table-zebra table-sm min-w-[1280px]">
        <thead>
          <tr>
            <th>候选域名</th>
            <th>来源</th>
            <th>状态</th>
            <th>site 索引</th>
            <th>权重/性质</th>
            <th>Whois/IP</th>
            <th>原因</th>
            <th class="w-64">操作</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!candidates.length">
            <td colspan="9" class="py-8 text-center text-base-content/55">{{ emptyText }}</td>
          </tr>
          <tr v-for="candidate in pagedCandidates" :key="candidate.id">
            <td>
              <a class="link-hover font-semibold text-primary" :href="`https://${candidate.domain}`" target="_blank" rel="noreferrer">{{ candidate.domain }}</a>
              <div class="max-w-xs truncate text-xs text-base-content/55">{{ candidate.title || '-' }}</div>
            </td>
            <td>
              <div>{{ sourceSummary(candidate).engines }}</div>
              <div class="max-w-56 truncate text-xs text-base-content/55">{{ sourceSummary(candidate).keywords }}</div>
            </td>
            <td>
              <StatusBadge :value="candidate.status" :label="statusLabel[candidate.status]" :tone="statusTone(candidate.status)" />
              <div class="mt-1 text-xs text-base-content/55">优先级 {{ candidate.priority_score }}</div>
            </td>
            <td>{{ siteIndexSummary(candidate) }}</td>
            <td>
              <div class="grid w-56 grid-cols-2 gap-1">
                <div v-for="field in weightFields" :key="field.key" class="flex items-center justify-between rounded border border-base-300 bg-base-100 px-1.5 py-0.5 text-xs">
                  <span class="text-base-content/60">{{ field.label }}</span>
                  <span class="font-semibold">{{ snapshotNumber(getWeightSnapshot(candidate), field.key) }}</span>
                </div>
              </div>
              <div class="mt-1 text-xs text-base-content/60">{{ weightStatusText(candidate) }}</div>
            </td>
            <td>
              <div class="max-w-64 text-xs">{{ intelSummary(candidate) }}</div>
              <div v-if="auxiliaryWhoisContact(candidate)" class="mt-1 max-w-64 truncate text-xs text-base-content/50">
                辅助：{{ auxiliaryWhoisContact(candidate) }}
              </div>
            </td>
            <td><div class="max-w-64 text-xs text-base-content/60">{{ candidate.reject_reason || '-' }}</div></td>
            <td>
              <div class="flex flex-wrap gap-1">
                <button class="btn btn-ghost btn-xs" :aria-label="`复制域名 ${candidate.domain}`" :title="`复制域名 ${candidate.domain}`" @click="copyDomain(candidate)">
                  <Copy class="h-3.5 w-3.5" />
                  复制
                </button>
                <button class="btn btn-ghost btn-xs" :disabled="busyId === candidate.id" @click="runQualify(candidate)">
                  <ShieldCheck class="h-3.5 w-3.5" />
                  预筛
                </button>
                <button class="btn btn-ghost btn-xs" :disabled="busyId === candidate.id" @click="openWeightModal(candidate)">
                  <Search class="h-3.5 w-3.5" />
                  补权重
                </button>
                <button class="btn btn-ghost btn-xs" :disabled="busyId === candidate.id" @click="refreshIntel(candidate)">
                  <SignalHigh class="h-3.5 w-3.5" />
                  情报
                </button>
                <button class="btn btn-primary btn-xs" :disabled="busyId === candidate.id || candidate.status !== 'QUALIFIED'" @click="promote(candidate)">
                  <Database class="h-3.5 w-3.5" />
                  入库
                </button>
              </div>
            </td>
            <td class="whitespace-nowrap text-xs text-base-content/60">{{ formatDateTime(candidate.updated_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="flex flex-col gap-2 border-t border-base-300 p-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="text-xs text-base-content/60">{{ visibleRangeText }}</div>
      <div class="flex flex-wrap items-center gap-2">
        <select v-model.number="pageSize" class="select select-bordered select-xs w-24">
          <option :value="10">10 / 页</option>
          <option :value="20">20 / 页</option>
          <option :value="50">50 / 页</option>
        </select>
        <div class="join">
          <button class="btn join-item btn-xs" :disabled="currentPage <= 1" @click="goPage(1)">首页</button>
          <button class="btn join-item btn-xs" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
          <button class="btn join-item btn-xs pointer-events-none">第 {{ currentPage }} / {{ totalPages }} 页</button>
          <button class="btn join-item btn-xs" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
        </div>
      </div>
    </div>
  </section>

  <div v-if="weightModalCandidate" class="modal modal-open">
    <div class="modal-box w-11/12 max-w-5xl p-0">
      <div class="flex items-start justify-between gap-4 border-b border-base-300 p-5">
        <div>
          <div class="flex items-center gap-2">
            <Search class="h-5 w-5 text-primary" />
            <h3 class="text-lg font-semibold">补权重</h3>
          </div>
          <p class="mt-1 text-sm text-base-content/60">{{ weightModalCandidate.domain }}</p>
        </div>
        <button class="btn btn-ghost btn-sm btn-square" :disabled="weightLookupState === 'loading'" aria-label="关闭补权重弹框" @click="closeWeightModal">
          <X class="h-4 w-4" />
        </button>
      </div>

      <div class="space-y-4 p-5">
        <div v-if="weightLookupState === 'loading'" class="alert alert-info">
          <span class="loading loading-spinner loading-sm"></span>
          <span>正在从爱站公开综合查询页获取权重、收录和备案性质。</span>
        </div>
        <div v-else-if="weightLookupState === 'success'" class="alert alert-success">
          <CheckCircle2 class="h-5 w-5" />
          <span>已获取权重数据；手动输入仅作为爱站获取失败时的补充。</span>
        </div>
        <div v-else-if="weightLookupState === 'failed'" class="alert alert-warning items-start">
          <AlertCircle class="mt-0.5 h-5 w-5" />
          <span>{{ weightLookupError || activeWeightSnapshot.error || '爱站获取失败，可以在下方手动补充。' }}</span>
        </div>

        <div class="rounded-box border border-base-300 bg-base-200/40 p-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="text-sm font-semibold">爱站返回结果</div>
              <div class="text-xs text-base-content/60">
                来源：{{ weightSourceLabel(activeWeightSnapshot.source) }}
                <a
                  v-if="activeWeightSnapshot.source_url"
                  class="link ml-2 inline-flex items-center gap-1"
                  :href="activeWeightSnapshot.source_url"
                  target="_blank"
                  rel="noreferrer"
                >
                  打开爱站
                  <ExternalLink class="h-3 w-3" />
                </a>
              </div>
            </div>
            <div class="badge badge-outline">{{ activeWeightSnapshot.status || '未查询' }}</div>
          </div>

          <div class="mt-4 grid gap-3 lg:grid-cols-[1fr_1fr]">
            <div>
              <div class="text-xs font-medium uppercase text-base-content/55">平台权重</div>
              <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div v-for="field in weightFields" :key="field.key" class="rounded-box border border-base-300 bg-base-100 px-3 py-2">
                  <div class="text-xs text-base-content/55">{{ field.label }}</div>
                  <div class="mt-1 font-semibold">{{ snapshotNumber(activeWeightSnapshot, field.key) }}</div>
                </div>
              </div>
            </div>

            <div>
              <div class="text-xs font-medium uppercase text-base-content/55">收录数据</div>
              <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <div v-for="field in indexedFields" :key="field.key" class="rounded-box border border-base-300 bg-base-100 px-3 py-2">
                  <div class="text-xs text-base-content/55">{{ field.label }}</div>
                  <div class="mt-1 font-semibold">{{ numberText(snapshotNumber(activeWeightSnapshot, field.key)) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="mt-4 grid gap-3 text-sm md:grid-cols-4">
            <div>
              <div class="text-xs text-base-content/55">网站性质</div>
              <div class="font-medium">{{ activeWeightSnapshot.site_nature || '-' }}</div>
            </div>
            <div>
              <div class="text-xs text-base-content/55">备案号</div>
              <div class="truncate font-medium">{{ activeWeightSnapshot.metadata?.icp_number || '-' }}</div>
            </div>
            <div>
              <div class="text-xs text-base-content/55">主体名称</div>
              <div class="truncate font-medium">{{ activeWeightSnapshot.metadata?.icp_company || '-' }}</div>
            </div>
            <div>
              <div class="text-xs text-base-content/55">审核时间</div>
              <div class="font-medium">{{ activeWeightSnapshot.metadata?.icp_passed_at || '-' }}</div>
            </div>
          </div>
        </div>

        <div v-if="manualFallbackVisible" class="rounded-box border border-warning/30 bg-warning/5 p-4">
          <div class="mb-3 flex items-center gap-2">
            <PencilLine class="h-4 w-4 text-warning" />
            <div>
              <div class="text-sm font-semibold">手动补充</div>
              <div class="text-xs text-base-content/60">仅在爱站获取失败或数据缺失时使用。</div>
            </div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label v-for="field in weightFields" :key="field.key" class="form-control">
              <span class="label-text">{{ field.label }}</span>
              <input
                :value="weightForm[field.key]"
                type="number"
                min="0"
                class="input input-bordered input-sm"
                :disabled="manualFallbackDisabled"
                @input="setNumberField(field.key, ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label v-for="field in indexedFields" :key="field.key" class="form-control">
              <span class="label-text">{{ field.label }}</span>
              <input
                :value="weightForm[field.key]"
                type="number"
                min="0"
                class="input input-bordered input-sm"
                :disabled="manualFallbackDisabled"
                @input="setNumberField(field.key, ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label class="form-control sm:col-span-2 lg:col-span-4">
              <span class="label-text">网站性质 / 备案主体</span>
              <input v-model.trim="weightForm.site_nature" class="input input-bordered input-sm" :disabled="manualFallbackDisabled" placeholder="例如：个人" />
            </label>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap justify-end gap-2 border-t border-base-300 p-5">
        <button class="btn btn-outline btn-sm" :disabled="weightLookupState === 'loading'" @click="lookupAizhanWeight">
          <RefreshCw class="h-4 w-4" />
          重新查询爱站
        </button>
        <button v-if="manualFallbackVisible" class="btn btn-warning btn-sm" :disabled="manualFallbackDisabled" @click="submitManualWeight">保存手动补充</button>
        <button class="btn btn-primary btn-sm" :disabled="weightLookupState === 'loading'" @click="closeWeightModal">完成</button>
      </div>
    </div>
    <div class="modal-backdrop bg-neutral/40" @click="closeWeightModal"></div>
  </div>
</template>
