// Shared domain types. Mirrors API_CONTRACT.md exactly.

export interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface AuthPayload {
  user: User;
  access_token: string;
  token_type: 'bearer';
}

export type MonitorStatus = 'healthy' | 'degraded' | 'down' | 'paused';
export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD';

export interface Monitor {
  id: string;
  user_id: string;
  name: string;
  url: string;
  method: HttpMethod;
  description: string;
  interval: number;
  timeout: number;
  expected_status: number;
  headers: Record<string, string>;
  body: unknown;
  active: boolean;
  status: MonitorStatus;
  consecutive_failures: number;
  consecutive_successes: number;
  last_checked_at: string | null;
  uptime_24h: number;
  created_at: string;
  updated_at: string;
}

export interface MonitorInput {
  name: string;
  url: string;
  method: HttpMethod;
  description?: string;
  interval: number;
  timeout: number;
  expected_status: number;
  headers?: Record<string, string>;
  body?: unknown;
  active?: boolean;
}

export interface CheckResult {
  id: string;
  api_id: string;
  timestamp: string;
  status_code: number | null;
  response_time_ms: number;
  success: boolean;
  error: string | null;
  timed_out: boolean;
  response_size_bytes: number;
}

export interface MonitorMetrics {
  uptime_percent: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  total_checks: number;
  successful_checks: number;
  failed_checks: number;
  error_rate_percent: number;
  status_code_distribution: Record<string, number>;
  response_time_series: Array<{ timestamp: string; avg_ms: number }>;
  uptime_series: Array<{ timestamp: string; uptime: number }>;
}

export type IncidentStatus = 'open' | 'investigating' | 'identified' | 'monitoring' | 'resolved';
export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';

export interface Incident {
  id: string;
  api_id: string;
  user_id: string;
  title: string;
  description: string;
  status: IncidentStatus;
  severity: IncidentSeverity;
  started_at: string;
  detected_at: string;
  resolved_at: string | null;
  duration_seconds: number | null;
  root_cause: string;
  resolution_notes: string;
  created_by: string;
  updated_at: string;
}

export interface IncidentEvent {
  id: string;
  incident_id: string;
  timestamp: string;
  event_type: 'detected' | 'created' | 'updated' | 'resolved' | 'note' | 'auto_resolved' | 'escalated';
  message: string;
}

export interface IncidentDetail {
  incident: Incident;
  api: Monitor | null;
  events: IncidentEvent[];
}

export interface IncidentSummary {
  total: number;
  open: number;
  resolved: number;
  critical: number;
  avg_resolution_seconds: number;
}

export interface ActivityEntry {
  id: string;
  user_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  resource_name: string;
  timestamp: string;
  ip: string;
  user_agent: string;
}

export interface NotificationPrefs {
  email_enabled: boolean;
  webhook_enabled: boolean;
}

export interface SettingsData {
  default_timeout: number;
  default_interval: number;
  failure_threshold: number;
  recovery_threshold: number;
  degraded_latency_ms: number;
  results_retention_days: number;
  notifications: NotificationPrefs;
  profile: { name: string; email: string };
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  events: string[];
  active: boolean;
  created_at: string;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface Paginated<T> {
  items: T[];
  pagination: Pagination;
}

export interface DashboardSummary {
  total_apis: number;
  healthy_apis: number;
  degraded_apis: number;
  down_apis: number;
  paused_apis: number;
  avg_response_time_ms: number;
  overall_uptime_24h: number;
  open_incidents: number;
  recent_incidents: Incident[];
  recent_activity: ActivityEntry[];
  health_overview: { healthy: number; degraded: number; down: number; paused: number };
}

export type Period = '24h' | '7d' | '30d';
