import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import { useAuth } from './auth/AuthContext';
import { Spinner } from './components/ui';
import type { ReactNode } from 'react';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import MonitorsList from './pages/MonitorsList';
import MonitorForm from './pages/MonitorForm';
import MonitorDetail from './pages/MonitorDetail';
import IncidentsList from './pages/IncidentsList';
import IncidentDetail from './pages/IncidentDetail';
import ActivityLog from './pages/ActivityLog';
import Settings from './pages/Settings';
import NotFound from './pages/NotFound';

function Protected({ children }: { children: ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }
  if (token) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />
      <Route
        path="/"
        element={
          <Protected>
            <AppLayout />
          </Protected>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="monitors" element={<MonitorsList />} />
        <Route path="monitors/new" element={<MonitorForm />} />
        <Route path="monitors/:id" element={<MonitorDetail />} />
        <Route path="monitors/:id/edit" element={<MonitorForm />} />
        <Route path="incidents" element={<IncidentsList />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="activity" element={<ActivityLog />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
