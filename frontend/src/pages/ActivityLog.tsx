import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ScrollText, Search } from 'lucide-react';
import { activityApi, getErrorMessage } from '../lib/api';
import { cx, formatDateTime, formatRelative, titleCase } from '../lib/utils';
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Table,
  TableSkeleton,
  inputCls,
  tdCls,
} from '../components/ui';

const ACTIONS = [
  'user.registered',
  'user.logged_in',
  'api.created',
  'api.updated',
  'api.deleted',
  'api.paused',
  'api.resumed',
  'api.tested',
  'incident.created',
  'incident.updated',
  'incident.resolved',
  'incident.auto_created',
  'incident.auto_resolved',
  'settings.updated',
  'webhook.created',
  'webhook.deleted',
];

const RESOURCE_TYPES = ['user', 'api', 'incident', 'settings', 'webhook'];

const PAGE_SIZE = 20;

function actionChip(action: string) {
  const color = action.startsWith('incident')
    ? 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300'
    : action.startsWith('api')
      ? 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300'
      : action.startsWith('user')
        ? 'bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300'
        : action.startsWith('webhook')
          ? 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
          : 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
  return (
    <span className={cx('inline-flex rounded-full px-2.5 py-0.5 font-mono text-xs font-medium', color)}>
      {action}
    </span>
  );
}

export default function ActivityLog() {
  const [resourceType, setResourceType] = useState('');
  const [action, setAction] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ['activity', resourceType, action, page],
    queryFn: () =>
      activityApi.list({
        resource_type: resourceType || undefined,
        action: action || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return query.data?.items ?? [];
    return (query.data?.items ?? []).filter(
      (e) =>
        e.resource_name.toLowerCase().includes(q) ||
        e.action.toLowerCase().includes(q) ||
        e.resource_type.toLowerCase().includes(q),
    );
  }, [query.data, search]);

  const resetPage = () => setPage(1);

  return (
    <div>
      <PageHeader title="Activity logs" subtitle="Audit trail of everything happening in the workspace" />

      <Card className="mb-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              placeholder="Search resource or action…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={cx(inputCls, 'pl-9')}
              aria-label="Search activity"
            />
          </div>
          <select
            value={resourceType}
            onChange={(e) => {
              setResourceType(e.target.value);
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by resource type"
          >
            <option value="">All resource types</option>
            {RESOURCE_TYPES.map((r) => (
              <option key={r} value={r}>
                {titleCase(r)}
              </option>
            ))}
          </select>
          <select
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              resetPage();
            }}
            className={inputCls}
            aria-label="Filter by action"
          >
            <option value="">All actions</option>
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
      </Card>

      <Card>
        {query.isPending ? (
          <TableSkeleton rows={10} cols={5} />
        ) : query.isError ? (
          <ErrorState message={getErrorMessage(query.error)} onRetry={() => query.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={ScrollText}
            title="No activity found"
            message="Activity across the workspace — logins, API changes, incidents — will be listed here."
          />
        ) : (
          <>
            <Table headers={['Timestamp', 'Action', 'Resource', 'Name', 'IP']}>
              {items.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className={tdCls} title={formatDateTime(e.timestamp)}>
                    {formatRelative(e.timestamp)}
                  </td>
                  <td className={tdCls}>{actionChip(e.action)}</td>
                  <td className={tdCls}>{titleCase(e.resource_type)}</td>
                  <td className={cx(tdCls, 'max-w-56 truncate')} title={e.resource_name}>
                    {e.resource_name || '—'}
                  </td>
                  <td className={cx(tdCls, 'font-mono text-xs')}>{e.ip || '—'}</td>
                </tr>
              ))}
            </Table>
            <Pagination
              page={query.data!.pagination.page}
              pages={query.data!.pagination.pages}
              total={query.data!.pagination.total}
              pageSize={PAGE_SIZE}
              onPage={setPage}
            />
          </>
        )}
      </Card>

      {search.trim() !== '' && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Text search filters the entries on this page. Use the dropdowns for server-side filtering.
        </p>
      )}
    </div>
  );
}
