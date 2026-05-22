const statusMap = {
  NEW: '新线索',
  CHECKED: '已检查',
  CONTACTED: '已联系',
  REPLIED: '已回复',
  NEGOTIATING: '谈价中',
  BOUGHT: '已买入',
  RESOLD: '已转卖',
  GIVE_UP: '已放弃',
};

const crawlStatusMap = {
  PENDING: '待抓取',
  RUNNING: '抓取中',
  SUCCESS: '抓取成功',
  FAILED: '抓取失败',
  SKIPPED: '已跳过',
};

const analysisStatusMap = {
  PENDING: '待分析',
  RUNNING: '分析中',
  SUCCESS: '分析成功',
  SUCCESS_WITH_WARNINGS: '有警告',
  FAILED: '分析失败',
};

const candidateStatusMap = {
  DISCOVERED: '已发现',
  REJECTED: '已淘汰',
  NEED_WEIGHT: '待补权重',
  NEED_SITE_INDEX: '待补索引',
  QUALIFIED: '已合格',
  PROMOTED: '已入库',
};

let leads = [];
let tasks = [];
let discoveryTasks = [];
let candidates = [];
let currentLead = null;
let providers = [];
let searchEngines = [];
let currentEmailLogs = [];
let currentActivities = [];
let currentProfile = null;

const $ = (selector) => document.querySelector(selector);

function parseDateTime(value) {
  if (!value) return null;
  const normalized = String(value).trim().replace(' ', 'T');
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  if (!value) return '-';
  const text = String(value).trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (match) {
    const [, year, month, day, hour = '00', minute = '00', second = '00'] = match;
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
  }
  const date = parseDateTime(text);
  if (!date) return text;
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.style.display = 'block';
  setTimeout(() => {
    el.style.display = 'none';
  }, 2600);
}

function getFilters() {
  return {
    keyword: $('#keyword').value.trim(),
    status: $('#statusFilter').value,
    crawl_status: $('#crawlStatusFilter').value,
    risk: $('#riskFilter').value,
    min_score: $('#minScore').value,
  };
}

function buildQuery(params) {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') qs.set(key, value);
  }
  return qs.toString();
}

function parseJsonField(value, fallback) {
  try {
    const parsed = JSON.parse(value || '');
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    let message = text || `请求失败：${res.status}`;
    try {
      const data = JSON.parse(text);
      message = data.detail || data.message || message;
    } catch {
      // keep raw text
    }
    throw new Error(message);
  }
  return await res.json();
}

async function loadProviders() {
  providers = await apiJson('/api/providers');
  const select = $('#providerSelect');
  if (!select) return;
  select.innerHTML = providers
    .map((provider) => {
      const selected = provider.provider_id === 'aizhan_rank_manual_csv' ? ' selected' : '';
      return `<option value="${escapeHtml(provider.provider_id)}"${selected}>${escapeHtml(provider.name)}</option>`;
    })
    .join('');
}

async function loadSearchEngines() {
  searchEngines = await apiJson('/api/search-engines');
  const select = $('#radarSearchEngines');
  if (!select) return;
  select.innerHTML = searchEngines
    .map((engine) => `<option value="${escapeHtml(engine.provider_id)}" selected>${escapeHtml(engine.name)}</option>`)
    .join('');
}

async function loadLeads() {
  const qs = buildQuery(getFilters());
  leads = await apiJson(`/api/leads?${qs}`);
  renderStats();
  renderTable();
}

async function loadTasks() {
  tasks = await apiJson('/api/crawl/tasks?limit=30');
  renderTasks();
}

async function loadDiscoveryTasks() {
  discoveryTasks = await apiJson('/api/discovery/tasks?limit=30');
  renderDiscoveryTasks();
}

async function loadCandidates() {
  const qs = buildQuery({
    status: $('#candidateStatusFilter') ? $('#candidateStatusFilter').value : '',
    keyword: $('#candidateKeyword') ? $('#candidateKeyword').value.trim() : '',
    limit: 100,
  });
  candidates = await apiJson(`/api/candidates?${qs}`);
  renderCandidates();
}

function renderStats() {
  $('#statTotal').textContent = leads.length;
  $('#statHigh').textContent = leads.filter((item) => item.score >= 85).length;
  $('#statCrawlSuccess').textContent = leads.filter((item) => item.crawl_status === 'SUCCESS').length;
  $('#statFollowUpDue').textContent = leads.filter((item) => {
    const date = parseDateTime(item.next_follow_up_at);
    return date && date.getTime() <= Date.now();
  }).length;
  $('#statBought').textContent = leads.filter((item) => item.lead_status === 'BOUGHT').length;
  $('#statGiveUp').textContent = leads.filter((item) => item.lead_status === 'GIVE_UP').length;
}

function riskBadge(lead) {
  if (lead.risk_flags) return `<span class="badge risk">${escapeHtml(lead.risk_flags)}</span>`;
  return '<span class="badge good">无风险标记</span>';
}

function scoreBadge(score) {
  const cls = score >= 85 ? 'good' : score >= 65 ? 'warn' : '';
  return `<span class="badge ${cls}">${score}</span>`;
}

function crawlBadge(status) {
  const cls = status === 'SUCCESS' ? 'good' : status === 'FAILED' ? 'risk' : status === 'RUNNING' ? 'warn' : '';
  return `<span class="badge ${cls}">${crawlStatusMap[status] || status || '待抓取'}</span>`;
}

function analysisBadge(status) {
  const cls = status === 'SUCCESS' ? 'good' : status === 'FAILED' ? 'risk' : status === 'RUNNING' || status === 'SUCCESS_WITH_WARNINGS' ? 'warn' : '';
  return `<span class="badge ${cls}">${analysisStatusMap[status] || status || '待分析'}</span>`;
}

function contactSummary(lead) {
  const parts = [];
  if (lead.emails) parts.push(`邮箱 ${lead.emails.split('|').length}`);
  if (lead.phones) parts.push(`手机 ${lead.phones.split('|').length}`);
  if (lead.wechats) parts.push(`微信 ${lead.wechats.split('|').length}`);
  if (lead.qqs) parts.push(`QQ ${lead.qqs.split('|').length}`);
  return parts.length ? parts.join(' / ') : '暂无联系方式';
}

function followUpSummary(lead) {
  if (!lead.next_follow_up_at) return '未安排跟进';
  const due = parseDateTime(lead.next_follow_up_at);
  const overdue = due && due.getTime() <= Date.now();
  return `${overdue ? '待跟进' : '下次跟进'} ${escapeHtml(formatDateTime(lead.next_follow_up_at))}`;
}

function toDateTimeLocal(value) {
  if (!value) return '';
  return String(value).replace(' ', 'T').slice(0, 16);
}

function platformWeightSummary(lead) {
  const items = [
    ['百度PC', lead.baidu_pc_weight],
    ['百度移动', lead.baidu_mobile_weight],
    ['搜狗', lead.sogou_weight],
    ['360', lead.so_weight],
    ['神马', lead.sm_weight],
    ['头条', lead.toutiao_weight],
    ['必应', lead.bing_weight],
  ].filter(([, value]) => Number(value || 0) > 0);
  return items.length ? items.map(([name, value]) => `${name} ${value}`).join(' / ') : '暂无权重';
}

function platformIndexSummary(lead) {
  const items = [
    ['百度', lead.indexed_count],
    ['搜狗', lead.sogou_indexed_count],
    ['360', lead.so_indexed_count],
    ['神马', lead.sm_indexed_count],
    ['头条', lead.toutiao_indexed_count],
    ['必应', lead.bing_indexed_count],
  ].filter(([, value]) => Number(value || 0) > 0);
  return items.length ? items.map(([name, value]) => `${name} ${value}`).join(' / ') : '暂无收录';
}

function renderTable() {
  const tbody = $('#leadRows');
  if (!leads.length) {
    tbody.innerHTML = '<tr><td colspan="11" class="muted">暂无数据，请导入 CSV 或手动新增域名。</td></tr>';
    return;
  }

  tbody.innerHTML = leads
    .map((lead) => {
      return `
        <tr>
          <td class="domain-cell">
            <strong><a class="domain-link" href="${escapeHtml(buildSiteUrl(lead))}" target="_blank" rel="noopener noreferrer">${escapeHtml(lead.domain)}</a></strong>
            <div class="muted">${escapeHtml(lead.suffix || '-')} · ${escapeHtml(lead.source_provider || '无来源')}</div>
            <div class="muted ellipsis">${escapeHtml(lead.final_url || '-')}</div>
          </td>
          <td>
            ${escapeHtml(lead.title || '-')}
            <div class="muted">${escapeHtml(lead.suggestion || '-')}</div>
          </td>
          <td class="compact-cell">${escapeHtml(platformWeightSummary(lead))}</td>
          <td class="compact-cell">${escapeHtml(platformIndexSummary(lead))}</td>
          <td>${escapeHtml(lead.icp_type || '-')}</td>
          <td>
            ${scoreBadge(lead.score)}
            <div class="muted">可买性 ${escapeHtml(lead.buyability_grade || 'UNKNOWN')} / ${lead.buyability_score || 0}</div>
            <div class="muted">历史 ${escapeHtml(lead.history_grade || 'UNKNOWN')} / ${lead.history_score || 0}</div>
          </td>
          <td>
            <div>首报：${lead.first_offer} 元</div>
            <div class="muted">最高：${lead.max_offer} 元</div>
          </td>
          <td>
            <div>${escapeHtml(contactSummary(lead))}</div>
            <div>${crawlBadge(lead.crawl_status)} ${analysisBadge(lead.analysis_status)}</div>
            <div class="muted">抓取 ${lead.crawl_pages_done || 0}/${lead.crawl_pages_total || 0} 页 ｜ ${escapeHtml(lead.site_health || '未分析')}</div>
          </td>
          <td>${riskBadge(lead)}</td>
          <td>
            <span class="badge">${statusMap[lead.lead_status] || lead.lead_status}</span>
            <div class="muted">${followUpSummary(lead)}</div>
          </td>
          <td>
            <div class="row-actions">
              <button onclick="openDetail(${lead.id})">详情</button>
              <button onclick="copyMessage(${lead.id})">话术</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');
}

function renderTasks() {
  const tbody = $('#taskRows');
  if (!tasks.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">暂无抓取任务。</td></tr>';
    return;
  }
  tbody.innerHTML = tasks
    .map((task) => {
      return `
        <tr>
          <td>${escapeHtml(task.batch_id || '-')}</td>
          <td>${escapeHtml(task.domain || '-')}</td>
          <td>${crawlBadge(task.status)}</td>
          <td>${task.pages_done || 0}/${task.pages_total || 0}</td>
          <td class="muted ellipsis">${escapeHtml(task.error_message || '-')}</td>
          <td class="muted">${escapeHtml(formatDateTime(task.finished_at || task.started_at || task.created_at))}</td>
        </tr>
      `;
    })
    .join('');
}


function renderDiscoveryTasks() {
  const tbody = $('#discoveryTaskRows');
  if (!tbody) return;
  if (!discoveryTasks.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">暂无发现任务。</td></tr>';
    return;
  }
  tbody.innerHTML = discoveryTasks
    .map((task) => {
      const cls = task.status === 'SUCCESS' ? 'good' : task.status === 'FAILED' ? 'risk' : 'warn';
      return `
        <tr>
          <td>${escapeHtml(task.provider_id || '-')}</td>
          <td>${escapeHtml(task.source_type || '-')}</td>
          <td><span class="badge ${cls}">${escapeHtml(task.status || '-')}</span></td>
          <td>${task.created_count || 0}/${task.updated_count || 0}</td>
          <td class="muted ellipsis">${escapeHtml(task.keyword || '-')}</td>
          <td class="muted">${escapeHtml(formatDateTime(task.finished_at || task.started_at || task.created_at))}</td>
        </tr>
      `;
    })
    .join('');
}

function candidateStatusBadge(status) {
  const cls = status === 'QUALIFIED' || status === 'PROMOTED' ? 'good' : status === 'REJECTED' ? 'risk' : 'warn';
  return `<span class="badge ${cls}">${candidateStatusMap[status] || status}</span>`;
}

function candidateSiteIndexSummary(candidate) {
  const snapshot = parseJsonField(candidate.site_index_snapshot, {});
  const results = Array.isArray(snapshot.results) ? snapshot.results : [];
  if (!results.length) return '-';
  return results
    .map((item) => {
      const count = Number.isInteger(item.count) ? item.count.toLocaleString() : '异常';
      return `${item.engine}:${count}`;
    })
    .join(' / ');
}

function candidateWeightSummary(candidate) {
  const snapshot = parseJsonField(candidate.weight_snapshot, {});
  const weights = snapshot.weights || {};
  const values = ['baidu_pc_weight', 'baidu_mobile_weight', 'sogou_weight', 'so_weight', 'sm_weight', 'toutiao_weight', 'bing_weight']
    .map((key) => Number(weights[key] || 0));
  const maxWeight = values.length ? Math.max(...values) : 0;
  const nature = snapshot.site_nature || '-';
  if (!snapshot.status) return '-';
  return `最高 ${maxWeight} / ${nature}`;
}

function candidateIntelSummary(candidate) {
  const whois = parseJsonField(candidate.whois_snapshot, {});
  const ip = parseJsonField(candidate.ip_snapshot, {});
  const whoisResults = Array.isArray(whois.results) ? whois.results : [];
  const registrar = whoisResults.find((item) => item.registrar)?.registrar || '-';
  const isp = ip.isp || ip.org || '-';
  const domestic = ip.is_domestic ? '国内' : ip.country || '';
  return `${registrar} / ${isp}${domestic ? ` / ${domestic}` : ''}`;
}

function renderCandidates() {
  const tbody = $('#candidateRows');
  if (!tbody) return;
  if (!candidates.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">暂无候选，请先执行雷达搜索。</td></tr>';
    return;
  }
  tbody.innerHTML = candidates
    .map((candidate) => {
      const sourceEngines = parseJsonField(candidate.search_engines, []);
      const keywords = parseJsonField(candidate.keywords, []);
      return `
        <tr>
          <td class="domain-cell">
            <strong><a class="domain-link" href="https://${escapeHtml(candidate.domain)}" target="_blank" rel="noopener noreferrer">${escapeHtml(candidate.domain)}</a></strong>
            <div class="muted ellipsis">${escapeHtml(candidate.title || '-')}</div>
          </td>
          <td>
            <div>${escapeHtml(sourceEngines.join(' / ') || candidate.search_engine || '-')}</div>
            <div class="muted ellipsis">${escapeHtml(keywords.join('，') || candidate.keyword || '-')}</div>
          </td>
          <td>${candidateStatusBadge(candidate.status)}<div class="muted">优先级 ${candidate.priority_score || 0}</div></td>
          <td>${escapeHtml(candidateSiteIndexSummary(candidate))}</td>
          <td>${escapeHtml(candidateWeightSummary(candidate))}</td>
          <td class="muted ellipsis">${escapeHtml(candidateIntelSummary(candidate))}</td>
          <td class="muted ellipsis">${escapeHtml(candidate.reject_reason || '-')}</td>
          <td>
            <div class="row-actions">
              <button onclick="qualifyCandidate(${candidate.id})">预筛</button>
              <button onclick="fillCandidateWeight(${candidate.id})">补权重</button>
              <button onclick="refreshCandidateIntel(${candidate.id})">情报</button>
              <button onclick="promoteCandidate(${candidate.id})">入库</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join('');
}

async function loadCrawlLogs(leadId) {
  const logs = await apiJson(`/api/leads/${leadId}/crawl/logs?limit=30`);
  const box = $('#crawlLogs');
  if (!logs.length) {
    box.innerHTML = '<div class="muted">暂无日志</div>';
    return;
  }
  box.innerHTML = logs
    .map((log) => {
      const contact = [log.emails, log.phones, log.wechats, log.qqs].filter(Boolean).join(' ｜ ');
      return `
        <div class="log-item">
          <div><strong>${escapeHtml(log.status_code || '-')}</strong> ${escapeHtml(log.url || '-')}</div>
          <div class="muted ellipsis">最终：${escapeHtml(log.final_url || '-')}</div>
          <div class="muted">标题：${escapeHtml(log.title || '-')}</div>
          <div class="muted">联系方式：${escapeHtml(contact || '-')}</div>
          ${log.error_message ? `<div class="muted risk-text">错误：${escapeHtml(log.error_message)}</div>` : ''}
        </div>
      `;
    })
    .join('');
}

async function loadEmailLogs(leadId) {
  currentEmailLogs = await apiJson(`/api/leads/${leadId}/email-logs?limit=20`);
  const box = $('#emailLogs');
  if (!box) return;
  if (!currentEmailLogs.length) {
    box.innerHTML = '<div class="muted">暂无邮件记录</div>';
    return;
  }
  box.innerHTML = currentEmailLogs
    .map((log) => {
      const cls = log.status === 'SENT' ? 'good' : log.status === 'FAILED' ? 'risk' : 'warn';
      return `
        <div class="log-item">
          <div><span class="badge ${cls}">${escapeHtml(log.status)}</span> ${escapeHtml(log.to_email || '-')}</div>
          <div class="muted ellipsis">主题：${escapeHtml(log.subject || '-')}</div>
          <div class="muted">时间：${escapeHtml(formatDateTime(log.sent_at || log.created_at))}</div>
          ${log.error_message ? `<div class="muted risk-text">错误：${escapeHtml(log.error_message)}</div>` : ''}
        </div>
      `;
    })
    .join('');
}

async function loadActivities(leadId) {
  currentActivities = await apiJson(`/api/leads/${leadId}/activities?limit=30`);
  const box = $('#activityLogs');
  if (!box) return;
  if (!currentActivities.length) {
    box.innerHTML = '<div class="muted">暂无跟进记录</div>';
    return;
  }
  box.innerHTML = currentActivities
    .map((item) => `
      <div class="log-item">
        <div><strong>${escapeHtml(item.title || item.event_type)}</strong></div>
        <div class="muted">${escapeHtml(item.detail || '-')}</div>
        <div class="muted">${escapeHtml(formatDateTime(item.created_at))}</div>
      </div>
    `)
    .join('');
}

function renderProfile(profile) {
  const box = $('#profileInfo');
  const breakdownBox = $('#scoreBreakdown');
  if (!box || !breakdownBox) return;

  const riskText = profile.risk_level === 'HIGH' ? '高' : profile.risk_level === 'MEDIUM' ? '中' : '低';
  const contactText = profile.contactability === 'READY' ? '可触达' : '待补联系方式';
  const followText = profile.follow_up_state === 'DUE' ? '已到期' : profile.follow_up_state === 'SCHEDULED' ? '已安排' : '未安排';
  const buyability = profile.buyability || {};
  const buyabilityText = buyability.grade ? `${buyability.grade} / ${buyability.score || 0}` : 'UNKNOWN / 0';
  const buyabilityReasons = (buyability.reasons || []).length ? buyability.reasons.join(' ｜ ') : '暂无注册情报';
  const history = profile.history || {};
  const historyText = history.grade ? `${history.grade} / ${history.score || 0}` : 'UNKNOWN / 0';
  const historyReasons = (history.reasons || []).length ? history.reasons.join(' ｜ ') : '暂无历史画像';
  const signals = (profile.signals || []).length ? profile.signals.join(' ｜ ') : '暂无补充信号';

  box.innerHTML = `
    <div class="profile-item"><span>雷达等级</span><strong>${escapeHtml(profile.radar_grade || '-')}</strong></div>
    <div class="profile-item"><span>风险等级</span><strong>${escapeHtml(riskText)}</strong></div>
    <div class="profile-item"><span>触达状态</span><strong>${escapeHtml(contactText)}</strong></div>
    <div class="profile-item"><span>跟进状态</span><strong>${escapeHtml(followText)}</strong></div>
    <div class="profile-item"><span>可买性</span><strong>${escapeHtml(buyabilityText)}</strong></div>
    <div class="profile-item"><span>历史画像</span><strong>${escapeHtml(historyText)}</strong></div>
    <div class="profile-item" style="grid-column: 1 / -1;"><span>建议动作</span><strong>${escapeHtml(profile.recommended_action || '-')}</strong></div>
    <div class="profile-item" style="grid-column: 1 / -1;"><span>可买性理由</span><strong>${escapeHtml(buyabilityReasons)}</strong></div>
    <div class="profile-item" style="grid-column: 1 / -1;"><span>历史理由</span><strong>${escapeHtml(historyReasons)}</strong></div>
    <div class="profile-item" style="grid-column: 1 / -1;"><span>补充信号</span><strong>${escapeHtml(signals)}</strong></div>
  `;

  const breakdown = profile.score_breakdown || [];
  if (!breakdown.length) {
    breakdownBox.innerHTML = '<div class="muted">暂无评分拆解，重新评分后会生成。</div>';
    return;
  }
  breakdownBox.innerHTML = breakdown
    .map((item) => {
      const points = Number(item.points || 0);
      const cls = points >= 0 ? 'plus' : 'minus';
      const prefix = points > 0 ? '+' : '';
      return `
        <div class="breakdown-item">
          <span class="muted">${escapeHtml(item.category || '-')}</span>
          <strong>${escapeHtml(item.label || '-')}</strong>
          <strong class="points ${cls}">${prefix}${escapeHtml(points)}</strong>
          <span class="muted">${escapeHtml(item.reason || '-')}</span>
        </div>
      `;
    })
    .join('');
}

async function loadProfile(leadId) {
  currentProfile = await apiJson(`/api/leads/${leadId}/profile`);
  renderProfile(currentProfile);
}

function renderLeadDetailInfo(lead) {
  const archiveSnapshotLabel = Number(lead.archive_snapshot_count || 0) >= 100 ? '100+' : lead.archive_snapshot_count || 0;
  $('#detailInfo').innerHTML = `
    <div><strong>建议：</strong>${escapeHtml(lead.suggestion || '-')}</div>
    <div><strong>平台权重：</strong>${escapeHtml(platformWeightSummary(lead))}</div>
    <div><strong>平台收录：</strong>${escapeHtml(platformIndexSummary(lead))}</div>
    <div><strong>联系方式：</strong>邮箱 ${escapeHtml(lead.emails || '-')} ｜ 手机 ${escapeHtml(lead.phones || '-')} ｜ 微信 ${escapeHtml(lead.wechats || '-')} ｜ QQ ${escapeHtml(lead.qqs || '-')}</div>
    <div><strong>抓取：</strong>${crawlStatusMap[lead.crawl_status] || lead.crawl_status || '-'} ｜ ${lead.crawl_pages_done || 0}/${lead.crawl_pages_total || 0} 页 ｜ ${escapeHtml(formatDateTime(lead.last_crawled_at))}</div>
    <div><strong>增强分析：</strong>${analysisStatusMap[lead.analysis_status] || lead.analysis_status || '-'} ｜ DNS ${lead.dns_resolved ? '已解析' : '未解析'} ｜ SSL ${escapeHtml(lead.ssl_status || '-')} ${lead.ssl_days_left ? `(${lead.ssl_days_left} 天)` : ''} ｜ 健康度 ${escapeHtml(lead.site_health || '-')}</div>
    <div><strong>备案号：</strong>${escapeHtml(lead.icp_number || '-')} ｜ ${escapeHtml(lead.public_security_record || '-')}</div>
    <div><strong>注册情报：</strong>${escapeHtml(lead.registration_status || 'UNCHECKED')} ｜ ${escapeHtml(lead.registrar_name || '-')} ｜ 到期 ${escapeHtml(formatDateTime(lead.domain_expires_at))} ｜ 剩余 ${lead.days_until_expiry || 0} 天</div>
    <div><strong>可买性：</strong>${escapeHtml(lead.buyability_grade || 'UNKNOWN')} / ${lead.buyability_score || 0} ｜ ${escapeHtml(lead.rdap_status || '-')}</div>
    <div><strong>历史画像：</strong>${escapeHtml(lead.history_grade || 'UNKNOWN')} / ${lead.history_score || 0} ｜ 首次 ${escapeHtml(formatDateTime(lead.archive_first_seen_at))} ｜ 最近 ${escapeHtml(formatDateTime(lead.archive_last_seen_at))} ｜ 快照 ${archiveSnapshotLabel} 天</div>
    <div><strong>解析 IP：</strong>${escapeHtml(lead.resolved_ips || '-')}</div>
    <div><strong>错误：</strong>抓取 ${escapeHtml(lead.crawl_error || '-')} ｜ 分析 ${escapeHtml(lead.analysis_error || '-')}</div>
    <div><strong>风险：</strong>${escapeHtml(lead.risk_flags || '无')} ${lead.enhanced_risk_flags ? '｜增强：' + escapeHtml(lead.enhanced_risk_flags) : ''}</div>
    <div><strong>来源：</strong>${escapeHtml(lead.source_provider || '-')} ${lead.source_url ? '｜ ' + escapeHtml(lead.source_url) : ''}</div>
    <div><strong>下一步：</strong>${escapeHtml(lead.next_action || '-')} ｜ ${lead.next_follow_up_at ? escapeHtml(formatDateTime(lead.next_follow_up_at)) : '未安排跟进'}</div>
    <div><strong>更新时间：</strong>${escapeHtml(formatDateTime(lead.updated_at))}</div>
  `;
}

function buildSiteUrl(lead) {
  if (lead.final_url) return lead.final_url;
  return `https://${lead.domain}`;
}

function renderDialogTitle(lead) {
  $('#dialogTitle').textContent = lead.domain;
  $('#dialogTitleLinks').innerHTML = `
    <a class="external-chip" href="https://www.aizhan.com/cha/${encodeURIComponent(lead.domain)}/" target="_blank" rel="noopener noreferrer">爱站 SEO</a>
    <a class="external-chip" href="https://rank.aizhan.com/${encodeURIComponent(lead.domain)}/" target="_blank" rel="noopener noreferrer">爱站权重</a>
  `;
}

function switchWorkspaceView(view) {
  document.querySelectorAll('.workspace-tab').forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.view === view);
  });
  document.querySelectorAll('.workspace-view').forEach((panel) => {
    panel.classList.toggle('active', panel.id === `workspace-${view}`);
  });
}

async function refreshWorkspaceView(view) {
  if (view === 'leads') {
    await loadLeads();
    return;
  }
  if (view === 'tasks') {
    await loadTasks();
    return;
  }
  if (view === 'discovery') {
    await Promise.all([loadCandidates(), loadDiscoveryTasks()]);
  }
}

async function openDetail(id) {
  currentLead = await apiJson(`/api/leads/${id}`);
  renderDialogTitle(currentLead);
  $('#editStatus').value = currentLead.lead_status;
  $('#editDealPrice').value = currentLead.deal_price || '';
  $('#editResellPrice').value = currentLead.resell_price || '';
  $('#editGiveUpReason').value = currentLead.give_up_reason || '';
  $('#editNextFollowUpAt').value = toDateTimeLocal(currentLead.next_follow_up_at);
  $('#editNextAction').value = currentLead.next_action || '';
  $('#editContactNote').value = currentLead.contact_note || '';
  $('#editRemark').value = currentLead.remark || '';

  renderLeadDetailInfo(currentLead);

  const template = await apiJson(`/api/leads/${id}/email-template`);
  $('#messageText').value = template.body || '';
  $('#emailTo').value = template.to || '';
  $('#emailSubject').value = template.subject || '';
  await Promise.all([loadCrawlLogs(id), loadEmailLogs(id), loadActivities(id), loadProfile(id)]);
  $('#detailDialog').showModal();
}

async function saveCurrentLead() {
  if (!currentLead) return;
  const payload = {
    lead_status: $('#editStatus').value,
    deal_price: Number($('#editDealPrice').value || 0),
    resell_price: Number($('#editResellPrice').value || 0),
    give_up_reason: $('#editGiveUpReason').value,
    next_follow_up_at: $('#editNextFollowUpAt').value || null,
    next_action: $('#editNextAction').value,
    contact_note: $('#editContactNote').value,
    contact_message: $('#messageText').value,
    remark: $('#editRemark').value,
  };

  currentLead = await apiJson(`/api/leads/${currentLead.id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  toast('已保存');
  renderLeadDetailInfo(currentLead);
  await Promise.all([loadLeads(), loadActivities(currentLead.id), loadProfile(currentLead.id)]);
}

async function copyMessage(id) {
  const text = await fetch(`/api/leads/${id}/message`).then((res) => res.text());
  await navigator.clipboard.writeText(text);
  toast('话术已复制');
}

async function sendCurrentEmail() {
  if (!currentLead) return;
  const payload = {
    to: $('#emailTo').value.trim(),
    subject: $('#emailSubject').value.trim(),
    body: $('#messageText').value.trim(),
  };
  if (!payload.to) {
    toast('请先填写收件人邮箱');
    return;
  }
  if (!payload.body) {
    toast('请先填写邮件正文/话术');
    return;
  }
  if (!confirm(`确认发送邮件给 ${payload.to}？`)) return;
  $('#sendEmailBtn').disabled = true;
  try {
    const result = await apiJson(`/api/leads/${currentLead.id}/send-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    toast(result.message || '邮件已发送');
    currentLead = await apiJson(`/api/leads/${currentLead.id}`);
    await Promise.all([loadEmailLogs(currentLead.id), loadActivities(currentLead.id), loadProfile(currentLead.id), loadLeads()]);
  } finally {
    $('#sendEmailBtn').disabled = false;
  }
}

async function crawlCurrentLead() {
  if (!currentLead) return;
  $('#crawlBtn').disabled = true;
  try {
    currentLead = await apiJson(`/api/leads/${currentLead.id}/crawl`, { method: 'POST' });
    toast('抓取完成');
    await openDetail(currentLead.id);
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  } finally {
    $('#crawlBtn').disabled = false;
  }
}

async function analyzeCurrentLead() {
  if (!currentLead) return;
  $('#analyzeBtn').disabled = true;
  try {
    currentLead = await apiJson(`/api/leads/${currentLead.id}/analyze`, { method: 'POST' });
    toast('增强分析完成');
    await openDetail(currentLead.id);
    await loadLeads();
  } finally {
    $('#analyzeBtn').disabled = false;
  }
}

async function refreshCurrentRegistration() {
  if (!currentLead) return;
  $('#registrationBtn').disabled = true;
  try {
    currentLead = await apiJson(`/api/leads/${currentLead.id}/registration`, { method: 'POST' });
    toast('注册信息已刷新');
    renderLeadDetailInfo(currentLead);
    await Promise.all([loadProfile(currentLead.id), loadActivities(currentLead.id), loadLeads()]);
  } finally {
    $('#registrationBtn').disabled = false;
  }
}

async function refreshCurrentHistory() {
  if (!currentLead) return;
  $('#historyBtn').disabled = true;
  try {
    currentLead = await apiJson(`/api/leads/${currentLead.id}/history`, { method: 'POST' });
    toast('历史画像已刷新');
    renderLeadDetailInfo(currentLead);
    await Promise.all([loadProfile(currentLead.id), loadActivities(currentLead.id), loadLeads()]);
  } finally {
    $('#historyBtn').disabled = false;
  }
}

async function batchAnalyzeCurrentFilters() {
  const limit = Number(prompt('本次最多增强分析多少条？建议先从 20～50 条开始。', '30') || 0);
  if (!limit) return;
  $('#batchAnalysisBtn').disabled = true;
  try {
    const qs = buildQuery({ ...getFilters(), limit });
    const result = await apiJson(`/api/analysis/batch?${qs}`, { method: 'POST' });
    toast(`增强分析完成：成功 ${result.success}，失败 ${result.failed}`);
    await loadLeads();
  } finally {
    $('#batchAnalysisBtn').disabled = false;
  }
}

async function batchRegistrationCurrentFilters() {
  const limit = Number(prompt('本次最多查询多少条注册信息？建议先从 10～20 条开始。', '20') || 0);
  if (!limit) return;
  $('#batchRegistrationBtn').disabled = true;
  try {
    const qs = buildQuery({ ...getFilters(), limit });
    const result = await apiJson(`/api/registration/batch?${qs}`, { method: 'POST' });
    toast(`注册信息刷新完成：成功 ${result.success}，失败 ${result.failed}`);
    await loadLeads();
  } finally {
    $('#batchRegistrationBtn').disabled = false;
  }
}

async function batchHistoryCurrentFilters() {
  const limit = Number(prompt('本次最多查询多少条历史画像？建议先从 5～10 条开始。', '10') || 0);
  if (!limit) return;
  $('#batchHistoryBtn').disabled = true;
  try {
    const qs = buildQuery({ ...getFilters(), limit });
    const result = await apiJson(`/api/history/batch?${qs}`, { method: 'POST' });
    toast(`历史画像刷新完成：成功 ${result.success}，失败 ${result.failed}`);
    await loadLeads();
  } finally {
    $('#batchHistoryBtn').disabled = false;
  }
}

function selectedRadarSearchEngines() {
  const select = $('#radarSearchEngines');
  if (!select) return ['baidu', 'bing'];
  return Array.from(select.selectedOptions).map((option) => option.value).filter(Boolean);
}

async function radarDiscovery() {
  const mode = $('#radarKeywordMode').value;
  const keywords = $('#radarKeywords').value.trim();
  if (mode === 'manual' && !keywords) {
    toast('请输入关键词，或切换到随机词库');
    return;
  }
  const engines = selectedRadarSearchEngines();
  if (!engines.length) {
    toast('请至少选择一个搜索引擎');
    return;
  }
  const limit = Number(prompt('每个搜索引擎/关键词最多提取多少个候选？建议 5～10。', '10') || 0);
  if (!limit) return;
  $('#radarDiscoveryBtn').disabled = true;
  try {
    const result = await apiJson('/api/radar/discovery/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        keywords,
        keyword_mode: mode,
        search_engines: engines,
        limit,
        auto_qualify: false,
      }),
    });
    const errorText = (result.errors || []).length ? `，错误 ${result.errors.length} 条` : '';
    toast(`雷达搜索完成：新增 ${result.created}，更新 ${result.updated}，过滤 ${result.rejected}${errorText}`);
    await loadCandidates();
  } finally {
    $('#radarDiscoveryBtn').disabled = false;
  }
}

async function batchQualifyCandidates() {
  const limit = Number(prompt('本次最多预筛多少条候选？', '20') || 0);
  if (!limit) return;
  $('#batchQualifyCandidatesBtn').disabled = true;
  try {
    const result = await apiJson('/api/candidates/batch-qualify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status: $('#candidateStatusFilter').value,
        keyword: $('#candidateKeyword').value.trim(),
        limit,
        site_index_engines: selectedRadarSearchEngines(),
      }),
    });
    toast(`预筛完成：合格 ${result.qualified}，淘汰 ${result.rejected}，待补权重 ${result.need_weight}，待补索引 ${result.need_site_index}`);
    await loadCandidates();
  } finally {
    $('#batchQualifyCandidatesBtn').disabled = false;
  }
}

async function qualifyCandidate(id) {
  await apiJson(`/api/candidates/${id}/site-index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ site_index_engines: selectedRadarSearchEngines() }),
  });
  toast('候选预筛已执行');
  await loadCandidates();
}

async function fillCandidateWeight(id) {
  const weightsText = prompt('输入权重：百度PC,百度移动,搜狗,360,神马,头条,必应', '1,0,0,0,0,0,0');
  if (!weightsText) return;
  const siteNature = prompt('网站性质/备案主体，例如：个人', '个人');
  if (!siteNature) return;
  const values = weightsText.split(/[,，\s]+/).map((item) => Number(item || 0));
  const payload = {
    baidu_pc_weight: values[0] || 0,
    baidu_mobile_weight: values[1] || 0,
    sogou_weight: values[2] || 0,
    so_weight: values[3] || 0,
    sm_weight: values[4] || 0,
    toutiao_weight: values[5] || 0,
    bing_weight: values[6] || 0,
    site_nature: siteNature,
  };
  await apiJson(`/api/candidates/${id}/weight-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  toast('权重/网站性质已补充并预筛');
  await loadCandidates();
}

async function refreshCandidateIntel(id) {
  await apiJson(`/api/candidates/${id}/intel`, { method: 'POST' });
  toast('Whois/IP 情报已刷新');
  await loadCandidates();
}

async function promoteCandidate(id) {
  if (!confirm('确认将该候选转入正式线索库？合格候选会自动抓取联系方式。')) return;
  await apiJson(`/api/candidates/${id}/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_crawl: true }),
  });
  toast('已转入正式线索库');
  await Promise.all([loadCandidates(), loadLeads(), loadTasks()]);
}

async function keywordDiscovery() {
  const keywords = prompt('输入中文、英文或拼音关键词，一行一个或用逗号分隔。例如：小说,kaoyan,tiku', '小说,kaoyan,tiku');
  if (!keywords) return;
  const limit = Number(prompt('最多生成多少条候选域名？', '200') || 0);
  if (!limit) return;
  $('#keywordDiscoveryBtn').disabled = true;
  try {
    const result = await apiJson('/api/discovery/keywords', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords, limit }),
    });
    if ((result.total || 0) === 0 && (result.invalid_keywords || []).length) {
      toast(`没有生成候选：${result.invalid_keywords.join('、')} 无法转成可用域名词根`);
    } else {
      const converted = (result.normalized_keywords || [])
        .filter((item) => item.raw && item.token && item.raw.toLowerCase() !== item.token)
        .map((item) => `${item.raw}→${item.token}`);
      const suffix = converted.length ? ` ｜ 已转拼音：${converted.join('，')}` : '';
      toast(`关键词发现完成：新增 ${result.created}，更新 ${result.updated}${suffix}`);
    }
    await Promise.all([loadLeads(), loadDiscoveryTasks()]);
  } finally {
    $('#keywordDiscoveryBtn').disabled = false;
  }
}

async function searchDiscovery() {
  const query = prompt('输入中文或英文检索词，例如：小说、考研、图片压缩', '小说');
  if (!query) return;
  const limit = Number(prompt('最多提取多少个真实站点？建议先从 5～10 个开始。', '10') || 0);
  if (!limit) return;
  $('#searchDiscoveryBtn').disabled = true;
  try {
    const result = await apiJson('/api/discovery/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit, auto_crawl: true }),
    });
    const crawl = result.crawl
      ? `，自动抓取成功 ${result.crawl.success}，失败 ${result.crawl.failed}`
      : '';
    toast(`中文搜索发现完成：新增 ${result.created}，更新 ${result.updated}${crawl}`);
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  } finally {
    $('#searchDiscoveryBtn').disabled = false;
  }
}

async function externalLinkDiscovery() {
  const sourceLimit = Number(prompt('从当前筛选线索中选多少个站点做外链发现？', '10') || 0);
  if (!sourceLimit) return;
  const newLimit = Number(prompt('最多发现多少个新域名？', '100') || 0);
  if (!newLimit) return;
  $('#externalDiscoveryBtn').disabled = true;
  try {
    const qs = buildQuery({ ...getFilters(), source_limit: sourceLimit, new_limit: newLimit });
    const result = await apiJson(`/api/discovery/external-links?${qs}`, { method: 'POST' });
    toast(`外链发现完成：新增 ${result.created}，更新 ${result.updated}`);
    await Promise.all([loadLeads(), loadDiscoveryTasks()]);
  } finally {
    $('#externalDiscoveryBtn').disabled = false;
  }
}

async function batchCrawlCurrentFilters() {
  const limit = Number(prompt('本次最多抓取多少条？建议先从 20～50 条开始。', '30') || 0);
  if (!limit) return;
  $('#batchCrawlBtn').disabled = true;
  try {
    const qs = buildQuery({ ...getFilters(), limit });
    const result = await apiJson(`/api/crawl/batch?${qs}`, { method: 'POST' });
    toast(`批量抓取完成：成功 ${result.success}，失败 ${result.failed}`);
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  } finally {
    $('#batchCrawlBtn').disabled = false;
  }
}

async function retryFailedCrawls() {
  const limit = Number(prompt('本次最多重试多少条失败线索？', '30') || 0);
  if (!limit) return;
  $('#retryFailedBtn').disabled = true;
  try {
    const result = await apiJson(`/api/crawl/retry-failed?limit=${limit}`, { method: 'POST' });
    toast(`重试完成：成功 ${result.success}，失败 ${result.failed}`);
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  } finally {
    $('#retryFailedBtn').disabled = false;
  }
}

async function rescoreCurrentLead() {
  if (!currentLead) return;
  currentLead = await apiJson(`/api/leads/${currentLead.id}/rescore`, { method: 'POST' });
  toast('已重新评分');
  await openDetail(currentLead.id);
  await loadLeads();
}

async function deleteCurrentLead() {
  if (!currentLead) return;
  if (!confirm(`确认删除 ${currentLead.domain}？`)) return;
  await apiJson(`/api/leads/${currentLead.id}`, { method: 'DELETE' });
  $('#detailDialog').close();
  currentLead = null;
  toast('已删除');
  await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

async function importCsv(file) {
  const form = new FormData();
  form.append('file', file);
  const providerId = $('#providerSelect')?.value || 'generic_csv';
  const result = await apiJson(`/api/providers/${encodeURIComponent(providerId)}/import`, { method: 'POST', body: form });
  toast(`导入完成：新增 ${result.created}，更新 ${result.updated}`);
  await loadLeads();
}

async function restoreJson(file) {
  const form = new FormData();
  form.append('file', file);
  const result = await apiJson('/api/restore/json', { method: 'POST', body: form });
  toast(`恢复完成：新增 ${result.created}，更新 ${result.updated}`);
  await loadLeads();
}

async function submitManualLeads() {
  const domains = $('#manualDomains').value.trim();
  if (!domains) {
    toast('请先输入域名');
    return;
  }

  $('#submitManualLeadBtn').disabled = true;
  try {
    const result = await apiJson('/api/leads/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        domains,
        title: $('#manualTitle').value.trim(),
        remark: $('#manualRemark').value.trim(),
        auto_crawl: $('#manualAutoCrawl').checked,
        auto_analyze: $('#manualAutoAnalyze').checked,
      }),
    });

    const crawlText = result.crawl ? `，抓取成功 ${result.crawl.success}，失败 ${result.crawl.failed}` : '';
    const analysisText = result.analysis ? `，分析成功 ${result.analysis.success}，失败 ${result.analysis.failed}` : '';
    toast(`手动新增完成：新增 ${result.created}，更新 ${result.updated}${crawlText}${analysisText}`);

    $('#manualDomains').value = '';
    $('#manualTitle').value = '';
    $('#manualRemark').value = '';
    $('#manualAutoCrawl').checked = false;
    $('#manualAutoAnalyze').checked = false;
    $('#manualLeadDialog').close();
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  } finally {
    $('#submitManualLeadBtn').disabled = false;
  }
}

function openManualLeadDialog() {
  $('#manualLeadDialog').showModal();
  $('#manualDomains').focus();
}

function download(url) {
  window.location.href = url;
}

function initEvents() {
  document.querySelectorAll('.workspace-tab').forEach((tab) => {
    tab.addEventListener('click', async () => {
      switchWorkspaceView(tab.dataset.view);
      await refreshWorkspaceView(tab.dataset.view);
    });
  });

  $('#csvFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (file) await importCsv(file);
    event.target.value = '';
  });

  $('#jsonFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (file) await restoreJson(file);
    event.target.value = '';
  });

  $('#manualLeadBtn').addEventListener('click', openManualLeadDialog);
  $('#closeManualLeadBtn').addEventListener('click', () => $('#manualLeadDialog').close());
  $('#cancelManualLeadBtn').addEventListener('click', () => $('#manualLeadDialog').close());
  $('#submitManualLeadBtn').addEventListener('click', submitManualLeads);

  $('#searchBtn').addEventListener('click', loadLeads);
  $('#resetBtn').addEventListener('click', async () => {
    $('#keyword').value = '';
    $('#statusFilter').value = '';
    $('#crawlStatusFilter').value = '';
    $('#riskFilter').value = '';
    $('#minScore').value = '';
    await loadLeads();
  });

  $('#exportCsvBtn').addEventListener('click', () => {
    const qs = buildQuery(getFilters());
    download(`/api/export/csv?${qs}`);
  });
  $('#backupJsonBtn').addEventListener('click', () => download('/api/export/json'));
  $('#batchCrawlBtn').addEventListener('click', batchCrawlCurrentFilters);
  $('#batchAnalysisBtn').addEventListener('click', batchAnalyzeCurrentFilters);
  $('#batchRegistrationBtn').addEventListener('click', batchRegistrationCurrentFilters);
  $('#batchHistoryBtn').addEventListener('click', batchHistoryCurrentFilters);
  $('#radarDiscoveryBtn').addEventListener('click', radarDiscovery);
  $('#batchQualifyCandidatesBtn').addEventListener('click', batchQualifyCandidates);
  $('#refreshCandidatesBtn').addEventListener('click', loadCandidates);
  $('#candidateKeyword').addEventListener('keydown', async (event) => {
    if (event.key === 'Enter') await loadCandidates();
  });
  $('#candidateStatusFilter').addEventListener('change', loadCandidates);
  $('#keywordDiscoveryBtn').addEventListener('click', keywordDiscovery);
  $('#searchDiscoveryBtn').addEventListener('click', searchDiscovery);
  $('#externalDiscoveryBtn').addEventListener('click', externalLinkDiscovery);
  $('#retryFailedBtn').addEventListener('click', retryFailedCrawls);
  $('#refreshTasksBtn').addEventListener('click', loadTasks);
  $('#refreshDiscoveryTasksBtn').addEventListener('click', loadDiscoveryTasks);

  $('#closeDialogBtn').addEventListener('click', () => $('#detailDialog').close());
  $('#saveBtn').addEventListener('click', saveCurrentLead);
  $('#deleteBtn').addEventListener('click', deleteCurrentLead);
  $('#crawlBtn').addEventListener('click', crawlCurrentLead);
  $('#analyzeBtn').addEventListener('click', analyzeCurrentLead);
  $('#registrationBtn').addEventListener('click', refreshCurrentRegistration);
  $('#historyBtn').addEventListener('click', refreshCurrentHistory);
  $('#rescoreBtn').addEventListener('click', rescoreCurrentLead);
  $('#refreshLogsBtn').addEventListener('click', async () => {
    if (currentLead) await loadCrawlLogs(currentLead.id);
  });
  $('#copyMessageBtn').addEventListener('click', async () => {
    await navigator.clipboard.writeText($('#messageText').value);
    toast('话术已复制');
  });
  $('#sendEmailBtn').addEventListener('click', sendCurrentEmail);
  $('#refreshEmailLogsBtn').addEventListener('click', async () => {
    if (currentLead) await loadEmailLogs(currentLead.id);
  });
  $('#refreshActivitiesBtn').addEventListener('click', async () => {
    if (currentLead) await loadActivities(currentLead.id);
  });

  $('#clearBtn').addEventListener('click', async () => {
    if (!confirm('确认清空所有线索和抓取日志？建议先备份 JSON。')) return;
    await apiJson('/api/clear', { method: 'POST' });
    toast('已清空');
    await Promise.all([loadLeads(), loadTasks(), loadDiscoveryTasks()]);
  });
}

initEvents();
Promise.all([loadProviders(), loadSearchEngines(), loadLeads(), loadTasks(), loadDiscoveryTasks(), loadCandidates()]).catch((error) => toast(error.message));
