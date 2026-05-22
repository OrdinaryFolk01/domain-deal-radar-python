export type LeadStatus = 'NEW' | 'CHECKED' | 'CONTACTED' | 'REPLIED' | 'NEGOTIATING' | 'BOUGHT' | 'RESOLD' | 'GIVE_UP';

export type CandidateStatus = 'DISCOVERED' | 'REJECTED' | 'NEED_WEIGHT' | 'NEED_SITE_INDEX' | 'QUALIFIED' | 'PROMOTED';

export interface Lead {
  id: number;
  domain: string;
  root_domain: string;
  suffix: string;
  title: string;
  baidu_pc_weight: number;
  baidu_mobile_weight: number;
  indexed_count: number;
  sogou_weight: number;
  so_weight: number;
  sm_weight: number;
  toutiao_weight: number;
  bing_weight: number;
  sogou_indexed_count: number;
  so_indexed_count: number;
  sm_indexed_count: number;
  toutiao_indexed_count: number;
  bing_indexed_count: number;
  icp_type: string;
  remark: string;
  source_provider: string;
  source_url: string;
  status_code: string;
  final_url: string;
  emails: string;
  phones: string;
  wechats: string;
  qqs: string;
  crawl_status: string;
  crawl_error: string;
  crawl_pages_done: number;
  crawl_pages_total: number;
  analysis_status: string;
  analysis_error: string;
  dns_resolved: boolean;
  resolved_ips: string;
  site_health: string;
  enhanced_risk_flags: string;
  registration_status: string;
  registrar_name: string;
  domain_expires_at: string | null;
  buyability_score: number;
  buyability_grade: string;
  history_score: number;
  history_grade: string;
  score: number;
  risk_flags: string;
  suggestion: string;
  first_offer: number;
  max_offer: number;
  lead_status: LeadStatus;
  contact_note: string;
  contact_message: string;
  next_action: string;
  next_follow_up_at: string | null;
  deal_price: number;
  resell_price: number;
  give_up_reason: string;
  updated_at: string;
}

export interface DomainCandidate {
  id: number;
  domain: string;
  root_domain: string;
  suffix: string;
  title: string;
  summary: string;
  search_engine: string;
  search_engines: string;
  keyword: string;
  keywords: string;
  source_url: string;
  source_urls: string;
  status: CandidateStatus;
  reject_reason: string;
  weight_snapshot: string;
  site_index_snapshot: string;
  whois_snapshot: string;
  ip_snapshot: string;
  contact_snapshot: string;
  priority_score: number;
  promoted_lead_id: number | null;
  updated_at: string;
  created_at: string;
}

export interface SearchEngine {
  provider_id: string;
  name: string;
  enabled: boolean;
}

export interface RadarDiscoveryResult {
  created: number;
  updated: number;
  rejected: number;
  errors: string[];
  candidate_ids: number[];
  keywords: string[];
  search_engines: string[];
}

export interface RadarSearchHistoryEntry {
  id: string;
  searchedAt: string;
  keywords: string[];
  searchEngines: string[];
  candidateIds: number[];
  created: number;
  updated: number;
  rejected: number;
  errorsCount: number;
}

export interface CrawlTask {
  id: number;
  batch_id: string;
  domain: string;
  status: string;
  pages_total: number;
  pages_done: number;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DiscoveryTask {
  id: number;
  provider_id: string;
  source_type: string;
  status: string;
  keyword: string;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface LeadActivity {
  id: number;
  title: string;
  event_type: string;
  detail: string;
  created_at: string;
}

export interface EmailLog {
  id: number;
  to_email: string;
  subject: string;
  status: string;
  error_message: string;
  created_at: string;
  sent_at: string | null;
}

export interface EmailTemplate {
  to: string;
  subject: string;
  body: string;
}

export interface EmailSendResponse {
  ok: boolean;
  message: string;
  log_id: number | null;
}

export interface EmailSettings {
  receive_protocol: 'imap' | 'pop3';
  receive_host: string;
  receive_port: number;
  receive_use_ssl: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_from: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  has_password: boolean;
  source: string;
}

export interface EmailSettingsUpdate {
  receive_protocol: 'imap' | 'pop3';
  receive_host: string;
  receive_port: number;
  receive_use_ssl: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password?: string;
  smtp_from: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
}

export interface LeadProfile {
  radar_grade: string;
  risk_level: string;
  contactability: string;
  follow_up_state: string;
  recommended_action: string;
  signals: string[];
  contacts: Record<string, number>;
  buyability: { score: number; grade: string; status: string; reasons: string[] };
  history: { score: number; grade: string; status: string; reasons: string[] };
  score_breakdown: Array<{ category: string; label: string; points: number; reason: string }>;
}
