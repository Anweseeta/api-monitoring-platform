import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PlusCircle,
  ScrollText,
  Server,
  Settings,
  Sun,
  X,
} from 'lucide-react';
import { useAuth } from '../../auth/AuthContext';
import { useTheme } from '../../hooks/useTheme';
import { cx } from '../../lib/utils';

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const SECTIONS: Array<{ heading: string; items: NavItem[] }> = [
  {
    heading: 'Overview',
    items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true }],
  },
  {
    heading: 'Monitoring',
    items: [
      { to: '/monitors', label: 'All APIs', icon: Server, end: true },
      { to: '/monitors/new', label: 'Add API', icon: PlusCircle },
    ],
  },
  {
    heading: 'Response',
    items: [{ to: '/incidents', label: 'Incidents', icon: AlertTriangle }],
  },
  {
    heading: 'System',
    items: [
      { to: '/activity', label: 'Activity Logs', icon: ScrollText },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

function linkCls({ isActive }: { isActive: boolean }) {
  return cx(
    'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
  );
}

function SidebarContent({ onNavigate }: { onNavigate: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 pb-2 pt-6">
        <div className="rounded-lg bg-indigo-600 p-2">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-base font-bold text-slate-900 dark:text-white">API Monitor</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">Uptime & incidents</p>
        </div>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {SECTIONS.map((section) => (
          <div key={section.heading}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              {section.heading}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className={linkCls} onClick={onNavigate}>
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-slate-200 p-4 dark:border-slate-800">
        <p className="px-1 text-xs text-slate-400 dark:text-slate-500">
          API Monitor <span className="text-slate-300 dark:text-slate-600">·</span> v1.0
        </p>
      </div>
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  if (!user) return null;
  const initials = user.name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
          {initials}
        </span>
        <span className="hidden max-w-36 truncate text-left text-sm font-medium text-slate-700 dark:text-slate-200 sm:block">
          {user.name}
        </span>
        <ChevronDown className="hidden h-4 w-4 text-slate-400 sm:block" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg dark:border-slate-700 dark:bg-slate-900">
            <div className="px-3 py-2">
              <p className="truncate text-sm font-medium text-slate-900 dark:text-white">{user.name}</p>
              <p className="truncate text-xs text-slate-500 dark:text-slate-400">{user.email}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate('/settings');
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Settings className="h-4 w-4" /> Settings
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                logout();
                navigate('/login');
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
            >
              <LogOut className="h-4 w-4" /> Log out
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { dark, toggle } = useTheme();

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:block">
        <SidebarContent onNavigate={() => undefined} />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setDrawerOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setDrawerOpen(false)}
              className="absolute right-3 top-5 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      {/* Main column */}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
            <button
              type="button"
              aria-label="Open menu"
              onClick={() => setDrawerOpen(true)}
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="hidden items-center gap-2 text-sm text-slate-500 dark:text-slate-400 lg:flex">
              <span className="font-medium text-slate-700 dark:text-slate-200">Workspace</span>
            </div>
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
                title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
                onClick={toggle}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </button>
              <UserMenu />
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
