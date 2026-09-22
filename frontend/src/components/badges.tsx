import type { HttpMethod, IncidentSeverity, IncidentStatus, MonitorStatus } from '../types';
import { cx } from '../lib/utils';

const base = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium';

function Dot({ className }: { className: string }) {
  return <span className={cx('h-1.5 w-1.5 rounded-full', className)} />;
}

const STATUS_STYLES: Record<MonitorStatus, { chip: string; dot: string; label: string }> = {
  healthy: {
    chip: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
    dot: 'bg-emerald-500',
    label: 'Healthy',
  },
  degraded: {
    chip: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
    dot: 'bg-amber-500',
    label: 'Degraded',
  },
  down: {
    chip: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
    dot: 'bg-red-500',
    label: 'Down',
  },
  paused: {
    chip: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
    dot: 'bg-slate-400',
    label: 'Paused',
  },
};

export function MonitorStatusBadge({ status }: { status: MonitorStatus }) {
  const s = STATUS_STYLES[status];
  return (
    <span className={cx(base, s.chip)}>
      <Dot className={s.dot} />
      {s.label}
    </span>
  );
}

const SEVERITY_STYLES: Record<IncidentSeverity, { chip: string; label: string }> = {
  low: {
    chip: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300',
    label: 'Low',
  },
  medium: {
    chip: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
    label: 'Medium',
  },
  high: {
    chip: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
    label: 'High',
  },
  critical: {
    chip: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
    label: 'Critical',
  },
};

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  const s = SEVERITY_STYLES[severity];
  return <span className={cx(base, s.chip)}>{s.label}</span>;
}

const INCIDENT_STATUS_STYLES: Record<IncidentStatus, { chip: string; dot: string; label: string }> = {
  open: {
    chip: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
    dot: 'bg-red-500',
    label: 'Open',
  },
  investigating: {
    chip: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
    dot: 'bg-amber-500',
    label: 'Investigating',
  },
  identified: {
    chip: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300',
    dot: 'bg-sky-500',
    label: 'Identified',
  },
  monitoring: {
    chip: 'bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300',
    dot: 'bg-violet-500',
    label: 'Monitoring',
  },
  resolved: {
    chip: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
    dot: 'bg-emerald-500',
    label: 'Resolved',
  },
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const s = INCIDENT_STATUS_STYLES[status];
  return (
    <span className={cx(base, s.chip)}>
      <Dot className={s.dot} />
      {s.label}
    </span>
  );
}

const METHOD_COLORS: Record<HttpMethod, string> = {
  GET: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  POST: 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300',
  PUT: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  PATCH: 'bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300',
  DELETE: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  HEAD: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
};

export function MethodBadge({ method }: { method: HttpMethod }) {
  return (
    <span
      className={cx(
        'inline-flex rounded px-1.5 py-0.5 font-mono text-[11px] font-bold',
        METHOD_COLORS[method],
      )}
    >
      {method}
    </span>
  );
}

export function SuccessBadge({ success }: { success: boolean }) {
  return success ? (
    <span className={cx(base, 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300')}>
      Success
    </span>
  ) : (
    <span className={cx(base, 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300')}>Failed</span>
  );
}
