import { useEffect, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Loader2, Plus, Trash2, User, Webhook as WebhookIcon } from 'lucide-react';
import { getErrorMessage, settingsApi, webhooksApi } from '../lib/api';
import { useToast } from '../lib/toast';
import { INTERVAL_OPTIONS, WEBHOOK_EVENT_OPTIONS, cx, formatDateTime } from '../lib/utils';
import {
  Button,
  Card,
  CardHeader,
  ConfirmModal,
  EmptyState,
  ErrorState,
  Field,
  Modal,
  PageHeader,
  Skeleton,
  Toggle,
  inputCls,
} from '../components/ui';

// ---------------------------------------------------------------------------
// Settings form
// ---------------------------------------------------------------------------
const settingsSchema = z.object({
  profileName: z.string().min(1, 'Name is required').max(100),
  default_interval: z.number().refine((v) => INTERVAL_OPTIONS.includes(v), 'Invalid interval'),
  default_timeout: z.number().int().min(1, 'Min 1s').max(120, 'Max 120s'),
  failure_threshold: z.number().int().min(1, 'Min 1').max(20, 'Max 20'),
  recovery_threshold: z.number().int().min(1, 'Min 1').max(20, 'Max 20'),
  degraded_latency_ms: z.number().int().min(50, 'Min 50ms').max(60_000, 'Max 60000ms'),
  results_retention_days: z.number().int().min(1, 'Min 1 day').max(365, 'Max 365 days'),
  email_enabled: z.boolean(),
  webhook_enabled: z.boolean(),
});

type SettingsValues = z.infer<typeof settingsSchema>;

const webhookSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  url: z.string().min(1, 'URL is required').url('Enter a valid URL').refine(
    (u) => /^https?:\/\//i.test(u),
    'Only http(s) URLs are allowed',
  ),
  events: z.array(z.string()).min(1, 'Select at least one event'),
  active: z.boolean(),
});

type WebhookValues = z.infer<typeof webhookSchema>;

function SectionTitle({ icon: Icon, title, hint }: { icon: typeof User; title: string; hint?: string }) {
  return (
    <div className="mb-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
        <Icon className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        {title}
      </h3>
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

export default function Settings() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [showWebhookModal, setShowWebhookModal] = useState(false);
  const [deleteWebhookId, setDeleteWebhookId] = useState<string | null>(null);

  const settingsQ = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get });
  const webhooksQ = useQuery({ queryKey: ['webhooks'], queryFn: webhooksApi.list });

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<SettingsValues>({ resolver: zodResolver(settingsSchema) });

  useEffect(() => {
    if (settingsQ.data) {
      const s = settingsQ.data;
      reset({
        profileName: s.profile.name,
        default_interval: s.default_interval,
        default_timeout: s.default_timeout,
        failure_threshold: s.failure_threshold,
        recovery_threshold: s.recovery_threshold,
        degraded_latency_ms: s.degraded_latency_ms,
        results_retention_days: s.results_retention_days,
        email_enabled: s.notifications.email_enabled,
        webhook_enabled: s.notifications.webhook_enabled,
      });
    }
  }, [settingsQ.data, reset]);

  const saveMut = useMutation({
    mutationFn: (v: SettingsValues) =>
      settingsApi.update({
        profile: { name: v.profileName },
        default_interval: v.default_interval,
        default_timeout: v.default_timeout,
        failure_threshold: v.failure_threshold,
        recovery_threshold: v.recovery_threshold,
        degraded_latency_ms: v.degraded_latency_ms,
        results_retention_days: v.results_retention_days,
        notifications: { email_enabled: v.email_enabled, webhook_enabled: v.webhook_enabled },
      }),
    onSuccess: () => {
      toast.success('Settings saved');
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to save settings')),
  });

  // Webhook create form
  const {
    register: whRegister,
    control: whControl,
    handleSubmit: whSubmit,
    reset: whReset,
    formState: { errors: whErrors, isSubmitting: whSubmitting },
  } = useForm<WebhookValues>({
    resolver: zodResolver(webhookSchema),
    defaultValues: { name: '', url: '', events: [], active: true },
  });

  const createWebhookMut = useMutation({
    mutationFn: (v: WebhookValues) =>
      webhooksApi.create({ name: v.name, url: v.url, events: v.events, active: v.active }),
    onSuccess: (w) => {
      toast.success(`Webhook "${w.name}" added`);
      setShowWebhookModal(false);
      whReset();
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to add webhook')),
  });

  const deleteWebhookMut = useMutation({
    mutationFn: (id: string) => webhooksApi.remove(id),
    onSuccess: () => {
      toast.success('Webhook deleted');
      setDeleteWebhookId(null);
      queryClient.invalidateQueries({ queryKey: ['webhooks'] });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to delete webhook')),
  });

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Settings" subtitle="Workspace preferences and notification channels" />

      {settingsQ.isPending ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="p-6">
              <Skeleton className="mb-4 h-5 w-40" />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Skeleton className="h-14" />
                <Skeleton className="h-14" />
              </div>
            </Card>
          ))}
        </div>
      ) : settingsQ.isError ? (
        <Card>
          <ErrorState message={getErrorMessage(settingsQ.error)} onRetry={() => settingsQ.refetch()} />
        </Card>
      ) : (
        <form onSubmit={handleSubmit((v) => saveMut.mutate(v))} className="space-y-4" noValidate>
          <Card className="p-6">
            <SectionTitle icon={User} title="Profile" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Display name" error={errors.profileName?.message} htmlFor="profileName">
                <input id="profileName" className={inputCls} {...register('profileName')} />
              </Field>
              <Field label="Email" htmlFor="email" hint="Email is read-only.">
                <input
                  id="email"
                  className={cx(inputCls, 'cursor-not-allowed opacity-60')}
                  value={settingsQ.data.profile.email}
                  readOnly
                  disabled
                />
              </Field>
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle
              icon={Plus}
              title="Monitoring defaults"
              hint="Used as defaults when adding a new API."
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Default check interval" error={errors.default_interval?.message} htmlFor="default_interval">
                <select id="default_interval" className={inputCls} {...register('default_interval', { setValueAs: (v) => Number(v) })}>
                  {INTERVAL_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s < 60 ? `${s}s` : s < 3600 ? `${s / 60} min` : '1 hour'}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Default timeout (seconds)" error={errors.default_timeout?.message} htmlFor="default_timeout">
                <input
                  id="default_timeout"
                  type="number"
                  min={1}
                  max={120}
                  className={inputCls}
                  {...register('default_timeout', { valueAsNumber: true })}
                />
              </Field>
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle
              icon={Bell}
              title="Alerting thresholds"
              hint="Control when incidents are created and resolved automatically."
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Failure threshold"
                error={errors.failure_threshold?.message}
                htmlFor="failure_threshold"
                hint="Consecutive failures before an incident is created."
              >
                <input
                  id="failure_threshold"
                  type="number"
                  min={1}
                  max={20}
                  className={inputCls}
                  {...register('failure_threshold', { valueAsNumber: true })}
                />
              </Field>
              <Field
                label="Recovery threshold"
                error={errors.recovery_threshold?.message}
                htmlFor="recovery_threshold"
                hint="Consecutive successes before an incident auto-resolves."
              >
                <input
                  id="recovery_threshold"
                  type="number"
                  min={1}
                  max={20}
                  className={inputCls}
                  {...register('recovery_threshold', { valueAsNumber: true })}
                />
              </Field>
              <Field
                label="Degraded latency (ms)"
                error={errors.degraded_latency_ms?.message}
                htmlFor="degraded_latency_ms"
                hint="Successful checks slower than this are marked degraded."
              >
                <input
                  id="degraded_latency_ms"
                  type="number"
                  min={50}
                  max={60000}
                  className={inputCls}
                  {...register('degraded_latency_ms', { valueAsNumber: true })}
                />
              </Field>
              <Field
                label="Result retention (days)"
                error={errors.results_retention_days?.message}
                htmlFor="results_retention_days"
                hint="Check results older than this are pruned."
              >
                <input
                  id="results_retention_days"
                  type="number"
                  min={1}
                  max={365}
                  className={inputCls}
                  {...register('results_retention_days', { valueAsNumber: true })}
                />
              </Field>
            </div>
          </Card>

          <Card className="p-6">
            <SectionTitle icon={Bell} title="Notifications" />
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/60">
                <div>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Email notifications</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Receive incident alerts by email.
                  </p>
                </div>
                <Controller
                  control={control}
                  name="email_enabled"
                  render={({ field }) => (
                    <Toggle checked={field.value} onChange={field.onChange} label="Email notifications" />
                  )}
                />
              </div>
              <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/60">
                <div>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Webhook notifications</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Dispatch incident events to your webhooks below.
                  </p>
                </div>
                <Controller
                  control={control}
                  name="webhook_enabled"
                  render={({ field }) => (
                    <Toggle checked={field.value} onChange={field.onChange} label="Webhook notifications" />
                  )}
                />
              </div>
            </div>
          </Card>

          <div className="flex justify-end">
            <Button type="submit" disabled={isSubmitting || saveMut.isPending || !isDirty}>
              {(isSubmitting || saveMut.isPending) && <Loader2 className="h-4 w-4 animate-spin" />}
              Save settings
            </Button>
          </div>
        </form>
      )}

      {/* Webhooks */}
      <Card className="mt-6">
        <CardHeader
          title="Webhooks"
          subtitle="Incident events are dispatched as JSON payloads"
          action={
            <Button size="sm" onClick={() => setShowWebhookModal(true)}>
              <Plus className="h-4 w-4" /> Add webhook
            </Button>
          }
        />
        {webhooksQ.isPending ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : webhooksQ.isError ? (
          <ErrorState message={getErrorMessage(webhooksQ.error)} onRetry={() => webhooksQ.refetch()} />
        ) : webhooksQ.data.length === 0 ? (
          <EmptyState
            icon={WebhookIcon}
            title="No webhooks yet"
            message="Add a webhook to receive incident.created, incident.resolved, api.down and api.recovered events."
            action={
              <Button size="sm" onClick={() => setShowWebhookModal(true)}>
                <Plus className="h-4 w-4" /> Add webhook
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {webhooksQ.data.map((w) => (
              <li key={w.id} className="flex items-start justify-between gap-3 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{w.name}</p>
                    <span
                      className={cx(
                        'rounded-full px-2 py-0.5 text-xs font-medium',
                        w.active
                          ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                          : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
                      )}
                    >
                      {w.active ? 'Active' : 'Disabled'}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate font-mono text-xs text-slate-500 dark:text-slate-400">
                    {w.url}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {w.events.map((e) => (
                      <span
                        key={e}
                        className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      >
                        {e}
                      </span>
                    ))}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">Added {formatDateTime(w.created_at)}</p>
                </div>
                <button
                  type="button"
                  aria-label={`Delete webhook ${w.name}`}
                  title="Delete webhook"
                  onClick={() => setDeleteWebhookId(w.id)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Add webhook modal */}
      <Modal open={showWebhookModal} title="Add webhook" onClose={() => setShowWebhookModal(false)}>
        <form onSubmit={whSubmit((v) => createWebhookMut.mutate(v))} className="space-y-4" noValidate>
          <Field label="Name" error={whErrors.name?.message} htmlFor="wh-name">
            <input id="wh-name" placeholder="Slack alerts" className={inputCls} {...whRegister('name')} />
          </Field>
          <Field label="URL" error={whErrors.url?.message} htmlFor="wh-url">
            <input
              id="wh-url"
              placeholder="https://hooks.example.com/incidents"
              inputMode="url"
              className={cx(inputCls, 'font-mono')}
              {...whRegister('url')}
            />
          </Field>
          <Field label="Events" error={whErrors.events?.message}>
            <div className="space-y-2">
              <Controller
                control={whControl}
                name="events"
                render={({ field }) => (
                  <>
                    {WEBHOOK_EVENT_OPTIONS.map((ev) => (
                      <label key={ev} className="flex cursor-pointer items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                        <input
                          type="checkbox"
                          value={ev}
                          checked={field.value.includes(ev)}
                          onChange={(e) => {
                            field.onChange(
                              e.target.checked
                                ? [...field.value, ev]
                                : field.value.filter((x) => x !== ev),
                            );
                          }}
                          className="h-4 w-4 rounded accent-indigo-600"
                        />
                        <span className="font-mono text-xs">{ev}</span>
                      </label>
                    ))}
                  </>
                )}
              />
            </div>
          </Field>
          <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/60">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Active</p>
            <Controller
              control={whControl}
              name="active"
              render={({ field }) => (
                <Toggle checked={field.value} onChange={field.onChange} label="Webhook active" />
              )}
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setShowWebhookModal(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={whSubmitting || createWebhookMut.isPending}>
              {(whSubmitting || createWebhookMut.isPending) && <Loader2 className="h-4 w-4 animate-spin" />}
              Add webhook
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmModal
        open={deleteWebhookId !== null}
        title="Delete webhook"
        message="This webhook will stop receiving incident events. Continue?"
        confirmLabel="Delete"
        loading={deleteWebhookMut.isPending}
        onConfirm={() => deleteWebhookId && deleteWebhookMut.mutate(deleteWebhookId)}
        onClose={() => setDeleteWebhookId(null)}
      />
    </div>
  );
}
