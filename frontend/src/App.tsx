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

// Dashboard
import DashboardPage from './pages/dashboard/DashboardPage';

// AI pages
import AssistantPage from './pages/assistant/AssistantPage';
import AICreatePage from './pages/ai-create/AICreatePage';

// Management (legacy unified view)
import ManagementPage from './pages/management/ManagementPage';

// Accounting
import LedgersPage from './pages/accounting/LedgersPage';
import GroupsPage from './pages/accounting/GroupsPage';
import VouchersPage from './pages/accounting/VouchersPage';
import VoucherTypesPage from './pages/accounting/VoucherTypesPage';

// Inventory
import StockItemsPage from './pages/inventory/StockItemsPage';
import StockGroupsPage from './pages/inventory/StockGroupsPage';
import StockCategoriesPage from './pages/inventory/StockCategoriesPage';
import UnitsPage from './pages/inventory/UnitsPage';
import GodownsPage from './pages/inventory/GodownsPage';
import StockTransactionsPage from './pages/inventory/StockTransactionsPage';

// Tally
import ConflictsPage from './pages/tally/ConflictsPage';

// Other app pages
import AnalyticsPage from './pages/analytics/AnalyticsPage';
import UploadsPage from './pages/uploads/UploadsPage';
import ReportsPage from './pages/reports/ReportsPage';
import AuditLogsPage from './pages/audit/AuditLogsPage';
import SettingsPage from './pages/settings/SettingsPage';
import TallyPage from './pages/tally/TallyPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
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
              {/* Dashboard */}
              <Route path="/dashboard" element={<DashboardPage />} />

              {/* Accounting */}
              <Route path="/accounting/ledgers" element={<LedgersPage />} />
              <Route path="/accounting/groups" element={<GroupsPage />} />
              <Route path="/accounting/vouchers" element={<VouchersPage />} />
              <Route path="/accounting/vouchers/:type" element={<VouchersPage />} />
              <Route path="/accounting/voucher-types" element={<VoucherTypesPage />} />

              {/* Inventory */}
              <Route path="/inventory/stock-items" element={<StockItemsPage />} />
              <Route path="/inventory/stock-groups" element={<StockGroupsPage />} />
              <Route path="/inventory/stock-categories" element={<StockCategoriesPage />} />
              <Route path="/inventory/units" element={<UnitsPage />} />
              <Route path="/inventory/godowns" element={<GodownsPage />} />
              <Route path="/inventory/stock-transactions" element={<StockTransactionsPage />} />

              {/* AI */}
              <Route path="/assistant" element={<AssistantPage />} />
              <Route path="/ai-create" element={<AICreatePage />} />

              {/* Management (legacy unified view — kept for backward compat) */}
              <Route path="/management" element={<ManagementPage />} />

              {/* Other */}
              <Route path="/uploads" element={<UploadsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/audit-logs" element={<AuditLogsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/tally" element={<TallyPage />} />
              <Route path="/tally/conflicts" element={<ConflictsPage />} />
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
