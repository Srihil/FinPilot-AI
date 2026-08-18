import { useState } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { Skeleton } from '../ui/skeleton';
import { TallyActivityDrawer } from '../ui/TallyActivityDrawer';

export function AppShell() {
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const { isAuthenticated, isLoading }  = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="space-y-4 w-64">
          <Skeleton className="h-8 w-48 mx-auto" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-56" />
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar
          onMenuClick={() => setSidebarOpen(true)}
          onActivityClick={() => setActivityOpen(true)}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="p-4 lg:p-6 min-h-full">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Global Tally Activity Drawer — available on every page */}
      <TallyActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
    </div>
  );
}
