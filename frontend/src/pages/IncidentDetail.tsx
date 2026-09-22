import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FilePlus2,
  Loader2,
  MessageSquare,
  Pencil,
  TrendingUp,
  Trash2,
  Zap,
} from 'lucide-react';
import { getErrorMessage, incidentsApi } from '../lib/api';
import { useToast } from '../lib/toast';
import { cx, formatDateTime, formatDuration, formatRelative } from '../lib/utils';
import type { IncidentEvent, IncidentSeverity, IncidentStatus } from '../types';
import {
  Button,
  Card,
  CardHeader,
  ConfirmModal,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  PageHeader,
  Skeleton,
  inputCls,
} from '../components/ui';
import { IncidentStatusBadge, SeverityBadge } from '../components/badges';

const editSchema = z.object({
  status: z.enum(['open', 'investigating', 'identified', 'monitoring', 'resolved']),
  severity: z.enum(['low', 'medium', 'high', 'critical']),
  root_cause: z.string().max(2000),
  resolution_notes: z.string().max(2000),
});

type EditValues = z.infer<typeof editSchema>;

const EVENT_ICONS: Record<IncidentEvent['event_type'], typeof Zap> = {
  detected: AlertTriangle,
  created: FilePlus2,
  updated: Pencil,
  resolved: CheckCircle2,
  note: MessageSquare,
  auto_resolved: Zap,
  escalated: TrendingUp,
};

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <div className="mt-1 text-sm text-slate-900 dark:text-slate-100">{children}</div>
    </div>
  );
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const query = useQuery({
    queryKey: ['incidents', 'detail', id],
    queryFn: () => incidentsApi.get(id!),
    enabled: Boolean(id),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: { status: 'open', severity: 'medium', root_cause: '', resolution_notes: '' },
  });

  useEffect(() => {
    if (query.data) {
      const inc = query.data.incident;
      reset({
        status: inc.status,
        severity: inc.severity,
        root_cause: inc.root_cause ?? '',
        resolution_notes: inc.resolution_notes ?? '',
      });
    }
  }, [query.data, reset]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['incidents'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const updateMut = useMutation({
    mutationFn: (v: EditValues) =>
      incidentsApi.update(id!, {
        status: v.status as IncidentStatus,
        severity: v.severity as IncidentSeverity,
        root_cause: v.root_cause,
        resolution_notes: v.resolution_notes,
      }),
    onSuccess: () => {
      toast.success('Incident updated');
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to update incident')),
  });

  const resolveMut = useMutation({
    mutationFn: (notes?: string) => incidentsApi.resolve(id!, notes),
    onSuccess: () => {
      toast.success('Incident resolved');
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to resolve incident')),
  });

  const deleteMut = useMutation({
    mutationFn: () => incidentsApi.remove(id!),
    onSuccess: () => {
      toast.success('Incident deleted');
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      navigate('/incidents');
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to delete incident')),
  });

  if (query.isPending) {
    return (
      <div>
        <PageHeader title="Incident" />
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Card className="space-y-4 p-6 xl:col-span-2">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-40 w-full" />
          </Card>
          <Card className="space-y-3 p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </Card>
        </div>
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div>
        <PageHeader title="Incident" />
        <Card>
          <ErrorState
            message={getErrorMessage(query.error, 'Incident not found')}
            onRetry={() => query.refetch()}
          />
        </Card>
      </div>
    );
  }

  const { incident: inc, api, events } = query.data;
  const isResolved = inc.status === 'resolved';

  return (
    <div>
      <PageHeader
        title={inc.title}
        subtitle={`Opened ${formatRelative(inc.started_at)} · ${inc.created_by === 'system' ? 'auto-detected' : 'reported manually'}`}
        actions={
          <>
            <Link to="/incidents">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="h-4 w-4" /> All incidents
              </Button>
            </Link>
            {!isResolved && (
              <Button
                size="sm"
                onClick={() => resolveMut.mutate(inc.resolution_notes || undefined)}
                disabled={resolveMut.isPending}
              >
                {resolveMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                <CheckCircle2 className="h-4 w-4" /> Resolve
              </Button>
            )}
            <IconButton
              title="Delete incident"
              onClick={() => setConfirmDelete(true)}
              className="border border-red-200 text-red-600 hover:!bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:!bg-red-950"
            >
              <Trash2 className="h-4 w-4" />
            </IconButton>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Main column */}
        <div className="space-y-4 xl:col-span-2">
          <Card className="p-6">
            <div className="flex flex-wrap items-center gap-2">
              <IncidentStatusBadge status={inc.status} />
              <SeverityBadge severity={inc.severity} />
            </div>
            <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2">
              <InfoRow label="API">
                {api ? (
                  <Link to={`/monitors/${api.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                    {api.name}
                  </Link>
                ) : (
                  '—'
                )}
              </InfoRow>
              <InfoRow label="Detected at">{formatDateTime(inc.detected_at)}</InfoRow>
              <InfoRow label="Started at">{formatDateTime(inc.started_at)}</InfoRow>
              <InfoRow label="Resolved at">
                {inc.resolved_at ? formatDateTime(inc.resolved_at) : '—'}
              </InfoRow>
              <InfoRow label="Duration">
                {formatDuration(
                  inc.duration_seconds ??
                    (inc.resolved_at ? null : (Date.now() - new Date(inc.started_at).getTime()) / 1000),
                )}
              </InfoRow>
              <InfoRow label="Reported by">{inc.created_by}</InfoRow>
            </div>
            {inc.description && (
              <div className="mt-5">
                <InfoRow label="Description">
                  <p className="whitespace-pre-wrap">{inc.description}</p>
                </InfoRow>
              </div>
            )}
            {inc.root_cause && (
              <div className="mt-5 rounded-lg bg-amber-50 p-4 dark:bg-amber-950/40">
                <p className="text-xs font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">
                  Root cause
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-amber-900 dark:text-amber-200">
                  {inc.root_cause}
                </p>
              </div>
            )}
            {inc.resolution_notes && (
              <div className="mt-4 rounded-lg bg-emerald-50 p-4 dark:bg-emerald-950/40">
                <p className="text-xs font-medium uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                  Resolution notes
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-emerald-900 dark:text-emerald-200">
                  {inc.resolution_notes}
                </p>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader title="Timeline" subtitle="Every event recorded for this incident" />
            {events.length === 0 ? (
              <EmptyState title="No events yet" message="Events will appear as the incident evolves." />
            ) : (
              <ol className="relative space-y-6 px-6 py-6">
                {events.map((e) => {
                  const Icon = EVENT_ICONS[e.event_type] ?? MessageSquare;
                  return (
                    <li key={e.id} className="relative flex gap-4 pl-2">
                      <span className="absolute -left-0 top-8 h-full w-px bg-slate-200 dark:bg-slate-700" aria-hidden />
                      <div className="z-10 -ml-2 rounded-full border border-slate-200 bg-white p-1.5 dark:border-slate-700 dark:bg-slate-900">
                        <Icon className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                      </div>
                      <div className="min-w-0 flex-1 pb-1">
                        <p className="text-sm text-slate-800 dark:text-slate-200">{e.message}</p>
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                          {e.event_type.replace('_', ' ')} · {formatDateTime(e.timestamp)}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>

        {/* Edit panel */}
        <div>
          <Card className="p-6 lg:sticky lg:top-20">
            <h3 className="mb-4 text-sm font-semibold text-slate-900 dark:text-white">
              Update incident
            </h3>
            <form onSubmit={handleSubmit((v) => updateMut.mutate(v))} className="space-y-4" noValidate>
              <Field label="Status" error={errors.status?.message} htmlFor="ed-status">
                <select id="ed-status" className={inputCls} {...register('status')}>
                  <option value="open">Open</option>
                  <option value="investigating">Investigating</option>
                  <option value="identified">Identified</option>
                  <option value="monitoring">Monitoring</option>
                  <option value="resolved">Resolved</option>
                </select>
              </Field>
              <Field label="Severity" error={errors.severity?.message} htmlFor="ed-severity">
                <select id="ed-severity" className={inputCls} {...register('severity')}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </Field>
              <Field label="Root cause" error={errors.root_cause?.message} htmlFor="ed-cause">
                <textarea
                  id="ed-cause"
                  rows={3}
                  placeholder="What caused the outage?"
                  className={inputCls}
                  {...register('root_cause')}
                />
              </Field>
              <Field label="Resolution notes" error={errors.resolution_notes?.message} htmlFor="ed-notes">
                <textarea
                  id="ed-notes"
                  rows={3}
                  placeholder="How was it fixed?"
                  className={inputCls}
                  {...register('resolution_notes')}
                />
              </Field>
              <Button type="submit" className="w-full" disabled={isSubmitting || updateMut.isPending}>
                {(isSubmitting || updateMut.isPending) && <Loader2 className="h-4 w-4 animate-spin" />}
                Save changes
              </Button>
              {!isResolved && (
                <p className={cx('text-center text-xs text-slate-500 dark:text-slate-400')}>
                  Setting status to <span className="font-medium">Resolved</span> stamps the
                  resolution time.
                </p>
              )}
            </form>
          </Card>
        </div>
      </div>

      <ConfirmModal
        open={confirmDelete}
        title="Delete incident"
        message={`Delete "${inc.title}"? This can't be undone.`}
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={() => deleteMut.mutate()}
        onClose={() => setConfirmDelete(false)}
      />
    </div>
  );
}
