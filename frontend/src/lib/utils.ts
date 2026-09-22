/** Join class names, skipping falsy values. */
export function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(' ');
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 'never';
  const diff = Date.now() - then;
  if (diff < 0) return 'just now';
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return formatDateTime(iso);
}

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || Number.isNaN(totalSeconds)) return '—';
  const s = Math.max(0, Math.floor(totalSeconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0 || parts.length === 0) parts.push(`${m}m`);
  return parts.join(' ');
}

export function formatMs(ms: number | null | undefined, decimals = 0): string {
  if (ms == null || Number.isNaN(ms)) return '—';
  return `${ms.toFixed(decimals)} ms`;
}

export function formatPercent(n: number | null | undefined, decimals = 2): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${n.toFixed(decimals)}%`;
}

const INTERVAL_LABELS: Record<number, string> = {
  60: '1 min',
  300: '5 min',
  600: '10 min',
  900: '15 min',
  1800: '30 min',
  3600: '1 hr',
};

export function intervalLabel(seconds: number): string {
  return INTERVAL_LABELS[seconds] ?? `${seconds}s`;
}

export const INTERVAL_OPTIONS = [60, 300, 600, 900, 1800, 3600];
export const METHOD_OPTIONS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'] as const;

export const WEBHOOK_EVENT_OPTIONS = [
  'incident.created',
  'incident.resolved',
  'api.down',
  'api.recovered',
] as const;

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Truncate a URL for table display. */
export function shortUrl(url: string, max = 42): string {
  return url.length > max ? `${url.slice(0, max - 1)}…` : url;
}
