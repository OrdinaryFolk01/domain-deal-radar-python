<script setup lang="ts">
import { Activity, BarChart3, Copy, Mail, RefreshCw, Save, Send, X } from '@lucide/vue';
import { computed, reactive, ref, watch } from 'vue';
import {
  analyzeLead,
  crawlLead,
  getEmailTemplate,
  getLead,
  getLeadProfile,
  listEmailLogs,
  listLeadActivities,
  patchLead,
  refreshHistory,
  refreshRegistration,
  sendLeadEmail,
} from '../api/radar';
import type { EmailLog, Lead, LeadActivity, LeadProfile } from '../api/types';
import { formatDateTime, numberText, splitPipe } from '../utils/format';
import StatusBadge from './StatusBadge.vue';

const props = defineProps<{ leadId: number | null }>();
const emit = defineEmits<{
  close: [];
  refresh: [];
  toast: [message: string, tone?: 'success' | 'error' | 'info'];
}>();

const lead = ref<Lead | null>(null);
const profile = ref<LeadProfile | null>(null);
const activities = ref<LeadActivity[]>([]);
const emails = ref<EmailLog[]>([]);
const busy = ref(false);
const sendingEmail = ref(false);
const form = reactive({
  emails: '',
  phones: '',
  wechats: '',
  qqs: '',
  contact_message: '',
  lead_status: 'NEW',
  next_action: '',
  contact_note: '',
  remark: '',
  give_up_reason: '',
  deal_price: 0,
  resell_price: 0,
});
const emailForm = reactive({
  to: '',
  subject: '',
});

const open = computed(() => props.leadId !== null);
const contacts = computed(() => (lead.value ? [form.emails, form.phones, form.wechats, form.qqs].flatMap((value) => splitPipe(value)) : []));
const weightSummary = computed(() => {
  if (!lead.value) return '-';
  const values = [
    lead.value.baidu_pc_weight,
    lead.value.baidu_mobile_weight,
    lead.value.sogou_weight,
    lead.value.so_weight,
    lead.value.sm_weight,
    lead.value.toutiao_weight,
    lead.value.bing_weight,
  ];
  return `最高 ${Math.max(...values)} / 百度 ${lead.value.baidu_pc_weight}-${lead.value.baidu_mobile_weight}`;
});
const indexSummary = computed(() => {
  if (!lead.value) return '-';
  const values = [
    lead.value.indexed_count,
    lead.value.sogou_indexed_count,
    lead.value.so_indexed_count,
    lead.value.sm_indexed_count,
    lead.value.toutiao_indexed_count,
    lead.value.bing_indexed_count,
  ];
  return numberText(Math.max(...values));
});

watch(
  () => props.leadId,
  async (id) => {
    if (id) await load(id);
  },
);

async function load(id: number) {
  busy.value = true;
  try {
    const [leadData, profileData, activityRows, emailRows, templateData] = await Promise.all([
      getLead(id),
      getLeadProfile(id),
      listLeadActivities(id),
      listEmailLogs(id),
      getEmailTemplate(id),
    ]);
    lead.value = leadData;
    profile.value = profileData;
    activities.value = activityRows;
    emails.value = emailRows;
    syncForm(leadData);
    emailForm.to = templateData.to || '';
    emailForm.subject = templateData.subject || '';
    form.contact_message = templateData.body || leadData.contact_message || '';
  } finally {
    busy.value = false;
  }
}

function normalizeContactField(value: string) {
  return (value || '')
    .replaceAll('；', '|')
    .replaceAll(';', '|')
    .replaceAll(',', '|')
    .replace(/\r?\n/g, '|')
    .split('|')
    .map((item) => item.trim())
    .filter(Boolean)
    .join(' | ');
}

function syncForm(leadData: Lead) {
  form.emails = leadData.emails || '';
  form.phones = leadData.phones || '';
  form.wechats = leadData.wechats || '';
  form.qqs = leadData.qqs || '';
  form.contact_message = leadData.contact_message || '';
  form.lead_status = leadData.lead_status;
  form.next_action = leadData.next_action || '';
  form.contact_note = leadData.contact_note || '';
  form.remark = leadData.remark || '';
  form.give_up_reason = leadData.give_up_reason || '';
  form.deal_price = leadData.deal_price || 0;
  form.resell_price = leadData.resell_price || 0;
}

async function save() {
  if (!lead.value) return;
  const payload = {
    ...form,
    emails: normalizeContactField(form.emails),
    phones: normalizeContactField(form.phones),
    wechats: normalizeContactField(form.wechats),
    qqs: normalizeContactField(form.qqs),
  } as Partial<Lead>;
  lead.value = await patchLead(lead.value.id, payload);
  syncForm(lead.value);
  emit('toast', '线索已保存', 'success');
  emit('refresh');
}

async function runAction(action: 'crawl' | 'analyze' | 'registration' | 'history') {
  if (!lead.value) return;
  busy.value = true;
  try {
    const actions = { crawl: crawlLead, analyze: analyzeLead, registration: refreshRegistration, history: refreshHistory };
    lead.value = await actions[action](lead.value.id);
    emit('toast', '操作已完成', 'success');
    emit('refresh');
    await load(lead.value.id);
  } finally {
    busy.value = false;
  }
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

async function copyMessage() {
  const message = form.contact_message.trim();
  if (!message) {
    emit('toast', '请先填写话术', 'error');
    return;
  }
  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(message);
    } else {
      fallbackCopyText(message);
    }
    emit('toast', '话术已复制', 'success');
  } catch {
    emit('toast', '话术复制失败', 'error');
  }
}

async function sendEmail() {
  if (!lead.value || sendingEmail.value) return;
  const to = emailForm.to.trim();
  const subject = emailForm.subject.trim();
  const body = form.contact_message.trim();
  if (!to) {
    emit('toast', '请先填写收件人邮箱', 'error');
    return;
  }
  if (!body) {
    emit('toast', '请先填写话术', 'error');
    return;
  }
  if (!window.confirm(`确认发送邮件给 ${to}？`)) return;

  sendingEmail.value = true;
  try {
    const result = await sendLeadEmail(lead.value.id, { to, subject, body });
    emit('toast', result.message || '邮件已发送', 'success');
    emit('refresh');
    await load(lead.value.id);
  } catch (error) {
    emit('toast', error instanceof Error ? error.message : '邮件发送失败', 'error');
  } finally {
    sendingEmail.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="drawer drawer-end z-50">
    <input type="checkbox" class="drawer-toggle" checked />
    <div class="drawer-side">
      <button class="drawer-overlay" aria-label="关闭详情" @click="emit('close')"></button>
      <aside class="min-h-full w-full max-w-5xl overflow-y-auto bg-base-100 p-4 shadow-2xl">
        <div class="top-0 z-10 -m-4 mb-4 border-b border-base-300 bg-base-100/95 p-4 backdrop-blur">
          <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div class="flex items-center gap-2">
                <h2 class="text-xl font-semibold">{{ lead?.domain || '线索详情' }}</h2>
                <StatusBadge v-if="lead" :value="lead.lead_status" />
              </div>
              <p class="mt-1 text-sm text-base-content/60">{{ lead?.title || '-' }}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="btn btn-outline btn-sm" :disabled="busy" @click="runAction('crawl')"><RefreshCw class="h-4 w-4" />抓取</button>
              <button class="btn btn-outline btn-sm" :disabled="busy" @click="runAction('analyze')"><BarChart3 class="h-4 w-4" />分析</button>
              <button class="btn btn-outline btn-sm" :disabled="busy" @click="runAction('registration')">注册</button>
              <button class="btn btn-outline btn-sm" :disabled="busy" @click="runAction('history')">历史</button>
              <button class="btn btn-primary btn-sm" :disabled="busy" @click="save"><Save class="h-4 w-4" />保存</button>
              <button class="btn btn-ghost btn-sm" @click="emit('close')"><X class="h-4 w-4" />关闭</button>
            </div>
          </div>
        </div>

        <div v-if="lead" class="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <section class="space-y-4">
            <div class="grid gap-3 md:grid-cols-4">
              <div class="rounded-box border border-base-300 p-3">
                <div class="text-xs text-base-content/55">雷达评分</div>
                <div class="text-2xl font-semibold">{{ lead.score }}</div>
              </div>
              <div class="rounded-box border border-base-300 p-3">
                <div class="text-xs text-base-content/55">可买性</div>
                <div class="text-lg font-semibold">{{ lead.buyability_grade }} / {{ lead.buyability_score }}</div>
              </div>
              <div class="rounded-box border border-base-300 p-3">
                <div class="text-xs text-base-content/55">历史画像</div>
                <div class="text-lg font-semibold">{{ lead.history_grade }} / {{ lead.history_score }}</div>
              </div>
              <div class="rounded-box border border-base-300 p-3">
                <div class="text-xs text-base-content/55">联系方式</div>
                <div class="text-lg font-semibold">{{ contacts.length || '待补' }}</div>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="font-semibold">基础信息</h3>
              <div class="mt-3 grid gap-2 text-sm md:grid-cols-2">
                <div>建议：{{ lead.suggestion || '-' }}</div>
                <div>性质/备案：{{ lead.icp_type || '-' }}</div>
                <div>权重：{{ weightSummary }}</div>
                <div>收录：{{ indexSummary }}</div>
                <div>抓取：{{ lead.crawl_status }} · {{ lead.crawl_pages_done }}/{{ lead.crawl_pages_total }} 页</div>
                <div>分析：{{ lead.analysis_status }} · {{ lead.site_health || '-' }}</div>
                <div class="grid gap-1 sm:grid-cols-[4rem_minmax(0,1fr)] md:col-span-2">
                  <span class="text-base-content/60">注册商：</span>
                  <span class="min-w-0 wrap-break-word">{{ lead.registrar_name || '-' }}</span>
                </div>
                <div>到期：{{ formatDateTime(lead.domain_expires_at) }}</div>
                <div class="md:col-span-2">联系方式：{{ contacts.join(' ｜ ') || '-' }}</div>
                <div class="md:col-span-2">风险：{{ lead.risk_flags || lead.enhanced_risk_flags || '无' }}</div>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="font-semibold">跟进编辑</h3>
              <div class="mt-3 grid gap-3 md:grid-cols-2">
                <div class="md:col-span-2 text-sm font-medium">联系方式</div>
                <label class="form-control">
                  <span class="label-text">邮箱</span>
                  <input v-model="form.emails" class="input input-bordered" placeholder="name@example.com" />
                </label>
                <label class="form-control">
                  <span class="label-text">电话</span>
                  <input v-model="form.phones" class="input input-bordered" placeholder="13800138000" />
                </label>
                <label class="form-control">
                  <span class="label-text">微信</span>
                  <input v-model="form.wechats" class="input input-bordered" />
                </label>
                <label class="form-control">
                  <span class="label-text">QQ</span>
                  <input v-model="form.qqs" class="input input-bordered" />
                </label>
                <div class="divider md:col-span-2 my-0"></div>
                <label class="form-control">
                  <span class="label-text">状态</span>
                  <select v-model="form.lead_status" class="select select-bordered">
                    <option value="NEW">新线索</option>
                    <option value="CHECKED">已检查</option>
                    <option value="CONTACTED">已联系</option>
                    <option value="REPLIED">已回复</option>
                    <option value="NEGOTIATING">谈价中</option>
                    <option value="BOUGHT">已买入</option>
                    <option value="RESOLD">已转卖</option>
                    <option value="GIVE_UP">已放弃</option>
                  </select>
                </label>
                <label class="form-control">
                  <span class="label-text">下一步</span>
                  <input v-model="form.next_action" class="input input-bordered" />
                </label>
                <label class="form-control">
                  <span class="label-text">成交价</span>
                  <input v-model.number="form.deal_price" type="number" class="input input-bordered" />
                </label>
                <label class="form-control">
                  <span class="label-text">转售价</span>
                  <input v-model.number="form.resell_price" type="number" class="input input-bordered" />
                </label>
                <label class="form-control ">
                  <span class="label-text">跟进记录</span>
                  <textarea v-model="form.contact_note" class="textarea textarea-bordered "></textarea>
                </label>
                <label class="form-control ">
                  <span class="label-text">备注</span>
                  <textarea v-model="form.remark" class="textarea textarea-bordered "></textarea>
                </label>
              </div>
            </div>
          </section>

          <section class="space-y-4">
            <div class="rounded-box border border-base-300 p-4">
              <h3 class="flex items-center gap-2 font-semibold"><Activity class="h-4 w-4 text-primary" />线索画像</h3>
              <p class="mt-2 text-sm">{{ profile?.recommended_action || '-' }}</p>
              <div class="mt-3 flex flex-wrap gap-2">
                <span
                  v-for="signal in profile?.signals || []"
                  :key="signal"
                  class="max-w-full wrap-break-word rounded-btn border border-base-300 px-2 py-1 text-xs leading-relaxed text-base-content/70"
                >
                  {{ signal }}
                </span>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="flex items-center gap-2 font-semibold"><Mail class="h-4 w-4 text-primary" />联系话术 / 邮件</h3>
              <div class="mt-3 space-y-3 flex flex-col">
                <label class="form-control flex justify-between items-center ">
                  <span class="label-text">收件人</span>
                  <input v-model="emailForm.to" class="input input-bordered ml-auto"  placeholder="name@example.com" />
                </label>
                <label class="form-control flex justify-between items-center ">
                  <span class="label-text">邮件主题</span>
                  <input v-model="emailForm.subject" class="input input-bordered" />
                </label>
                <label class="form-control">
                  <span class="label-text">话术 / 邮件正文</span>
                  <textarea v-model="form.contact_message" class="textarea textarea-bordered min-h-40 w-full"></textarea>
                </label>
                <div class="flex flex-wrap gap-2">
                  <button class="btn btn-outline btn-sm" type="button" @click="copyMessage">
                    <Copy class="h-4 w-4" />
                    复制话术
                  </button>
                  <button class="btn btn-primary btn-sm" type="button" :disabled="sendingEmail" @click="sendEmail">
                    <Send class="h-4 w-4" />
                    {{ sendingEmail ? '发送中' : '发送邮件' }}
                  </button>
                </div>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="font-semibold">评分拆解</h3>
              <div class="mt-3 space-y-2">
                <div v-if="!profile?.score_breakdown?.length" class="text-sm text-base-content/55">暂无评分拆解。</div>
                <div v-for="item in profile?.score_breakdown || []" :key="`${item.category}-${item.label}`" class="flex items-start justify-between gap-3 rounded-btn bg-base-200 p-2 text-sm">
                  <div>
                    <div class="font-medium">{{ item.label }}</div>
                    <div class="text-xs text-base-content/55">{{ item.reason }}</div>
                  </div>
                  <span class="font-semibold" :class="item.points >= 0 ? 'text-success' : 'text-error'">{{ item.points > 0 ? '+' : '' }}{{ item.points }}</span>
                </div>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="flex items-center gap-2 font-semibold"><Mail class="h-4 w-4 text-primary" />邮件记录</h3>
              <div class="mt-3 space-y-2">
                <div v-if="!emails.length" class="text-sm text-base-content/55">暂无邮件记录。</div>
                <div v-for="email in emails" :key="email.id" class="rounded-btn bg-base-200 p-2 text-sm">
                  <div class="font-medium">{{ email.to_email || '-' }}</div>
                  <div class="truncate text-xs text-base-content/55">{{ email.subject || '-' }}</div>
                  <div class="text-xs text-base-content/55">{{ email.status }} · {{ formatDateTime(email.sent_at || email.created_at) }}</div>
                </div>
              </div>
            </div>

            <div class="rounded-box border border-base-300 p-4">
              <h3 class="font-semibold">活动时间线</h3>
              <div class="mt-3 space-y-2">
                <div v-if="!activities.length" class="text-sm text-base-content/55">暂无活动记录。</div>
                <div v-for="activity in activities" :key="activity.id" class="rounded-btn bg-base-200 p-2 text-sm">
                  <div class="font-medium">{{ activity.title || activity.event_type }}</div>
                  <div class="text-xs text-base-content/55">{{ activity.detail || '-' }}</div>
                  <div class="text-xs text-base-content/45">{{ formatDateTime(activity.created_at) }}</div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </aside>
    </div>
  </div>
</template>
