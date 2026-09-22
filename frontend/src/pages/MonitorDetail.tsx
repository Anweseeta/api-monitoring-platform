import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  FlaskConical,
  Pause,
  Pencil,
  Play,
  Trash2,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getErrorMessage, monitorsApi } from '../lib/api';
import { useToast } from '../lib/toast';
import { useChartColors, useTheme } from '../hooks/useTheme';
import {
  cx,
  formatDateTime,
  formatMs,
  formatPercent,
  formatRelative,
  intervalLabel,
} from '../lib/utils';
import type { Period } from '../types';
import {
  Button,
  Card,
  CardHeader,
  ChartSkeleton,
  ConfirmModal,
  EmptyState,
  ErrorState,
  IconButton,
  PageHeader,
  Pagination,
  Skeleton,
  Table,
  TableSkeleton,
  tdCls,
} from '../components/ui';
import { MethodBadge, MonitorStatusBadge, SuccessBadge } from '../components/badges';

const PERIODS: Period[] = ['24h', '7d', '30d'];
const CHECKS_PAGE_SIZE = 15;

function PeriodSelector({ period, onChange }: { period: Period; onChange: (p: Period) => void }) {
  return (
    <div className="flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-700">
      {PERIODS.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onChange(p)}
          className={cx(
            'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            p === period
              ? 'bg-indigo-600 text-white'
              : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200',
          )}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/60">
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-slate-900 dark:text-white">{value}</p>
    </div>
  );
}

function tickFmt(iso: string, period: Period): string {
  const d = new Date(iso);
  return period === '24h'
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function MonitorDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { dark } = useTheme();
  const colors = useChartColors(dark);

  const [period, setPeriod] = useState<Period>('24h');
  const [checksPage, setChecksPage] = useState(1);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const monitorQ = useQuery({
    queryKey: ['monitors', 'detail', id],
    queryFn: () => monitorsApi.get(id!),
    enabled: Boolean(id),
  });
  const metricsQ = useQuery({
    queryKey: ['monitors', 'metrics', id, period],
    queryFn: () => monitorsApi.metrics(id!, period),
    enabled: Boolean(id),
  });
  const checksQ = useQuery({
    queryKey: ['monitors', 'checks', id, checksPage],
    queryFn: () => monitorsApi.checks(id!, checksPage, CHECKS_PAGE_SIZE),
    enabled: Boolean(id),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['monitors'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const pauseMut = useMutation({
    mutationFn: () => (monitorQ.data?.active ? monitorsApi.pause(id!) : monitorsApi.resume(id!)),
    onSuccess: (m) => {
      toast.success(m.active ? `Resumed "${m.name}"` : `Paused "${m.name}"`);
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to update monitor')),
  });

  const testMut = useMutation({
    mutationFn: () => monitorsApi.test(id!),
    onSuccess: (check) => {
      toast.toast(
        check.success
          ? `Responded with ${check.status_code} in ${Math.round(check.response_time_ms)} ms`
          : `Check failed${check.error ? `: ${check.error}` : ''}`,
        check.success ? 'success' : 'error',
      );
      invalidate();
      checksQ.refetch();
      metricsQ.refetch();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Test failed')),
  });

  const deleteMut = useMutation({
    mutationFn: () => monitorsApi.remove(id!),
    onSuccess: () => {
      toast.success('API deleted');
      queryClient.invalidateQueries({ queryKey: ['monitors'] });
      navigate('/monitors');
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to delete API')),
  });

  if (monitorQ.isPending) {
    return (
      <div>
        <PageHeader title="API details" />
        <Card className="space-y-4 p-6">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-5 w-2/3" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        </Card>
      </div>
    );
  }

  if (monitorQ.isError || !monitorQ.data) {
    return (
      <div>
        <PageHeader title="API details" />
        <Card>
          <ErrorState
            message={getErrorMessage(monitorQ.error, 'API not found')}
            onRetry={() => monitorQ.refetch()}
          />
        </Card>
      </div>
    );
  }

  const m = monitorQ.data;
  const metrics = metricsQ.data;

  const distData = metrics
    ? Object.entries(metrics.status_code_distribution).map(([k, v]) => ({
        name: k,
        value: v,
        color:
          k === '2xx' ? colors.healthy
          : k === '3xx' ? '#38bdf8'
          : k === '4xx' ? colors.degraded
          : k === '5xx' ? colors.down
          : '#a855f7',
      }))
    : [];

  return (
    <div>
      <PageHeader
        title={m.name}
        subtitle={m.url}
        actions={
          <>
            <Link to="/monitors">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="h-4 w-4" /> All APIs
              </Button>
            </Link>
            <Link to={`/monitors/${m.id}/edit`}>
              <Button variant="outline" size="sm">
                <Pencil className="h-4 w-4" /> Edit
              </Button>
            </Link>
            <Button variant="outline" size="sm" onClick={() => pauseMut.mutate()} disabled={pauseMut.isPending}>
              {m.active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {m.active ? 'Pause' : 'Resume'}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
              <FlaskConical className="h-4 w-4" /> Test now
            </Button>
            <IconButton
              title="Delete API"
              onClick={() => setConfirmDelete(true)}
              className="border border-red-200 text-red-600 hover:!bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:!bg-red-950"
            >
              <Trash2 className="h-4 w-4" />
            </IconButton>
          </>
        }
      />

      {/* Status + info */}
      <Card className="mb-4 p-6">
        <div className="flex flex-wrap items-center gap-3">
          <MethodBadge method={m.method} />
          <MonitorStatusBadge status={m.status} />
          {!m.active && (
            <span className="text-xs text-slate-500 dark:text-slate-400">Monitoring paused</span>
          )}
        </div>
        {m.description && (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{m.description}</p>
        )}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCell label="Uptime (24h)" value={formatPercent(m.uptime_24h)} />
          <MetricCell label="Check interval" value={intervalLabel(m.interval)} />
          <MetricCell label="Timeout" value={`${m.timeout}s`} />
          <MetricCell label="Expected status" value={String(m.expected_status)} />
          <MetricCell label="Last checked" value={formatRelative(m.last_checked_at)} />
          <MetricCell label="Consecutive failures" value={String(m.consecutive_failures)} />
          <MetricCell label="Consecutive successes" value={String(m.consecutive_successes)} />
          <MetricCell label="Created" value={formatRelative(m.created_at)} />
        </div>
      </Card>

      {/* Metrics */}
      <Card className="mb-4">
        <CardHeader
          title="Performance metrics"
          subtitle="Aggregated over the selected period"
          action={<PeriodSelector period={period} onChange={setPeriod} />}
        />
        {metricsQ.isPending ? (
          <div className="grid grid-cols-2 gap-3 p-6 sm:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : metricsQ.isError ? (
          <ErrorState message={getErrorMessage(metricsQ.error)} onRetry={() => metricsQ.refetch()} />
        ) : (
          <div className="grid grid-cols-2 gap-3 p-6 sm:grid-cols-4">
            <MetricCell label="Uptime" value={formatPercent(metrics!.uptime_percent)} />
            <MetricCell label="Avg latency" value={formatMs(metrics!.avg_latency_ms, 1)} />
            <MetricCell label="Min latency" value={formatMs(metrics!.min_latency_ms)} />
            <MetricCell label="Max latency" value={formatMs(metrics!.max_latency_ms)} />
            <MetricCell label="p50 latency" value={formatMs(metrics!.p50_latency_ms)} />
            <MetricCell label="p95 latency" value={formatMs(metrics!.p95_latency_ms)} />
            <MetricCell label="p99 latency" value={formatMs(metrics!.p99_latency_ms)} />
            <MetricCell label="Error rate" value={formatPercent(metrics!.error_rate_percent)} />
            <MetricCell label="Total checks" value={String(metrics!.total_checks)} />
            <MetricCell label="Successful" value={String(metrics!.successful_checks)} />
            <MetricCell label="Failed" value={String(metrics!.failed_checks)} />
          </div>
        )}
      </Card>

      {/* Charts */}
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Response time" subtitle={`Average latency — last ${period}`} />
          <div className="p-5">
            {metricsQ.isPending ? (
              <ChartSkeleton />
            ) : metricsQ.isError ? (
              <ErrorState message={getErrorMessage(metricsQ.error)} onRetry={() => metricsQ.refetch()} />
            ) : metrics!.response_time_series.length === 0 ? (
              <EmptyState title="No latency data" message="Run a check to collect data." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={metrics!.response_time_series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={(t: string) => tickFmt(t, period)} tick={{ fill: colors.tick, fontSize: 12 }} minTickGap={40} />
                    <YAxis tick={{ fill: colors.tick, fontSize: 12 }} tickFormatter={(v: number) => `${v}ms`} width={55} />
                    <Tooltip labelFormatter={(label: unknown) => formatDateTime(String(label ?? ''))} formatter={(value: unknown) => [`${Number(value ?? 0).toFixed(1)} ms`, 'Avg']} />
                    <Line type="monotone" dataKey="avg_ms" stroke={colors.latency} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>
        <Card>
          <CardHeader title="Uptime" subtitle={`Uptime percentage — last ${period}`} />
          <div className="p-5">
            {metricsQ.isPending ? (
              <ChartSkeleton />
            ) : metricsQ.isError ? (
              <ErrorState message={getErrorMessage(metricsQ.error)} onRetry={() => metricsQ.refetch()} />
            ) : metrics!.uptime_series.length === 0 ? (
              <EmptyState title="No uptime data" message="Run a check to collect data." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={metrics!.uptime_series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={(t: string) => tickFmt(t, period)} tick={{ fill: colors.tick, fontSize: 12 }} minTickGap={40} />
                    <YAxis domain={['auto', 100]} tick={{ fill: colors.tick, fontSize: 12 }} tickFormatter={(v: number) => `${v}%`} width={50} />
                    <Tooltip labelFormatter={(label: unknown) => formatDateTime(String(label ?? ''))} formatter={(value: unknown) => [`${Number(value ?? 0).toFixed(2)}%`, 'Uptime']} />
                    <Area type="monotone" dataKey="uptime" stroke={colors.uptime} fill={colors.uptime} fillOpacity={0.2} strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card className="mb-4">
        <CardHeader title="Status code distribution" subtitle={`Check outcomes — last ${period}`} />
        <div className="p-5">
          {metricsQ.isPending ? (
            <ChartSkeleton className="h-48" />
          ) : metricsQ.isError ? (
            <ErrorState message={getErrorMessage(metricsQ.error)} onRetry={() => metricsQ.refetch()} />
          ) : distData.every((d) => d.value === 0) ? (
            <EmptyState title="No check data" message="Run a check to collect data." />
          ) : (
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={distData} layout="vertical" margin={{ top: 0, right: 20, left: 20, bottom: 0 }}>
                  <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fill: colors.tick, fontSize: 12 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" tick={{ fill: colors.tick, fontSize: 12 }} width={110} />
                  <Tooltip formatter={(value: unknown) => [Number(value ?? 0), 'Checks']} />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {distData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </Card>

      {/* Check history */}
      <Card>
        <CardHeader title="Check history" subtitle="Newest first" />
        {checksQ.isPending ? (
          <TableSkeleton rows={8} cols={5} />
        ) : checksQ.isError ? (
          <ErrorState message={getErrorMessage(checksQ.error)} onRetry={() => checksQ.refetch()} />
        ) : checksQ.data.items.length === 0 ? (
          <EmptyState
            title="No checks yet"
            message="No check results recorded for this API. Run a manual test to record one."
            action={
              <Button size="sm" onClick={() => testMut.mutate()} disabled={testMut.isPending}>
                <FlaskConical className="h-4 w-4" /> Test now
              </Button>
            }
          />
        ) : (
          <>
            <Table headers={['Timestamp', 'Status code', 'Response time', 'Result', 'Error']}>
              {checksQ.data.items.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className={tdCls}>{formatDateTime(c.timestamp)}</td>
                  <td className={cx(tdCls, 'font-mono')}>{c.status_code ?? '—'}</td>
                  <td className={tdCls}>{formatMs(c.response_time_ms)}</td>
                  <td className={tdCls}>
                    <SuccessBadge success={c.success} />
                  </td>
                  <td className={cx(tdCls, 'max-w-64 truncate text-xs')} title={c.error ?? ''}>
                    {c.error ?? (c.timed_out ? 'Timed out' : '—')}
                  </td>
                </tr>
              ))}
            </Table>
            <Pagination
              page={checksQ.data.pagination.page}
              pages={checksQ.data.pagination.pages}
              total={checksQ.data.pagination.total}
              pageSize={CHECKS_PAGE_SIZE}
              onPage={setChecksPage}
            />
          </>
        )}
      </Card>

      <ConfirmModal
        open={confirmDelete}
        title="Delete API"
        message={`Delete "${m.name}"? All of its check history will be removed. This can't be undone.`}
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={() => deleteMut.mutate()}
        onClose={() => setConfirmDelete(false)}
      />
    </div>
  );
}
