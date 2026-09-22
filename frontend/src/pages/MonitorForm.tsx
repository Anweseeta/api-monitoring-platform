import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form';
import type { Control, UseFormRegister } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Eye, EyeOff, Loader2, Plus, Trash2 } from 'lucide-react';
import { getErrorMessage, monitorsApi } from '../lib/api';
import { useToast } from '../lib/toast';
import { INTERVAL_OPTIONS, METHOD_OPTIONS, cx } from '../lib/utils';
import type { HttpMethod } from '../types';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  Skeleton,
  Toggle,
  inputCls,
} from '../components/ui';

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------
const headerRowSchema = z.object({
  key: z.string(),
  value: z.string(),
  secret: z.boolean(),
});

type HeaderRow = z.infer<typeof headerRowSchema>;

const schema = z
  .object({
    name: z.string().min(1, 'Name is required').max(120, 'Name is too long'),
    url: z
      .string()
      .min(1, 'URL is required')
      .url('Enter a valid URL')
      .refine((u) => /^https?:\/\//i.test(u), 'Only http(s) URLs are allowed'),
    method: z.enum(METHOD_OPTIONS),
    description: z.string().max(500, 'Description is too long'),
    interval: z
      .number()
      .refine((v) => INTERVAL_OPTIONS.includes(v), 'Choose a valid interval'),
    timeout: z.number().int().min(1, 'Minimum 1 second').max(120, 'Maximum 120 seconds'),
    expected_status: z.number().int().min(100, 'Min 100').max(599, 'Max 599'),
    headers: z.array(headerRowSchema).superRefine((rows, ctx) => {
      const seen = new Set<string>();
      rows.forEach((row, i) => {
        if (row.key.trim() === '' && row.value.trim() === '') return;
        if (row.key.trim() === '') {
          ctx.addIssue({ code: 'custom', message: 'Header name required', path: [i, 'key'] });
          return;
        }
        const k = row.key.trim().toLowerCase();
        if (seen.has(k)) {
          ctx.addIssue({ code: 'custom', message: 'Duplicate header name', path: [i, 'key'] });
        }
        seen.add(k);
      });
    }),
    body: z.string(),
    active: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (['POST', 'PUT', 'PATCH'].includes(v.method) && (v.body ?? '').trim() !== '') {
      try {
        JSON.parse(v.body);
      } catch {
        ctx.addIssue({ code: 'custom', message: 'Body must be valid JSON', path: ['body'] });
      }
    }
  });

type FormValues = z.infer<typeof schema>;

const BODY_METHODS: HttpMethod[] = ['POST', 'PUT', 'PATCH'];

// ---------------------------------------------------------------------------
// Header row editor: secret values render as password inputs and are never
// logged or echoed anywhere.
// ---------------------------------------------------------------------------
function HeaderRowEditor({
  index,
  control,
  register,
  remove,
  error,
}: {
  index: number;
  control: Control<FormValues>;
  register: UseFormRegister<FormValues>;
  remove: (index: number) => void;
  error?: string;
}) {
  const secret = useWatch({ control, name: `headers.${index}.secret` as const });
  const [revealed, setRevealed] = useState(false);
  const inputType = secret && !revealed ? 'password' : 'text';

  return (
    <div>
      <div className="flex items-start gap-2">
        <input
          placeholder="Header name"
          autoComplete="off"
          className={inputCls}
          {...register(`headers.${index}.key` as const)}
        />
        <div className="relative flex-1">
          <input
            type={inputType}
            placeholder="Value"
            autoComplete="off"
            className={cx(inputCls, secret && 'pr-10')}
            {...register(`headers.${index}.value` as const)}
          />
          {secret && (
            <button
              type="button"
              aria-label={revealed ? 'Hide value' : 'Show value'}
              onClick={() => setRevealed((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              {revealed ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          )}
        </div>
        <label className="flex shrink-0 items-center gap-1.5 pt-2 text-xs text-slate-500 dark:text-slate-400">
          <input
            type="checkbox"
            className="h-4 w-4 rounded accent-indigo-600"
            {...register(`headers.${index}.secret` as const)}
          />
          Secret
        </label>
        <button
          type="button"
          aria-label="Remove header"
          onClick={() => remove(index)}
          className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function MonitorForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const existing = useQuery({
    queryKey: ['monitors', 'detail', id],
    queryFn: () => monitorsApi.get(id!),
    enabled: isEdit,
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      url: '',
      method: 'GET',
      description: '',
      interval: 300,
      timeout: 10,
      expected_status: 200,
      headers: [],
      body: '',
      active: true,
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'headers' });
  const method = watch('method');

  useEffect(() => {
    if (existing.data) {
      const m = existing.data;
      const rows: HeaderRow[] = Object.entries(m.headers ?? {}).map(([key, value]) => ({
        key,
        value,
        secret: true, // safest default — we can't know which were secret
      }));
      reset({
        name: m.name,
        url: m.url,
        method: m.method,
        description: m.description ?? '',
        interval: m.interval,
        timeout: m.timeout,
        expected_status: m.expected_status,
        headers: rows,
        body: m.body == null ? '' : typeof m.body === 'string' ? m.body : JSON.stringify(m.body, null, 2),
        active: m.active,
      });
    }
  }, [existing.data, reset]);

  const saveMut = useMutation({
    mutationFn: (values: FormValues) => {
      const headers: Record<string, string> = {};
      for (const row of values.headers) {
        if (row.key.trim() !== '') headers[row.key.trim()] = row.value;
      }
      const input = {
        name: values.name.trim(),
        url: values.url.trim(),
        method: values.method,
        description: values.description?.trim() ?? '',
        interval: values.interval,
        timeout: values.timeout,
        expected_status: values.expected_status,
        headers,
        body:
          BODY_METHODS.includes(values.method) && (values.body ?? '').trim() !== ''
            ? JSON.parse(values.body as string)
            : null,
        active: values.active,
      };
      return isEdit ? monitorsApi.update(id!, input) : monitorsApi.create(input);
    },
    onSuccess: (m) => {
      toast.success(isEdit ? `Updated "${m.name}"` : `Created "${m.name}"`);
      queryClient.invalidateQueries({ queryKey: ['monitors'] });
      navigate(`/monitors/${m.id}`);
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Failed to save API')),
  });

  if (isEdit && existing.isPending) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={isEdit ? 'Edit API' : 'Add API'} />
        <Card className="space-y-4 p-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </Card>
      </div>
    );
  }

  if (isEdit && existing.isError) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title="Edit API" />
        <Card>
          <ErrorState message={getErrorMessage(existing.error)} onRetry={() => existing.refetch()} />
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={isEdit ? 'Edit API' : 'Add API'}
        subtitle={isEdit ? 'Update the monitored endpoint' : 'Add a new endpoint to monitor'}
        actions={
          <Link to={isEdit ? `/monitors/${id}` : '/monitors'}>
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
          </Link>
        }
      />

      <form
        onSubmit={handleSubmit((v) => saveMut.mutate(v))}
        className="space-y-5"
        noValidate
      >
        <Card className="space-y-5 p-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Endpoint
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="sm:col-span-2">
              <Field label="Name" error={errors.name?.message} htmlFor="name">
                <input id="name" placeholder="Payments API" className={inputCls} {...register('name')} />
              </Field>
            </div>
            <Field label="Method" error={errors.method?.message} htmlFor="method">
              <select id="method" className={inputCls} {...register('method')}>
                {METHOD_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="URL" error={errors.url?.message} htmlFor="url" hint="Only public http(s) URLs can be monitored.">
            <input
              id="url"
              placeholder="https://api.example.com/health"
              inputMode="url"
              className={cx(inputCls, 'font-mono')}
              {...register('url')}
            />
          </Field>
          <Field label="Description" error={errors.description?.message} htmlFor="description">
            <textarea
              id="description"
              rows={2}
              placeholder="What does this API do?"
              className={inputCls}
              {...register('description')}
            />
          </Field>
        </Card>

        <Card className="space-y-5 p-6">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Check settings
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="Check interval" error={errors.interval?.message} htmlFor="interval">
              <select id="interval" className={inputCls} {...register('interval', { setValueAs: (v) => Number(v) })}>
                {INTERVAL_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s < 60 ? `${s}s` : s < 3600 ? `${s / 60} min` : '1 hour'}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Timeout (seconds)" error={errors.timeout?.message} htmlFor="timeout">
              <input id="timeout" type="number" min={1} max={120} className={inputCls} {...register('timeout', { valueAsNumber: true })} />
            </Field>
            <Field label="Expected status" error={errors.expected_status?.message} htmlFor="expected_status">
              <input
                id="expected_status"
                type="number"
                min={100}
                max={599}
                className={inputCls}
                {...register('expected_status', { valueAsNumber: true })}
              />
            </Field>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-800/60">
            <div>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Monitoring active</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Paused APIs are skipped by the scheduler.
              </p>
            </div>
            <Controller
              control={control}
              name="active"
              render={({ field }) => (
                <Toggle checked={field.value} onChange={field.onChange} label="Monitoring active" />
              )}
            />
          </div>
        </Card>

        <Card className="space-y-5 p-6">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Headers
            </h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append({ key: '', value: '', secret: false })}
            >
              <Plus className="h-3.5 w-3.5" /> Add header
            </Button>
          </div>
          {fields.length === 0 ? (
            <EmptyState
              title="No custom headers"
              message="Add headers like Authorization if the endpoint needs them. Mark sensitive values as secret."
            />
          ) : (
            <div className="space-y-3">
              {fields.map((field, index) => (
                <HeaderRowEditor
                  key={field.id}
                  index={index}
                  control={control}
                  register={register}
                  remove={remove}
                  error={
                    errors.headers?.[index]?.key?.message ??
                    errors.headers?.[index]?.value?.message
                  }
                />
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Secret values are masked and never shown in logs or check history.
          </p>
        </Card>

        {BODY_METHODS.includes(method as HttpMethod) && (
          <Card className="space-y-5 p-6">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Request body
            </h3>
            <Field label="JSON body" error={errors.body?.message} htmlFor="body" hint="Sent with each check. Must be valid JSON.">
              <textarea
                id="body"
                rows={6}
                spellCheck={false}
                placeholder='{"key": "value"}'
                className={cx(inputCls, 'font-mono')}
                {...register('body')}
              />
            </Field>
          </Card>
        )}

        <div className="flex justify-end gap-2">
          <Link to={isEdit ? `/monitors/${id}` : '/monitors'}>
            <Button type="button" variant="secondary">
              Cancel
            </Button>
          </Link>
          <Button type="submit" disabled={isSubmitting || saveMut.isPending}>
            {(isSubmitting || saveMut.isPending) && <Loader2 className="h-4 w-4 animate-spin" />}
            {isEdit ? 'Save changes' : 'Create API'}
          </Button>
        </div>
      </form>
    </div>
  );
}
