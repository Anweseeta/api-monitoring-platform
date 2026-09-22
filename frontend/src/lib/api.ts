import axios, { AxiosError } from 'axios';
import type {
  ActivityEntry,
  AuthPayload,
  CheckResult,
  DashboardSummary,
  HttpMethod,
  Incident,
  IncidentDetail,
  IncidentSeverity,
  IncidentStatus,
  IncidentSummary,
  Monitor,
  MonitorInput,
  MonitorMetrics,
  MonitorStatus,
  Paginated,
  Pagination,
  SettingsData,
  User,
  Webhook,
} from '../types';
import { ACCESS_TOKEN_KEY, API_BASE_URL } from '../config';

// ---------------------------------------------------------------------------
// Axios instance: attaches Bearer token, redirects to /login on 401.
// ---------------------------------------------------------------------------
export const api = axios.create({ baseURL: API_BASE_URL, timeout: 30_000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

// ---------------------------------------------------------------------------
// Envelopes
// ---------------------------------------------------------------------------
interface Envelope<T> {
  success: boolean;
  data: T;
}

interface ListEnvelope<T> {
  success: boolean;
  data: T[];
  pagination: Pagination;
}

async function unwrap<T>(promise: Promise<{ data: Envelope<T> }>): Promise<T> {
  const res = await promise;
  return res.data.data;
}

async function unwrapList<T>(promise: Promise<{ data: ListEnvelope<T> }>): Promise<Paginated<T>> {
  const res = await promise;
  return { items: res.data.data, pagination: res.data.pagination };
}

export interface ApiErrorBody {
  success: false;
  message: string;
  error_code?: string;
}

export function getErrorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as Partial<ApiErrorBody> | undefined;
    if (body?.message) return body.message;
    if (err.code === 'ECONNABORTED') return 'Request timed out. Please try again.';
    if (!err.response) return 'Could not reach the server. Is the backend running?';
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export const authApi = {
  register: (name: string, email: string, password: string) =>
    unwrap<AuthPayload>(api.post('/api/auth/register', { name, email, password })),
  login: (email: string, password: string) =>
    unwrap<AuthPayload>(api.post('/api/auth/login', { email, password })),
  me: () => unwrap<{ user: User }>(api.get('/api/auth/me')).then((d) => d.user),
};

// ---------------------------------------------------------------------------
// Monitors
// ---------------------------------------------------------------------------
export interface MonitorFilters {
  search?: string;
  status?: MonitorStatus | '';
  method?: HttpMethod | '';
  page?: number;
  page_size?: number;
}

export const monitorsApi = {
  list: (f: MonitorFilters = {}) =>
    unwrapList<Monitor>(
      api.get('/api/monitors', {
        params: {
          search: f.search || undefined,
          status: f.status || undefined,
          method: f.method || undefined,
          page: f.page,
          page_size: f.page_size,
        },
      }),
    ),
  create: (input: MonitorInput) => unwrap<Monitor>(api.post('/api/monitors', input)),
  get: (id: string) => unwrap<Monitor>(api.get(`/api/monitors/${id}`)),
  update: (id: string, input: Partial<MonitorInput>) => unwrap<Monitor>(api.put(`/api/monitors/${id}`, input)),
  remove: (id: string) => unwrap<null>(api.delete(`/api/monitors/${id}`)),
  test: (id: string) => unwrap<CheckResult>(api.post(`/api/monitors/${id}/test`)),
  pause: (id: string) => unwrap<Monitor>(api.post(`/api/monitors/${id}/pause`)),
  resume: (id: string) => unwrap<Monitor>(api.post(`/api/monitors/${id}/resume`)),
  checks: (id: string, page = 1, page_size = 20) =>
    unwrapList<CheckResult>(api.get(`/api/monitors/${id}/checks`, { params: { page, page_size } })),
  metrics: (id: string, period: string) =>
    unwrap<MonitorMetrics>(api.get(`/api/monitors/${id}/metrics`, { params: { period } })),
};

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export const dashboardApi = {
  summary: () => unwrap<DashboardSummary>(api.get('/api/dashboard/summary')),
  uptime: (period: string) =>
    unwrap<{ points: Array<{ timestamp: string; uptime: number }> }>(
      api.get('/api/dashboard/uptime', { params: { period } }),
    ).then((d) => d.points),
  latency: (period: string) =>
    unwrap<{ points: Array<{ timestamp: string; avg_ms: number }> }>(
      api.get('/api/dashboard/latency', { params: { period } }),
    ).then((d) => d.points),
  incidents: (period: string) =>
    unwrap<{ points: Array<{ timestamp: string; created: number; resolved: number }> }>(
      api.get('/api/dashboard/incidents', { params: { period } }),
    ).then((d) => d.points),
};

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------
export interface IncidentFilters {
  status?: IncidentStatus | '';
  severity?: IncidentSeverity | '';
  api_id?: string;
  from?: string;
  to?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface IncidentListResult extends Paginated<Incident> {
  summary: IncidentSummary;
}

export const incidentsApi = {
  list: async (f: IncidentFilters = {}): Promise<IncidentListResult> => {
    const res = await api.get('/api/incidents', {
      params: {
        status: f.status || undefined,
        severity: f.severity || undefined,
        api_id: f.api_id || undefined,
        from: f.from || undefined,
        to: f.to || undefined,
        search: f.search || undefined,
        page: f.page,
        page_size: f.page_size,
      },
    });
    const body = res.data as ListEnvelope<Incident> & { summary: IncidentSummary };
    return { items: body.data, pagination: body.pagination, summary: body.summary };
  },
  create: (input: { api_id: string; title: string; description?: string; severity?: IncidentSeverity }) =>
    unwrap<Incident>(api.post('/api/incidents', input)),
  get: (id: string) => unwrap<IncidentDetail>(api.get(`/api/incidents/${id}`)),
  update: (id: string, input: { status?: IncidentStatus; severity?: IncidentSeverity; root_cause?: string; resolution_notes?: string }) =>
    unwrap<Incident>(api.put(`/api/incidents/${id}`, input)),
  remove: (id: string) => unwrap<null>(api.delete(`/api/incidents/${id}`)),
  resolve: (id: string, resolution_notes?: string) =>
    unwrap<Incident>(api.post(`/api/incidents/${id}/resolve`, { resolution_notes })),
};

// ---------------------------------------------------------------------------
// Activity logs
// ---------------------------------------------------------------------------
export interface ActivityFilters {
  resource_type?: string;
  action?: string;
  page?: number;
  page_size?: number;
}

export const activityApi = {
  list: (f: ActivityFilters = {}) =>
    unwrapList<ActivityEntry>(
      api.get('/api/activity', {
        params: {
          resource_type: f.resource_type || undefined,
          action: f.action || undefined,
          page: f.page,
          page_size: f.page_size,
        },
      }),
    ),
};

// ---------------------------------------------------------------------------
// Settings & webhooks
// ---------------------------------------------------------------------------
export const settingsApi = {
  get: () => unwrap<SettingsData>(api.get('/api/settings')),
  update: (
    patch: Omit<Partial<SettingsData>, 'profile' | 'notifications'> & {
      profile?: { name?: string };
      notifications?: Partial<SettingsData['notifications']>;
    },
  ) => unwrap<SettingsData>(api.put('/api/settings', patch)),
};

export const webhooksApi = {
  list: () => unwrap<Webhook[]>(api.get('/api/webhooks')),
  create: (input: { name: string; url: string; events: string[]; active?: boolean }) =>
    unwrap<Webhook>(api.post('/api/webhooks', input)),
  remove: (id: string) => unwrap<null>(api.delete(`/api/webhooks/${id}`)),
};
