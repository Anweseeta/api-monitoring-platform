import { useCallback, useState } from 'react';
import { THEME_KEY } from '../config';

function readDark(): boolean {
  if (typeof document === 'undefined') return false;
  return document.documentElement.classList.contains('dark');
}

/** Called once in main.tsx before React renders to avoid a theme flash. */
export function initTheme(): void {
  const stored = localStorage.getItem(THEME_KEY);
  const dark =
    stored != null
      ? stored === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.classList.toggle('dark', dark);
}

export function useTheme() {
  const [dark, setDark] = useState<boolean>(readDark);

  const toggle = useCallback(() => {
    setDark((prev) => {
      const next = !prev;
      document.documentElement.classList.toggle('dark', next);
      localStorage.setItem(THEME_KEY, next ? 'dark' : 'light');
      return next;
    });
  }, []);

  return { dark, toggle };
}

/** Chart palette that stays legible in both themes. Pass `dark` from useTheme(). */
export function useChartColors(dark: boolean) {
  return {
    grid: dark ? '#1e293b' : '#e2e8f0',
    tick: dark ? '#94a3b8' : '#64748b',
    uptime: '#22c55e',
    latency: '#3b82f6',
    created: '#f59e0b',
    resolved: '#22c55e',
    healthy: '#22c55e',
    degraded: '#f59e0b',
    down: '#ef4444',
    paused: '#94a3b8',
  };
}
