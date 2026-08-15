import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth/AuthContext';
import { AppShell } from './components/layout/AppShell';
import { Toaster } from './components/ui/toaster';

// Public pages
import LandingPage from './pages/LandingPage';
import LoginPage from './pages/auth/LoginPage';
import SignupPage from './pages/auth/SignupPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';

// App pages
import DashboardPage from './pages/dashboard/DashboardPage';
import AssistantPage from './pages/assistant/AssistantPage';
import AnalyticsPage from './pages/analytics/AnalyticsPage';
import ApprovalsPage from './pages/approvals/ApprovalsPage';
import UploadsPage from './pages/uploads/UploadsPage';
import ReportsPage from './pages/reports/ReportsPage';
import AuditLogsPage from './pages/audit/AuditLogsPage';
import SettingsPage from './pages/settings/SettingsPage';
import TallyPage from './pages/tally/TallyPage';
import AICreatePage from './pages/ai-create/AICreatePage';
import ManagementPage from './pages/management/ManagementPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />

            {/* Protected app routes */}
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/assistant" element={<AssistantPage />} />
              <Route path="/management" element={<ManagementPage />} />
              <Route path="/uploads" element={<UploadsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
              <Route path="/audit-logs" element={<AuditLogsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/tally" element={<TallyPage />} />
              <Route path="/ai-create" element={<AICreatePage />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  );
}
