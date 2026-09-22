import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Server,
  Zap,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { dashboardApi, getErrorMessage, monitorsApi } from '../lib/api';
import { useChartColors, useTheme } from '../hooks/useTheme';
import { cx, formatDateTime, formatMs, formatPercent, formatRelative, titleCase } from '../lib/utils';
import type { Period } from '../types';
import {
  Button,
  Card,
  CardGridSkeleton,
  CardHeader,
  ChartSkeleton,
  EmptyState,
  ErrorState,
  PageHeader,
  StatCard,
  Table,
  TableSkeleton,
  tdCls,
} from '../components/ui';
import { IncidentStatusBadge, SeverityBadge } from '../components/badges';

const PERIODS: Period[] = ['24h', '7d', '30d'];

function formatTick(iso: string, period: Period): string {
  const d = new Date(iso);
  if (period === '24h') {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

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

export default function Dashboard() {
  const [period, setPeriod] = useState<Period>('24h');
  const { dark } = useTheme();
  const colors = useChartColors(dark);

  const summary = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: dashboardApi.summary,
  });
  const uptime = useQuery({
    queryKey: ['dashboard', 'uptime', period],
    queryFn: () => dashboardApi.uptime(period),
  });
  const latency = useQuery({
    queryKey: ['dashboard', 'latency', period],
    queryFn: () => dashboardApi.latency(period),
  });
  const incidentsTrend = useQuery({
    queryKey: ['dashboard', 'incidents', period],
    queryFn: () => dashboardApi.incidents(period),
  });
  const monitors = useQuery({
    queryKey: ['monitors', 'names'],
    queryFn: () => monitorsApi.list({ page: 1, page_size: 100 }),
  });

  const apiNames = useMemo(() => {
    const map = new Map<string, string>();
    monitors.data?.items.forEach((m) => map.set(m.id, m.name));
    return map;
  }, [monitors.data]);

  const healthData = useMemo(() => {
    const h = summary.data?.health_overview;
    if (!h) return [];
    return [
      { name: 'Healthy', value: h.healthy, color: colors.healthy },
      { name: 'Degraded', value: h.degraded, color: colors.degraded },
      { name: 'Down', value: h.down, color: colors.down },
      { name: 'Paused', value: h.paused, color: colors.paused },
    ].filter((d) => d.value > 0);
  }, [summary.data, colors]);

  const s = summary.data;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Live overview of your monitored APIs"
        actions={
          <Link to="/monitors/new">
            <Button>Add API</Button>
          </Link>
        }
      />

      {/* Summary cards */}
      {summary.isPending ? (
        <CardGridSkeleton count={5} />
      ) : summary.isError ? (
        <Card>
          <ErrorState message={getErrorMessage(summary.error)} onRetry={() => summary.refetch()} />
        </Card>
      ) : s ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard icon={Server} label="Total APIs" value={String(s.total_apis)} sub={`${s.paused_apis} paused`} />
          <StatCard
            icon={CheckCircle2}
            label="Healthy"
            value={String(s.healthy_apis)}
            sub={`${s.degraded_apis} degraded · ${s.down_apis} down`}
            accent="bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400"
          />
          <StatCard
            icon={Zap}
            label="Avg response time"
            value={formatMs(s.avg_response_time_ms)}
            sub="across all APIs"
            accent="bg-sky-100 text-sky-600 dark:bg-sky-950 dark:text-sky-400"
          />
          <StatCard
            icon={Activity}
            label="Uptime (24h)"
            value={formatPercent(s.overall_uptime_24h)}
            sub="overall"
            accent="bg-violet-100 text-violet-600 dark:bg-violet-950 dark:text-violet-400"
          />
          <StatCard
            icon={AlertTriangle}
            label="Open incidents"
            value={String(s.open_incidents)}
            sub={s.open_incidents > 0 ? 'needs attention' : 'all clear'}
            accent="bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400"
          />
        </div>
      ) : null}

      {/* Charts row 1 */}
      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-1">
          <CardHeader title="Health overview" subtitle="Current API status distribution" />
          <div className="p-5">
            {summary.isPending ? (
              <ChartSkeleton />
            ) : summary.isError ? (
              <ErrorState message={getErrorMessage(summary.error)} onRetry={() => summary.refetch()} />
            ) : healthData.length === 0 ? (
              <EmptyState title="No APIs yet" message="Add your first API to see the health overview." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={healthData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={3}>
                      {healthData.map((d) => (
                        <Cell key={d.name} fill={d.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value: unknown, name: unknown) => [Number(value ?? 0), String(name ?? '')]} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader
            title="Uptime trend"
            subtitle={`Overall uptime over the last ${period}`}
            action={<PeriodSelector period={period} onChange={setPeriod} />}
          />
          <div className="p-5">
            {uptime.isPending ? (
              <ChartSkeleton />
            ) : uptime.isError ? (
              <ErrorState message={getErrorMessage(uptime.error)} onRetry={() => uptime.refetch()} />
            ) : uptime.data.length === 0 ? (
              <EmptyState title="No uptime data" message="Check results will appear here once monitoring runs." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={uptime.data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={(t: string) => formatTick(t, period)}
                      tick={{ fill: colors.tick, fontSize: 12 }}
                      minTickGap={40}
                    />
                    <YAxis
                      domain={['auto', 100]}
                      tick={{ fill: colors.tick, fontSize: 12 }}
                      tickFormatter={(v: number) => `${v}%`}
                      width={50}
                    />
                    <Tooltip labelFormatter={(label: unknown) => formatDateTime(String(label ?? ''))} formatter={(value: unknown) => [`${Number(value ?? 0).toFixed(2)}%`, 'Uptime']} />
                    <Line type="monotone" dataKey="uptime" stroke={colors.uptime} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Charts row 2 */}
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Response time trend" subtitle={`Average latency over the last ${period}`} />
          <div className="p-5">
            {latency.isPending ? (
              <ChartSkeleton />
            ) : latency.isError ? (
              <ErrorState message={getErrorMessage(latency.error)} onRetry={() => latency.refetch()} />
            ) : latency.data.length === 0 ? (
              <EmptyState title="No latency data" message="Check results will appear here once monitoring runs." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={latency.data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={(t: string) => formatTick(t, period)}
                      tick={{ fill: colors.tick, fontSize: 12 }}
                      minTickGap={40}
                    />
                    <YAxis
                      tick={{ fill: colors.tick, fontSize: 12 }}
                      tickFormatter={(v: number) => `${v}ms`}
                      width={55}
                    />
                    <Tooltip labelFormatter={(label: unknown) => formatDateTime(String(label ?? ''))} formatter={(value: unknown) => [`${Number(value ?? 0).toFixed(1)} ms`, 'Avg latency']} />
                    <Line type="monotone" dataKey="avg_ms" stroke={colors.latency} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Incident trend" subtitle={`Created vs resolved over the last ${period}`} />
          <div className="p-5">
            {incidentsTrend.isPending ? (
              <ChartSkeleton />
            ) : incidentsTrend.isError ? (
              <ErrorState message={getErrorMessage(incidentsTrend.error)} onRetry={() => incidentsTrend.refetch()} />
            ) : incidentsTrend.data.length === 0 ? (
              <EmptyState title="No incident data" message="Incident activity will appear here." />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={incidentsTrend.data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={(t: string) => formatTick(t, period)}
                      tick={{ fill: colors.tick, fontSize: 12 }}
                      minTickGap={40}
                    />
                    <YAxis tick={{ fill: colors.tick, fontSize: 12 }} allowDecimals={false} width={35} />
                    <Tooltip labelFormatter={(label: unknown) => formatDateTime(String(label ?? ''))} />
                    <Legend />
                    <Bar dataKey="created" name="Created" fill={colors.created} radius={[3, 3, 0, 0]} />
                    <Bar dataKey="resolved" name="Resolved" fill={colors.resolved} radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Recent incidents"
            action={
              <Link to="/incidents" className="text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400">
                View all
              </Link>
            }
          />
          {summary.isPending ? (
            <TableSkeleton rows={5} cols={5} />
          ) : summary.isError ? (
            <ErrorState message={getErrorMessage(summary.error)} onRetry={() => summary.refetch()} />
          ) : (summary.data?.recent_incidents.length ?? 0) === 0 ? (
            <EmptyState title="No incidents" message="You're all clear — no incidents detected recently." />
          ) : (
            <Table headers={['Title', 'API', 'Status', 'Severity', 'Started']}>
              {summary.data!.recent_incidents.map((inc) => (
                <tr key={inc.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className={tdCls}>
                    <Link to={`/incidents/${inc.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      {inc.title}
                    </Link>
                  </td>
                  <td className={tdCls}>{apiNames.get(inc.api_id) ?? '—'}</td>
                  <td className={tdCls}>
                    <IncidentStatusBadge status={inc.status} />
                  </td>
                  <td className={tdCls}>
                    <SeverityBadge severity={inc.severity} />
                  </td>
                  <td className={tdCls}>{formatRelative(inc.started_at)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Recent activity"
            action={
              <Link to="/activity" className="text-sm font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400">
                View all
              </Link>
            }
          />
          {summary.isPending ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex gap-3">
                  <div className="h-8 w-8 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-4 w-3/4 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                    <div className="h-3 w-1/2 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
                  </div>
                </div>
              ))}
            </div>
          ) : summary.isError ? (
            <ErrorState message={getErrorMessage(summary.error)} onRetry={() => summary.refetch()} />
          ) : (summary.data?.recent_activity.length ?? 0) === 0 ? (
            <EmptyState title="No activity yet" message="Actions across the workspace will show up here." />
          ) : (
            <ul className="divide-y divide-slate-100 px-5 dark:divide-slate-800">
              {summary.data!.recent_activity.map((a) => (
                <li key={a.id} className="flex gap-3 py-3">
                  <div className="mt-0.5 rounded-full bg-slate-100 p-1.5 dark:bg-slate-800">
                    <Clock className="h-3.5 w-3.5 text-slate-500 dark:text-slate-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-800 dark:text-slate-200">
                      <span className="font-medium">{titleCase(a.action.replace(/\./g, ' '))}</span>
                      {a.resource_name ? ` — ${a.resource_name}` : ''}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{formatRelative(a.timestamp)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
