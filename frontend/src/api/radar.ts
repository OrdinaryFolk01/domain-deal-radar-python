import { apiJson, buildQuery, jsonOptions } from './client';
import type {
  CrawlTask,
  DiscoveryTask,
  DomainCandidate,
  EmailLog,
  EmailSendResponse,
  EmailSettings,
  EmailSettingsUpdate,
  EmailTemplate,
  Lead,
  LeadActivity,
  LeadProfile,
  RadarDiscoveryResult,
  SearchEngine,
} from './types';

export interface LeadFilters {
  keyword?: string;
  status?: string;
  crawl_status?: string;
  risk?: string;
  min_score?: string;
  limit?: number;
}

export interface CandidateFilters {
  status?: string;
  keyword?: string;
  sources?: string;
  ids?: string;
  limit?: number;
}

export function listLeads(filters: LeadFilters): Promise<Lead[]> {
  return apiJson(`/api/leads?${buildQuery({ ...filters, limit: filters.limit ?? 500 })}`);
}

export function listCandidates(filters: CandidateFilters): Promise<DomainCandidate[]> {
  return apiJson(`/api/candidates?${buildQuery({ ...filters, limit: filters.limit ?? 200 })}`);
}

export function listSearchEngines(): Promise<SearchEngine[]> {
  return apiJson('/api/search-engines');
}

export function startRadarDiscovery(payload: {
  keywords: string;
  keyword_mode: string;
  search_engines: string[];
  limit: number;
  auto_qualify: boolean;
}) {
  return apiJson<RadarDiscoveryResult>('/api/radar/discovery/start', jsonOptions(payload));
}

export function batchQualifyCandidates(payload: { status: string; keyword: string; limit: number; site_index_engines: string[] }) {
  return apiJson<{ total: number; qualified: number; rejected: number; need_weight: number; need_site_index: number }>(
    '/api/candidates/batch-qualify',
    jsonOptions(payload),
  );
}

export function qualifyCandidate(id: number, engines: string[]) {
  return apiJson<DomainCandidate>(`/api/candidates/${id}/site-index`, jsonOptions({ site_index_engines: engines }));
}

export function updateCandidateWeight(
  id: number,
  payload: Partial<{
    baidu_pc_weight: number;
    baidu_mobile_weight: number;
    sogou_weight: number;
    so_weight: number;
    sm_weight: number;
    toutiao_weight: number;
    bing_weight: number;
    indexed_count: number;
    sogou_indexed_count: number;
    so_indexed_count: number;
    sm_indexed_count: number;
    toutiao_indexed_count: number;
    bing_indexed_count: number;
    site_nature: string;
  }>,
) {
  return apiJson<DomainCandidate>(`/api/candidates/${id}/weight-check`, jsonOptions(payload));
}

export function refreshCandidateIntel(id: number) {
  return apiJson<DomainCandidate>(`/api/candidates/${id}/intel`, { method: 'POST' });
}

export function promoteCandidate(id: number, autoCrawl = true) {
  return apiJson<Lead>(`/api/candidates/${id}/promote`, jsonOptions({ auto_crawl: autoCrawl }));
}

export function listTasks(): Promise<CrawlTask[]> {
  return apiJson('/api/crawl/tasks?limit=30');
}

export function listDiscoveryTasks(): Promise<DiscoveryTask[]> {
  return apiJson('/api/discovery/tasks?limit=30');
}

export function getLead(id: number): Promise<Lead> {
  return apiJson(`/api/leads/${id}`);
}

export function getLeadProfile(id: number): Promise<LeadProfile> {
  return apiJson(`/api/leads/${id}/profile`);
}

export function listLeadActivities(id: number): Promise<LeadActivity[]> {
  return apiJson(`/api/leads/${id}/activities?limit=30`);
}

export function listEmailLogs(id: number): Promise<EmailLog[]> {
  return apiJson(`/api/leads/${id}/email-logs?limit=20`);
}

export function getEmailTemplate(id: number): Promise<EmailTemplate> {
  return apiJson(`/api/leads/${id}/email-template`);
}

export function sendLeadEmail(id: number, payload: { to: string; subject: string; body: string }): Promise<EmailSendResponse> {
  return apiJson(`/api/leads/${id}/send-email`, jsonOptions(payload));
}

export function getEmailSettings(): Promise<EmailSettings> {
  return apiJson('/api/settings/email');
}

export function saveEmailSettings(payload: EmailSettingsUpdate): Promise<EmailSettings> {
  return apiJson('/api/settings/email', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function patchLead(id: number, payload: Partial<Lead>) {
  return apiJson<Lead>(
    `/api/leads/${id}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
}

export function crawlLead(id: number) {
  return apiJson<Lead>(`/api/leads/${id}/crawl`, { method: 'POST' });
}

export function analyzeLead(id: number) {
  return apiJson<Lead>(`/api/leads/${id}/analyze`, { method: 'POST' });
}

export function refreshRegistration(id: number) {
  return apiJson<Lead>(`/api/leads/${id}/registration`, { method: 'POST' });
}

export function refreshHistory(id: number) {
  return apiJson<Lead>(`/api/leads/${id}/history`, { method: 'POST' });
}

export function createManualLeads(payload: {
  domains: string;
  title: string;
  remark: string;
  auto_crawl: boolean;
  auto_analyze: boolean;
}) {
  return apiJson<{ created: number; updated: number; total: number }>('/api/leads/manual', jsonOptions(payload));
}

export function importProviderCsv(providerId: string, file: File) {
  const form = new FormData();
  form.append('file', file);
  return apiJson<{ created: number; updated: number; total: number }>(`/api/providers/${encodeURIComponent(providerId)}/import`, {
    method: 'POST',
    body: form,
  });
}

export function listProviders() {
  return apiJson<Array<{ provider_id: string; name: string }>>('/api/providers');
}
