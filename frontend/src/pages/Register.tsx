import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import AuthLayout from '../components/auth/AuthLayout';
import { Button, Field, inputCls } from '../components/ui';
import { useAuth } from '../auth/AuthContext';

const schema = z
  .object({
    name: z.string().min(1, 'Name is required').max(100, 'Name is too long'),
    email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
    password: z.string().min(6, 'Password must be at least 6 characters'),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: 'Passwords do not match',
    path: ['confirmPassword'],
  });

type FormValues = z.infer<typeof schema>;

export default function Register() {
  const { register: signup } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    try {
      await signup(values.name, values.email, values.password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setServerError(err instanceof Error ? err.message : 'Registration failed');
    }
  };

  return (
    <AuthLayout title="Create your account" subtitle="Start monitoring your APIs in minutes">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {serverError && (
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
          >
            {serverError}
          </div>
        )}
        <Field label="Name" error={errors.name?.message} htmlFor="name">
          <input
            id="name"
            type="text"
            autoComplete="name"
            placeholder="Jane Doe"
            className={inputCls}
            {...register('name')}
          />
        </Field>
        <Field label="Email" error={errors.email?.message} htmlFor="email">
          <input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            className={inputCls}
            {...register('email')}
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Password" error={errors.password?.message} htmlFor="password">
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              className={inputCls}
              {...register('password')}
            />
          </Field>
          <Field label="Confirm password" error={errors.confirmPassword?.message} htmlFor="confirmPassword">
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              className={inputCls}
              {...register('confirmPassword')}
            />
          </Field>
        </div>
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
