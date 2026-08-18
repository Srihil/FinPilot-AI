import apiClient from './client';
import type {
  User, AuthTokens, LoginRequest, SignupRequest,
  DashboardOverview, DashboardCharts,
  Customer, Vendor, Product,
  Transaction, Invoice, Expense,
  Approval, AuditLog,
  Conversation, Message,
  UploadResult, Report,
  CompanySettings, AISettings,
  AnalyticsOverview, AnalyticsCharts,
  PaginatedResponse,
  TallyLedger, TallyGroup, TallyStockGroup, TallyStockItem, TallyUnit, TallyGodown,
  ManagementOverview, VoucherItem, VoucherTypeItem, SyncHealth, StockCategory,
} from '../types';

// ─── Auth ────────────────────────────────────────────────────────────────────

export const authApi = {
  login: async (data: LoginRequest): Promise<AuthTokens> => {
    const response = await apiClient.post('/api/auth/login', {
      email: data.email,
      password: data.password,
    });
    return response.data;
  },

  signup: async (data: SignupRequest): Promise<User> => {
    const response = await apiClient.post('/api/auth/signup', data);
    return response.data;
  },

  me: async (): Promise<User> => {
    const response = await apiClient.get('/api/auth/me');
    return response.data;
  },
};

// ─── Dashboard ────────────────────────────────────────────────────────────────

export const dashboardApi = {
  overview: async (): Promise<DashboardOverview> => {
    const response = await apiClient.get('/api/dashboard/overview');
    return response.data;
  },

  charts: async (): Promise<DashboardCharts> => {
    const response = await apiClient.get('/api/dashboard/charts');
    return response.data;
  },
};

// ─── Customers ────────────────────────────────────────────────────────────────

export const customersApi = {
  list: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<Customer>> => {
    const response = await apiClient.get('/api/customers', { params });
    return response.data;
  },

  get: async (id: string): Promise<Customer> => {
    const response = await apiClient.get(`/api/customers/${id}`);
    return response.data;
  },

  create: async (data: Partial<Customer>): Promise<Customer> => {
    const response = await apiClient.post('/api/customers', data);
    return response.data;
  },

  update: async (id: string, data: Partial<Customer>): Promise<Customer> => {
    const response = await apiClient.put(`/api/customers/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/customers/${id}`);
  },
};

// ─── Vendors ─────────────────────────────────────────────────────────────────

export const vendorsApi = {
  list: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<Vendor>> => {
    const response = await apiClient.get('/api/vendors', { params });
    return response.data;
  },

  create: async (data: Partial<Vendor>): Promise<Vendor> => {
    const response = await apiClient.post('/api/vendors', data);
    return response.data;
  },

  update: async (id: string, data: Partial<Vendor>): Promise<Vendor> => {
    const response = await apiClient.put(`/api/vendors/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/vendors/${id}`);
  },
};

// ─── Products ────────────────────────────────────────────────────────────────

export const productsApi = {
  list: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<Product>> => {
    const response = await apiClient.get('/api/products', { params });
    return response.data;
  },

  create: async (data: Partial<Product>): Promise<Product> => {
    const response = await apiClient.post('/api/products', data);
    return response.data;
  },

  update: async (id: string, data: Partial<Product>): Promise<Product> => {
    const response = await apiClient.put(`/api/products/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/products/${id}`);
  },
};

// ─── Invoices / Transactions ──────────────────────────────────────────────────

export const invoicesApi = {
  list: async (params: { page?: number; page_size?: number; status?: string; type?: string }): Promise<PaginatedResponse<Transaction>> => {
    const response = await apiClient.get('/api/invoices', { params });
    return response.data;
  },

  create: async (data: Partial<Invoice>): Promise<Invoice> => {
    const response = await apiClient.post('/api/invoices', data);
    return response.data;
  },
};

// ─── Expenses ─────────────────────────────────────────────────────────────────

export const expensesApi = {
  list: async (params: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResponse<Expense>> => {
    const response = await apiClient.get('/api/expenses', { params });
    return response.data;
  },

  create: async (data: Partial<Expense>): Promise<Expense> => {
    const response = await apiClient.post('/api/expenses', data);
    return response.data;
  },
};

// ─── Approvals ────────────────────────────────────────────────────────────────

export const approvalsApi = {
  list: async (): Promise<Approval[]> => {
    const response = await apiClient.get('/api/approvals');
    // API returns { items: [...], total: N }
    return response.data?.items ?? response.data ?? [];
  },

  approve: async (id: string, notes?: string): Promise<Approval> => {
    const response = await apiClient.post(`/api/approvals/${id}/approve`, { notes });
    return response.data;
  },

  reject: async (id: string, notes?: string): Promise<Approval> => {
    const response = await apiClient.post(`/api/approvals/${id}/reject`, { notes });
    return response.data;
  },
};

// ─── Analytics ────────────────────────────────────────────────────────────────

export const analyticsApi = {
  overview: async (params: { date_from?: string; date_to?: string }): Promise<AnalyticsOverview> => {
    const response = await apiClient.get('/api/analytics/overview', { params });
    return response.data;
  },

  charts: async (params: { date_from?: string; date_to?: string }): Promise<AnalyticsCharts> => {
    const response = await apiClient.get('/api/analytics/charts', { params });
    return response.data;
  },
};

// ─── Audit Logs ───────────────────────────────────────────────────────────────

export const auditApi = {
  list: async (params: { page?: number; page_size?: number }): Promise<PaginatedResponse<AuditLog>> => {
    const response = await apiClient.get('/api/audit-logs', { params });
    return response.data;
  },
};

// ─── AI Assistant ────────────────────────────────────────────────────────────

export const assistantApi = {
  createConversation: async (title = 'New Conversation'): Promise<Conversation> => {
    const response = await apiClient.post('/api/assistant/conversations', { title });
    return response.data;
  },

  listConversations: async (): Promise<Conversation[]> => {
    const response = await apiClient.get('/api/assistant/conversations');
    return Array.isArray(response.data) ? response.data : (response.data?.items ?? []);
  },

  sendMessage: async (conversationId: string, content: string): Promise<Message> => {
    const response = await apiClient.post(`/api/assistant/conversations/${conversationId}/messages`, { content });
    return response.data;
  },

  getMessages: async (conversationId: string): Promise<Message[]> => {
    const response = await apiClient.get(`/api/assistant/conversations/${conversationId}/messages`);
    return response.data;
  },

  deleteConversation: async (conversationId: string): Promise<void> => {
    await apiClient.delete(`/api/assistant/conversations/${conversationId}`);
  },

  proposeTransaction: async (text: string): Promise<{
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    proposed: any;
    validation: { is_valid: boolean; errors: string[]; warnings: string[] };
    is_demo: boolean;
  }> => {
    const response = await apiClient.post('/api/assistant/propose-transaction', { text });
    return response.data;
  },
};

// ─── Uploads ─────────────────────────────────────────────────────────────────

export const uploadsApi = {
  uploadCSV: async (file: File, data_type: string): Promise<UploadResult> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('data_type', data_type);
    const response = await apiClient.post('/api/uploads/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  uploadPDFInvoice: async (file: File): Promise<Record<string, unknown>> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post('/api/uploads/pdf-invoice', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};

// ─── Reports ──────────────────────────────────────────────────────────────────

export const reportsApi = {
  generate: async (data: { type: string; date_from: string; date_to: string }): Promise<Report> => {
    const response = await apiClient.post('/api/reports/generate', {
      report_type: data.type,
      period_start: data.date_from ? `${data.date_from}T00:00:00` : undefined,
      period_end: data.date_to ? `${data.date_to}T23:59:59` : undefined,
    });
    return response.data;
  },

  list: async (): Promise<Report[]> => {
    const response = await apiClient.get('/api/reports');
    return response.data;
  },

  /** Download a PDF report as a blob and trigger browser save dialog. */
  download: async (reportId: string, filename: string): Promise<void> => {
    const response = await apiClient.get(`/api/reports/${reportId}/download`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename.endsWith('.pdf') ? filename : `${filename}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};

// ─── Settings ────────────────────────────────────────────────────────────────

export const settingsApi = {
  getCompany: async (): Promise<CompanySettings> => {
    const response = await apiClient.get('/api/settings/company');
    return response.data;
  },

  updateCompany: async (data: Partial<CompanySettings>): Promise<CompanySettings> => {
    const response = await apiClient.put('/api/settings/company', data);
    return response.data;
  },

  getAI: async (): Promise<AISettings> => {
    const response = await apiClient.get('/api/settings/ai');
    return response.data;
  },

  updateAI: async (data: Partial<AISettings>): Promise<AISettings> => {
    const response = await apiClient.put('/api/settings/ai', data);
    return response.data;
  },
};

// ─── Tally ───────────────────────────────────────────────────────────────────

export type TallyJobItem = {
  id: string;
  operation: string;
  status: 'PENDING' | 'CLAIMED' | 'SUCCESS' | 'FAILED' | 'RETRYING';
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
};

export const tallyApi = {
  activity: async (limit = 30): Promise<{ items: TallyJobItem[] }> => {
    const response = await apiClient.get('/api/tally/activity', { params: { limit } });
    return response.data;
  },
  retryJob: async (jobId: string): Promise<{ id: string; status: string; message: string }> => {
    const response = await apiClient.post(`/api/tally/jobs/${jobId}/retry`);
    return response.data;
  },
};

// ─── Management ──────────────────────────────────────────────────────────────

export const managementApi = {
  overview: async (): Promise<ManagementOverview> => {
    const res = await apiClient.get('/api/management/overview');
    return res.data;
  },

  ledgers: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyLedger>> => {
    const res = await apiClient.get('/api/management/ledgers', { params });
    return res.data;
  },

  createLedger: async (data: { name: string; parent_group?: string; opening_balance?: number }): Promise<TallyLedger> => {
    const res = await apiClient.post('/api/management/ledgers', data);
    return res.data;
  },

  stockGroups: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyStockGroup>> => {
    const res = await apiClient.get('/api/management/stock-groups', { params });
    return res.data;
  },

  createStockGroup: async (data: { name: string; parent?: string }): Promise<TallyStockGroup> => {
    const res = await apiClient.post('/api/management/stock-groups', data);
    return res.data;
  },

  units: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyUnit>> => {
    const res = await apiClient.get('/api/management/units', { params });
    return res.data;
  },

  createUnit: async (data: { name: string; symbol?: string; decimal_places?: number }): Promise<TallyUnit> => {
    const res = await apiClient.post('/api/management/units', data);
    return res.data;
  },

  godowns: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyGodown>> => {
    const res = await apiClient.get('/api/management/godowns', { params });
    return res.data;
  },

  createGodown: async (data: { name: string; parent?: string }): Promise<TallyGodown> => {
    const res = await apiClient.post('/api/management/godowns', data);
    return res.data;
  },

  vouchers: async (params: {
    page?: number;
    page_size?: number;
    voucher_type?: string;
    search?: string;
    date_from?: string;
    date_to?: string;
    ledger_name?: string;
  }): Promise<PaginatedResponse<VoucherItem>> => {
    const res = await apiClient.get('/api/management/vouchers', { params });
    return res.data;
  },

  deleteVoucher: async (entityType: 'invoice' | 'expense', id: string) => {
    const res = await apiClient.delete(`/api/management/vouchers/${entityType}/${id}`);
    return res.data as { deleted: boolean; message: string };
  },

  syncHealth: async (): Promise<SyncHealth> => {
    const res = await apiClient.get('/api/management/sync-health');
    return res.data;
  },

  clearLocalVouchers: async (): Promise<{ deleted_invoices: number; deleted_expenses: number; message: string }> => {
    const res = await apiClient.post('/api/management/clear-local-vouchers');
    return res.data;
  },

  wipeAllVouchers: async (): Promise<{ deleted_invoices: number; deleted_expenses: number; message: string }> => {
    const res = await apiClient.post('/api/management/wipe-vouchers');
    return res.data;
  },

  wipeAllLocalData: async (): Promise<{
    invoices: number; expenses: number; stock_transactions: number;
    voucher_types: number; ledgers: number; account_groups: number;
    stock_groups: number; stock_items: number; stock_categories: number;
    units: number; godowns: number; message: string;
  }> => {
    const res = await apiClient.post('/api/management/wipe-all-local-data');
    return res.data;
  },

  voucherTypes: async (params?: { page?: number; page_size?: number; search?: string }) => {
    const res = await apiClient.get('/api/management/voucher-types', { params });
    return res.data as { items: VoucherTypeItem[]; total: number; total_pages: number };
  },

  createVoucherType: async (data: { name: string; parent: string; numbering_method?: string }) => {
    const res = await apiClient.post('/api/management/voucher-types', data);
    return res.data;
  },

  deleteVoucherType: async (id: string) => {
    const res = await apiClient.delete(`/api/management/voucher-types/${id}`);
    return res.data;
  },

  updateLedger: async (id: string, data: { name?: string; parent_group?: string; opening_balance?: number }) => {
    const res = await apiClient.patch(`/api/management/ledgers/${id}`, data);
    return res.data;
  },
  deleteLedger: async (id: string) => {
    const res = await apiClient.delete(`/api/management/ledgers/${id}`);
    return res.data;
  },

  updateStockGroup: async (id: string, data: { name?: string; parent?: string }) => {
    const res = await apiClient.patch(`/api/management/stock-groups/${id}`, data);
    return res.data;
  },
  deleteStockGroup: async (id: string) => {
    const res = await apiClient.delete(`/api/management/stock-groups/${id}`);
    return res.data;
  },

  updateUnit: async (id: string, data: { name?: string; symbol?: string; decimal_places?: number }) => {
    const res = await apiClient.patch(`/api/management/units/${id}`, data);
    return res.data;
  },
  deleteUnit: async (id: string) => {
    const res = await apiClient.delete(`/api/management/units/${id}`);
    return res.data;
  },

  updateGodown: async (id: string, data: { name?: string; parent?: string }) => {
    const res = await apiClient.patch(`/api/management/godowns/${id}`, data);
    return res.data;
  },
  deleteGodown: async (id: string) => {
    const res = await apiClient.delete(`/api/management/godowns/${id}`);
    return res.data;
  },

  stockItems: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyStockItem>> => {
    const res = await apiClient.get('/api/management/stock-items', { params });
    return res.data;
  },
  createStockItem: async (data: { name: string; stock_group?: string; stock_category?: string; unit?: string; rate?: number; opening_qty?: number }): Promise<TallyStockItem> => {
    const res = await apiClient.post('/api/management/stock-items', data);
    return res.data;
  },
  updateStockItem: async (id: string, data: { name?: string; stock_group?: string; stock_category?: string; unit?: string; rate?: number }) => {
    const res = await apiClient.patch(`/api/management/stock-items/${id}`, data);
    return res.data;
  },
  deleteStockItem: async (id: string) => {
    const res = await apiClient.delete(`/api/management/stock-items/${id}`);
    return res.data;
  },

  createVoucher: async (data: {
    voucher_type: string;
    date: string;
    amount: number;
    narration?: string;
    party_ledger?: string;
    account_ledger?: string;
    sales_ledger?: string;
    purchase_ledger?: string;
    dr_ledger?: string;
    cr_ledger?: string;
    from_account?: string;
    to_account?: string;
    custom_voucher_type_name?: string;
  }) => {
    const res = await apiClient.post('/api/management/vouchers/create', data);
    return res.data;
  },

  updateVoucher: async (entityType: 'invoice' | 'expense', id: string, data: {
    date?: string;
    amount?: number;
    narration?: string;
  }) => {
    const res = await apiClient.patch(`/api/management/vouchers/${entityType}/${id}`, data);
    return res.data;
  },

  stockCategories: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<StockCategory>> => {
    const res = await apiClient.get('/api/inventory/stock-categories', { params });
    return res.data;
  },
  createStockCategory: async (data: { name: string; parent?: string; description?: string }): Promise<StockCategory> => {
    const res = await apiClient.post('/api/inventory/stock-categories', data);
    return res.data;
  },
  updateStockCategory: async (id: string, data: { name?: string; parent?: string; description?: string }) => {
    const res = await apiClient.patch(`/api/inventory/stock-categories/${id}`, data);
    return res.data;
  },
  deleteStockCategory: async (id: string) => {
    const res = await apiClient.delete(`/api/inventory/stock-categories/${id}`);
    return res.data;
  },
};

// ─── Groups ──────────────────────────────────────────────────────────────────

export const groupsApi = {
  list: async (params: { page?: number; page_size?: number; search?: string }): Promise<PaginatedResponse<TallyGroup>> => {
    const res = await apiClient.get('/api/management/groups', { params });
    return res.data;
  },
  create: async (data: { name: string; parent?: string; nature?: string }): Promise<TallyGroup> => {
    const res = await apiClient.post('/api/management/groups', data);
    return res.data;
  },
  update: async (id: string, data: { name?: string; parent?: string; nature?: string }) => {
    const res = await apiClient.patch(`/api/management/groups/${id}`, data);
    return res.data;
  },
  delete: async (id: string) => {
    const res = await apiClient.delete(`/api/management/groups/${id}`);
    return res.data;
  },
};

// ─── AI Create ───────────────────────────────────────────────────────────────

export const aiCreateApi = {
  extractEntity: async (text: string): Promise<{
    entity_type: string;
    data: Record<string, unknown>;
    confidence: number;
    missing_fields: string[];
  }> => {
    const response = await apiClient.post('/api/assistant/extract-entity', { text });
    return response.data;
  },

  createEntity: async (
    entity_type: string,
    data: Record<string, unknown>
  ): Promise<{
    id: string;
    entity_type: string;
    tally_queued: boolean;
  }> => {
    const response = await apiClient.post('/api/assistant/create-entity', { entity_type, data });
    return response.data;
  },
};
