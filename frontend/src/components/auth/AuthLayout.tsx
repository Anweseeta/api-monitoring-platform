import { Activity } from 'lucide-react';
import type { ReactNode } from 'react';

export default function AuthLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-12 dark:bg-slate-950">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="rounded-2xl bg-indigo-600 p-3 shadow-lg">
            <Activity className="h-7 w-7 text-white" />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            API Monitor
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Uptime monitoring & incident tracking
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">{title}</h2>
          <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  );
}
