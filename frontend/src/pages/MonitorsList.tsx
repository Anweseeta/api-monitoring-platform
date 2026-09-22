import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Eye,
  FlaskConical,
  Pause,
  Pencil,
  Play,
  Plus,
  Search,
  Server,
  Trash2,
} from 'lucide-react';
import { getErrorMessage, monitorsApi } from '../lib/api';
import { useDebounce } from '../hooks/useDebounce';
import { useToast } from '../lib/toast';
import { cx, formatPercent, formatRelative, intervalLabel, shortUrl } from '../lib/utils';
import { METHOD_OPTIONS } from '../lib/utils';
import type { HttpMethod, Monitor, MonitorStatus } from '../types';
import {
  Button,
  Card,
  ConfirmModal,
  EmptyState,
  ErrorState,
  IconButton,
  PageHeader,
  Pagination,
  Table,
  TableSkeleton,
  inputCls,
  tdCls,
} from '../components/ui';
import { MethodBadge, MonitorStatusBadge } from '../components/badges';

const STATUS_FILTERS: Array<{ value: MonitorStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'healthy', label: 'Healthy' },
  { value: 'degraded', label: 'Degraded' },
  { value: 'down', label: 'Down' },
  { value: 'paused', label: 'Paused' },
];

const PAGE_SIZE = 15;

export default function MonitorsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<MonitorStatus | ''>('');
  const [method, setMethod] = useState<HttpMethod | ''>('');
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<Monitor | null>(null);

  const debouncedSearch = useDebounce(search, 400);

  const query = useQuery({
    queryKey: ['monitors', 'list', debouncedSearch, status, method, page],
    queryFn: () =>
      monitorsApi.list({
        search: debouncedSearch,
        status,
        method,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['monitors'] });

  const pauseMut = useMutation({
    mutationFn: (m: Monitor) => (m.active ? monitorsApi.pause(m.id) : monitorsApi.resume(m.id)),
    onSuccess: (m) => {
      toast.success(m.active ? `Resumed "${m.name}"` : `Paused "${m.name}"`);
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to update monitor')),
  });

  const testMut = useMutation({
    mutationFn: (m: Monitor) => monitorsApi.test(m.id),
    onSuccess: (check, m) => {
      toast.toast(
        check.success
          ? `"${m.name}" responded with ${check.status_code} in ${Math.round(check.response_time_ms)} ms`
          : `"${m.name}" check failed${check.error ? `: ${check.error}` : ''}`,
        check.success ? 'success' : 'error',
      );
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Test failed')),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => monitorsApi.remove(id),
    onSuccess: () => {
      toast.success('API deleted');
      setDeleteTarget(null);
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to delete API')),
  });

  const resetPage = () => setPage(1);
  const hasFilters = search !== '' || status !== '' || method !== '';

  return (
    <div>
      <PageHeader
        title="APIs"
        subtitle="All monitored endpoints"
        actions={
          <Button onClick={() => navigate('/monitors/new')}>
            <Plus className="h-4 w-4" /> Add API
          </Button>
        }
      />

      {/* Filters */}
      <Card className="mb-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              placeholder="Search name or URL…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
              className={cx(inputCls, 'pl-9')}
              aria-label="Search APIs"
            />
          </div>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as MonitorStatus | '');
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
            value={method}
            onChange={(e) => {
              setMethod(e.target.value as HttpMethod | '');
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by method"
          >
            <option value="">All methods</option>
            {METHOD_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          {hasFilters && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch('');
                setStatus('');
                setMethod('');
                resetPage();
              }}
            >
              Clear filters
            </Button>
          )}
        </div>
      </Card>

      {/* Table */}
      <Card>
        {query.isPending ? (
          <TableSkeleton rows={8} cols={7} />
        ) : query.isError ? (
          <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
        ) : query.data.items.length === 0 ? (
          <EmptyState
            icon={Server}
            title="No APIs configured yet"
            message={
              hasFilters
                ? 'No APIs match your filters. Try widening the search.'
                : 'Add your first API to start monitoring uptime, latency and incidents.'
            }
            action={
              !hasFilters ? (
                <Button onClick={() => navigate('/monitors/new')}>
                  <Plus className="h-4 w-4" /> Add your first API
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <Table headers={['Name', 'URL', 'Method', 'Status', 'Uptime 24h', 'Last checked', 'Interval', 'Actions']}>
              {query.data.items.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className={tdCls}>
                    <Link
                      to={`/monitors/${m.id}`}
                      className="font-medium text-slate-900 hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-400"
                    >
                      {m.name}
                    </Link>
                  </td>
                  <td className={cx(tdCls, 'max-w-56 truncate font-mono text-xs')} title={m.url}>
                    {shortUrl(m.url)}
                  </td>
                  <td className={tdCls}>
                    <MethodBadge method={m.method} />
                  </td>
                  <td className={tdCls}>
                    <MonitorStatusBadge status={m.status} />
                  </td>
                  <td className={tdCls}>{formatPercent(m.uptime_24h)}</td>
                  <td className={tdCls}>{formatRelative(m.last_checked_at)}</td>
                  <td className={tdCls}>{intervalLabel(m.interval)}</td>
                  <td className={tdCls}>
                    <div className="flex items-center gap-0.5">
                      <IconButton title="View details" onClick={() => navigate(`/monitors/${m.id}`)}>
                        <Eye className="h-4 w-4" />
                      </IconButton>
                      <IconButton title="Edit" onClick={() => navigate(`/monitors/${m.id}/edit`)}>
                        <Pencil className="h-4 w-4" />
                      </IconButton>
                      <IconButton
                        title={m.active ? 'Pause monitoring' : 'Resume monitoring'}
                        onClick={() => pauseMut.mutate(m)}
                        disabled={pauseMut.isPending}
                      >
                        {m.active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                      </IconButton>
                      <IconButton
                        title="Test now"
                        onClick={() => testMut.mutate(m)}
                        disabled={testMut.isPending}
                      >
                        <FlaskConical className="h-4 w-4" />
                      </IconButton>
                      <IconButton
                        title="Delete"
                        onClick={() => setDeleteTarget(m)}
                        className="hover:!bg-red-50 hover:!text-red-600 dark:hover:!bg-red-950 dark:hover:!text-red-400"
                      >
                        <Trash2 className="h-4 w-4" />
                      </IconButton>
                    </div>
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

      <ConfirmModal
        open={deleteTarget !== null}
        title="Delete API"
        message={`Delete "${deleteTarget?.name}"? All of its check history will be removed. This can't be undone.`}
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}
