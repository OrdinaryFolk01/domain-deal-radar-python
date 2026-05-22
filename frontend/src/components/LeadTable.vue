<script setup lang="ts">
import { Eye, RefreshCw } from '@lucide/vue';
import type { Lead } from '../api/types';
import { numberText, splitPipe } from '../utils/format';
import StatusBadge from './StatusBadge.vue';

interface LeadTableFilters {
  keyword: string;
  status: string;
  crawl_status: string;
  risk: string;
  min_score: string;
}

defineProps<{
  leads: Lead[];
  filters: LeadTableFilters;
}>();

const emit = defineEmits<{
  refresh: [];
  openLead: [id: number];
  updateFilters: [filters: LeadTableFilters];
}>();

const leadStatusText: Record<string, string> = {
  NEW: '新线索',
  CHECKED: '已检查',
  CONTACTED: '已联系',
  REPLIED: '已回复',
  NEGOTIATING: '谈价中',
  BOUGHT: '已买入',
  RESOLD: '已转卖',
  GIVE_UP: '已放弃',
};

function patchFilter(filters: LeadTableFilters, key: keyof LeadTableFilters, value: string) {
  emit('updateFilters', { ...filters, [key]: value });
}

function weightSummary(lead: Lead) {
  const values = [lead.baidu_pc_weight, lead.baidu_mobile_weight, lead.sogou_weight, lead.so_weight, lead.sm_weight, lead.toutiao_weight, lead.bing_weight];
  return `最高 ${Math.max(...values)} / 百度 ${lead.baidu_pc_weight}-${lead.baidu_mobile_weight}`;
}

function indexSummary(lead: Lead) {
  const values = [lead.indexed_count, lead.sogou_indexed_count, lead.so_indexed_count, lead.sm_indexed_count, lead.toutiao_indexed_count, lead.bing_indexed_count];
  return numberText(Math.max(...values));
}

function contactSummary(lead: Lead) {
  const total = splitPipe(lead.emails).length + splitPipe(lead.phones).length + splitPipe(lead.wechats).length + splitPipe(lead.qqs).length;
  return total ? `${total} 条` : '待补';
}

function scoreTone(score: number) {
  if (score >= 85) return 'success';
  if (score >= 65) return 'info';
  if (score >= 45) return 'warning';
  return 'neutral';
}

</script>

<template>
  <section class="rounded-box border border-base-300 bg-base-100 shadow-sm">
    <div class="flex flex-col gap-3 border-b border-base-300 p-4 xl:flex-row xl:items-center xl:justify-between">
      <div>
        <h2 class="text-base font-semibold">正式线索库</h2>
        <p class="text-sm text-base-content/60">只放已经值得继续跟进的站点，批量尽调和触达都从这里开始。</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <input
          :value="filters.keyword"
          class="input input-bordered input-sm w-56"
          placeholder="搜索域名 / 标题 / 备注"
          @input="patchFilter(filters, 'keyword', ($event.target as HTMLInputElement).value)"
          @keydown.enter="emit('refresh')"
        />
        <select :value="filters.status" class="select select-bordered select-sm w-36" @change="patchFilter(filters, 'status', ($event.target as HTMLSelectElement).value)">
          <option value="">全部状态</option>
          <option value="NEW">新线索</option>
          <option value="CONTACTED">已联系</option>
          <option value="NEGOTIATING">谈价中</option>
          <option value="BOUGHT">已买入</option>
          <option value="GIVE_UP">已放弃</option>
        </select>
        <select :value="filters.crawl_status" class="select select-bordered select-sm w-36" @change="patchFilter(filters, 'crawl_status', ($event.target as HTMLSelectElement).value)">
          <option value="">抓取不限</option>
          <option value="PENDING">待抓取</option>
          <option value="SUCCESS">抓取成功</option>
          <option value="FAILED">抓取失败</option>
        </select>
        <input
          :value="filters.min_score"
          type="number"
          min="0"
          class="input input-bordered input-sm w-28"
          placeholder="最低分"
          @input="patchFilter(filters, 'min_score', ($event.target as HTMLInputElement).value)"
        />
        <button class="btn btn-outline btn-sm" @click="emit('refresh')">
          <RefreshCw class="h-4 w-4" />
          刷新
        </button>
      </div>
    </div>
    <div class="overflow-x-auto">
      <table class="table table-zebra table-sm min-w-315">
        <thead>
          <tr>
            <th>域名</th>
            <th>权重/收录</th>
            <th>备案</th>
            <th>评分</th>
            <th>报价</th>
            <th>联系方式/抓取</th>
            <th>风险</th>
            <th>跟进</th>
            <th class="w-28">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!leads.length">
            <td colspan="9" class="py-8 text-center text-base-content/55">暂无正式线索。</td>
          </tr>
          <tr v-for="lead in leads" :key="lead.id">
            <td>
              <a class="link-hover font-semibold text-primary" :href="lead.final_url || `https://${lead.domain}`" target="_blank" rel="noreferrer">{{ lead.domain }}</a>
              <div class="max-w-xs truncate text-xs text-base-content/55">{{ lead.title || '-' }}</div>
              <div class="text-xs text-base-content/45">{{ lead.source_provider || '-' }}</div>
            </td>
            <td>
              <div>{{ weightSummary(lead) }}</div>
              <div class="text-xs text-base-content/55">收录 {{ indexSummary(lead) }}</div>
            </td>
            <td>{{ lead.icp_type || '-' }}</td>
            <td>
              <StatusBadge :value="String(lead.score)" :label="String(lead.score)" :tone="scoreTone(lead.score)" />
              <div class="mt-1 text-xs text-base-content/55">可买 {{ lead.buyability_grade }} / {{ lead.buyability_score }}</div>
              <div class="text-xs text-base-content/55">历史 {{ lead.history_grade }} / {{ lead.history_score }}</div>
            </td>
            <td>
              <div>首报 {{ numberText(lead.first_offer) }}</div>
              <div class="text-xs text-base-content/55">最高 {{ numberText(lead.max_offer) }}</div>
            </td>
            <td>
              <div>{{ contactSummary(lead) }}</div>
              <div class="text-xs text-base-content/55">{{ lead.crawl_status }} / {{ lead.analysis_status }}</div>
              <div class="text-xs text-base-content/55">{{ lead.crawl_pages_done }}/{{ lead.crawl_pages_total }} 页 · {{ lead.site_health || '未分析' }}</div>
            </td>
            <td>
              <StatusBadge :value="lead.risk_flags ? 'risk' : 'ok'" :label="lead.risk_flags ? '有风险' : '无风险'" :tone="lead.risk_flags ? 'error' : 'success'" />
              <div class="mt-1 max-w-48 truncate text-xs text-base-content/55">{{ lead.risk_flags || lead.enhanced_risk_flags || '-' }}</div>
            </td>
            <td>
              <StatusBadge :value="lead.lead_status" :label="leadStatusText[lead.lead_status] || lead.lead_status" />
              <div class="mt-1 max-w-44 truncate text-xs text-base-content/55">{{ lead.next_action || lead.suggestion || '-' }}</div>
            </td>
            <td>
              <button class="btn btn-primary btn-xs" @click="emit('openLead', lead.id)">
                <Eye class="h-3.5 w-3.5" />
                详情
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
