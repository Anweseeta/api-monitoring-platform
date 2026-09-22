import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { AlertTriangle, Clock, Flag, Loader2, Plus, Search } from 'lucide-react';
import { getErrorMessage, incidentsApi, monitorsApi } from '../lib/api';
import { useDebounce } from '../hooks/useDebounce';
import { useToast } from '../lib/toast';
import { cx, formatDateTime, formatDuration, formatRelative } from '../lib/utils';
import type { IncidentSeverity, IncidentStatus } from '../types';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  PageHeader,
  Pagination,
  StatCard,
  Table,
  TableSkeleton,
  inputCls,
  tdCls,
} from '../components/ui';
import { IncidentStatusBadge, SeverityBadge } from '../components/badges';

const STATUS_FILTERS: Array<{ value: IncidentStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'identified', label: 'Identified' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'resolved', label: 'Resolved' },
];

const SEVERITY_FILTERS: Array<{ value: IncidentSeverity | ''; label: string }> = [
  { value: '', label: 'All severities' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const PAGE_SIZE = 15;

const newIncidentSchema = z.object({
  api_id: z.string().min(1, 'Choose an API'),
  title: z.string().min(1, 'Title is required').max(200),
  description: z.string().max(1000),
  severity: z.enum(['low', 'medium', 'high', 'critical']),
});

type NewIncidentValues = z.infer<typeof newIncidentSchema>;

export default function IncidentsList() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<IncidentStatus | ''>('');
  const [severity, setSeverity] = useState<IncidentSeverity | ''>('');
  const [apiId, setApiId] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const [showNew, setShowNew] = useState(false);

  const debouncedSearch = useDebounce(search, 400);

  const query = useQuery({
    queryKey: ['incidents', 'list', debouncedSearch, status, severity, apiId, from, to, page],
    queryFn: () =>
      incidentsApi.list({
        search: debouncedSearch,
        status,
        severity,
        api_id: apiId || undefined,
        from: from || undefined,
        to: to || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const monitorsQ = useQuery({
    queryKey: ['monitors', 'names'],
    queryFn: () => monitorsApi.list({ page: 1, page_size: 100 }),
  });

  const apiNames = useMemo(() => {
    const map = new Map<string, string>();
    monitorsQ.data?.items.forEach((m) => map.set(m.id, m.name));
    return map;
  }, [monitorsQ.data]);

  const {
    register: newRegister,
    handleSubmit: newSubmit,
    reset: newReset,
    formState: { errors: newErrors, isSubmitting: newSubmitting },
  } = useForm<NewIncidentValues>({
    resolver: zodResolver(newIncidentSchema),
    defaultValues: { api_id: '', title: '', description: '', severity: 'high' },
  });

  const createMut = useMutation({
    mutationFn: (v: NewIncidentValues) =>
      incidentsApi.create({
        api_id: v.api_id,
        title: v.title,
        description: v.description || undefined,
        severity: v.severity,
      }),
    onSuccess: (inc) => {
      toast.success(`Incident "${inc.title}" created`);
      setShowNew(false);
      newReset();
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to create incident')),
  });

  const resetPage = () => setPage(1);
  const hasFilters =
    search !== '' || status !== '' || severity !== '' || apiId !== '' || from !== '' || to !== '';
  const clearFilters = () => {
    setSearch('');
    setStatus('');
    setSeverity('');
    setApiId('');
    setFrom('');
    setTo('');
    resetPage();
  };

  const summary = query.data?.summary;

  return (
    <div>
      <PageHeader
        title="Incidents"
        subtitle="Track and resolve API outages"
        actions={
          <Button onClick={() => setShowNew(true)}>
            <Plus className="h-4 w-4" /> Report incident
          </Button>
        }
      />

      {/* Summary cards */}
      {query.isPending ? (
        <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="p-5">
              <div className="h-4 w-20 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
              <div className="mt-3 h-8 w-12 animate-pulse rounded bg-slate-200 dark:bg-slate-800" />
            </Card>
          ))}
        </div>
      ) : query.isError ? (
        <Card>
          <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
        </Card>
      ) : (
        summary && (
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-5">
            <StatCard icon={Flag} label="Total" value={String(summary.total)} />
            <StatCard
              icon={AlertTriangle}
              label="Open"
              value={String(summary.open)}
              accent="bg-red-100 text-red-600 dark:bg-red-950 dark:text-red-400"
            />
            <StatCard
              icon={Clock}
              label="Avg resolution"
              value={formatDuration(summary.avg_resolution_seconds)}
              accent="bg-sky-100 text-sky-600 dark:bg-sky-950 dark:text-sky-400"
            />
            <StatCard
              icon={AlertTriangle}
              label="Critical"
              value={String(summary.critical)}
              accent="bg-orange-100 text-orange-600 dark:bg-orange-950 dark:text-orange-400"
            />
            <StatCard
              icon={Flag}
              label="Resolved"
              value={String(summary.resolved)}
              accent="bg-emerald-100 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400"
            />
          </div>
        )
      )}

      {/* Filters */}
      <Card className="mb-4 mt-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <div className="relative xl:col-span-2">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              placeholder="Search incidents…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
              className={cx(inputCls, 'pl-9')}
              aria-label="Search incidents"
            />
          </div>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as IncidentStatus | '');
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by status"
          >
            {STATUS_FILTERS.map((f) => (
              <option key={f.label} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value as IncidentSeverity | '');
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by severity"
          >
            {SEVERITY_FILTERS.map((f) => (
              <option key={f.label} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <select
            value={apiId}
            onChange={(e) => {
              setApiId(e.target.value);
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by API"
          >
            <option value="">All APIs</option>
            {monitorsQ.data?.items.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="date"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
                resetPage();
              }}
              className={inputCls}
              aria-label="From date"
            />
            <input
              type="date"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                resetPage();
              }}
              className={inputCls}
              aria-label="To date"
            />
          </div>
        </div>
        {hasFilters && (
          <div className="mt-3">
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Clear filters
            </Button>
          </div>
        )}
      </Card>

      {/* Table */}
      <Card>
        {query.isPending ? (
          <TableSkeleton rows={8} cols={6} />
        ) : query.isError ? (
          <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
        ) : query.data.items.length === 0 ? (
          <EmptyState
            icon={AlertTriangle}
            title="No incidents"
            message={
              hasFilters
                ? 'No incidents match your filters. Try widening the search.'
                : 'No incidents detected. When an API goes down, it will show up here.'
            }
          />
        ) : (
          <>
            <Table headers={['Title', 'API', 'Status', 'Severity', 'Started', 'Duration']}>
              {query.data.items.map((inc) => (
                <tr key={inc.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className={tdCls}>
                    <Link
                      to={`/incidents/${inc.id}`}
                      className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                    >
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
                  <td className={tdCls} title={formatDateTime(inc.started_at)}>
                    {formatRelative(inc.started_at)}
                  </td>
                  <td className={tdCls}>
                    {formatDuration(
                      inc.duration_seconds ??
                        (inc.resolved_at
                          ? null
                          : (Date.now() - new Date(inc.started_at).getTime()) / 1000),
                    )}
                  </td>
                </tr>
              ))}
            </Table>
            <Pagination
              page={query.data.pagination.page}
              pages={query.data.pagination.pages}
              total={query.data.pagination.total}
              pageSize={PAGE_SIZE}
              onPage={setPage}
            />
          </>
        )}
      </Card>

      {/* New incident modal */}
      <Modal open={showNew} title="Report incident" onClose={() => setShowNew(false)}>
        <form onSubmit={newSubmit((v) => createMut.mutate(v))} className="space-y-4" noValidate>
          <Field label="API" error={newErrors.api_id?.message} htmlFor="ni-api">
            <select id="ni-api" className={inputCls} {...newRegister('api_id')}>
              <option value="">Select an API…</option>
              {monitorsQ.data?.items.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Title" error={newErrors.title?.message} htmlFor="ni-title">
            <input
              id="ni-title"
              placeholder="Payments API is returning 500s"
              className={inputCls}
              {...newRegister('title')}
            />
          </Field>
          <Field label="Description" error={newErrors.description?.message} htmlFor="ni-desc">
            <textarea id="ni-desc" rows={3} className={inputCls} {...newRegister('description')} />
          </Field>
          <Field label="Severity" error={newErrors.severity?.message} htmlFor="ni-sev">
            <select id="ni-sev" className={inputCls} {...newRegister('severity')}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setShowNew(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={newSubmitting || createMut.isPending}>
              {(newSubmitting || createMut.isPending) && <Loader2 className="h-4 w-4 animate-spin" />}
              Create incident
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
