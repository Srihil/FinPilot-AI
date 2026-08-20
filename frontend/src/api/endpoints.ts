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
  list: async (params: {
    page?: number;
    page_size?: number;
    action?: string;
    user_id?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<PaginatedResponse<AuditLog>> => {
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

  /**
   * SSE streaming version of sendMessage.
   * Uses fetch (not axios) — axios does not expose ReadableStream.
   *
   *   onStatus(text)  — a tool is executing; show as status label
   *   onToken(text)   — append this chunk to the growing response
   *   onDone(message) — final persisted Message (replace the placeholder)
   *   onError(text)   — fatal error string
   */
  streamMessage: async (
    conversationId: string,
    content: string,
    onStatus: (text: string) => void,
    onToken: (text: string) => void,
    onDone: (message: Message) => void,
    onError: (text: string) => void,
  ): Promise<void> => {
    const authToken = localStorage.getItem('finpilot_token');
    const base = (import.meta.env.VITE_API_URL as string) || '';

    const response = await fetch(
      `${base}/api/assistant/conversations/${conversationId}/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ content }),
      },
    );

    if (!response.ok) {
      onError(`HTTP ${response.status}`);
      return;
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const processEvents = (raw: string): string => {
      const blocks = raw.split('\n\n');
      const incomplete = blocks.pop() ?? '';
      for (const block of blocks) {
        if (!block.trim()) continue;
        let eventType = 'message';
        let eventData = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim();
          else if (line.startsWith('data: ')) eventData = line.slice(6).trim();
        }
        if (!eventData) continue;
        try {
          const parsed = JSON.parse(eventData);
          if (eventType === 'status') onStatus(parsed.content ?? '');
          else if (eventType === 'token') onToken(parsed.content ?? '');
          else if (eventType === 'done') onDone(parsed as Message);
          else if (eventType === 'error') onError(parsed.content ?? 'Unknown error');
        } catch { /* malformed JSON — skip */ }
      }
      return incomplete;
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = processEvents(buffer);
      }
      if (buffer.trim()) processEvents(buffer + '\n\n');
    } finally {
      reader.releaseLock();
    }
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

  // ── Smart ingestion pipeline ──────────────────────────────────────────────

  ingestParse: async (file: File): Promise<{
    upload_id: string;
    detected_entity_type: string;
    entity_subtype: string;
    entity_confidence: 'high' | 'medium' | 'low';
    from_cache: boolean;
    file_columns: string[];
    mapping_suggestions: Record<string, string>;
    schema_fields: string[];
    sample_rows: Record<string, unknown>[];
    total_rows: number;
    file_format: string;
  }> => {
    const fd = new FormData();
    fd.append('file', file);
    const response = await apiClient.post('/api/uploads/ingest/parse', fd);
    return response.data;
  },

  ingestValidate: async (uploadId: string, entityType: string, columnMapping: Record<string, string>): Promise<{
    upload_id: string;
    summary: { valid: number; warnings: number; errors: number; total: number };
    rows: Array<{
      row_id: number;
      status: 'valid' | 'warning' | 'error';
      errors: Array<{ field: string; message: string }>;
      warnings: Array<{ field: string; message: string }>;
      mapped: Record<string, unknown>;
    }>;
  }> => {
    const response = await apiClient.post(`/api/uploads/ingest/${uploadId}/validate`, {
      entity_type: entityType,
      column_mapping: columnMapping,
    });
    return response.data;
  },

  ingestCommit: async (uploadId: string, selectedRowIds: number[], syncToTally: boolean): Promise<{
    upload_id: string;
    started: boolean;
    total_selected: number;
    message: string;
  }> => {
    const response = await apiClient.post(`/api/uploads/ingest/${uploadId}/commit`, {
      selected_row_ids: selectedRowIds,
      sync_to_tally: syncToTally,
    });
    return response.data;
  },

  ingestStatus: async (uploadId: string): Promise<{
    upload_id: string;
    status: string;
    entity_type: string;
    total_rows: number;
    valid_rows: number;
    invalid_rows: number;
    imported_rows: number;
    tally_queued: number;
    commit_summary: Record<string, unknown> | null;
    completed_at: string | null;
  }> => {
    const response = await apiClient.get(`/api/uploads/ingest/${uploadId}/status`);
    return response.data;
  },
};

// ─── Reports ──────────────────────────────────────────────────────────────────

export const reportsApi = {
  generate: async (data: {
    type: string;
    date_from: string;
    date_to: string;
    party_id?: string;
    enable_ai_summary?: boolean;
    enable_ai_comparison?: boolean;
    comparison_basis?: string;
    comparison_period_start?: string;
    comparison_period_end?: string;
  }): Promise<Report> => {
    const response = await apiClient.post('/api/reports/generate', {
      report_type: data.type,
      period_start: data.date_from ? `${data.date_from}T00:00:00` : undefined,
      period_end: data.date_to ? `${data.date_to}T23:59:59` : undefined,
      party_id: data.party_id,
      enable_ai_summary: data.enable_ai_summary,
      enable_ai_comparison: data.enable_ai_comparison,
      comparison_basis: data.comparison_basis,
      comparison_period_start: data.comparison_period_start
        ? `${data.comparison_period_start}T00:00:00` : undefined,
      comparison_period_end: data.comparison_period_end
        ? `${data.comparison_period_end}T23:59:59` : undefined,
    });
    return response.data;
  },

  list: async (page = 1, pageSize = 10): Promise<{
    items: (Report & { ai_insights?: string })[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }> => {
    const response = await apiClient.get('/api/reports', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  delete: async (reportId: string): Promise<void> => {
    await apiClient.delete(`/api/reports/${reportId}`);
  },

  bulkDelete: async (ids: string[]): Promise<{ deleted: number }> => {
    const response = await apiClient.post('/api/reports/bulk-delete', { ids });
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
  payload?: Record<string, unknown>;
};

export type BulkDeleteEntityType =
  | 'ledger' | 'stock_item' | 'stock_group' | 'unit' | 'godown' | 'stock_category' | 'group';

export interface BulkDeleteApiResult {
  batch_id: string | null;
  tally_queued: number;
  deleted_immediately: number;
  errors: Array<{ id: string; name?: string; reason: string }>;
  has_connector: boolean;
}

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

export const bulkDeleteApi = {
  masters: async (entity_type: BulkDeleteEntityType, ids: string[]): Promise<BulkDeleteApiResult> => {
    const res = await apiClient.post('/api/management/bulk-delete', { entity_type, ids });
    return res.data;
  },
  vouchers: async (items: Array<{ id: string; entity_type: string }>): Promise<BulkDeleteApiResult> => {
    const res = await apiClient.post('/api/management/vouchers/bulk-delete', { items });
    return res.data;
  },
  uploads: async (ids: string[]): Promise<BulkDeleteApiResult> => {
    let deleted = 0;
    const errors: Array<{ id: string; reason: string }> = [];
    await Promise.all(ids.map(async (id) => {
      try {
        await apiClient.delete(`/api/uploads/${id}`);
        deleted++;
      } catch {
        errors.push({ id, reason: 'Delete failed' });
      }
    }));
    return { batch_id: null, tally_queued: 0, deleted_immediately: deleted, errors, has_connector: false };
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

  updateLedger: async (id: string, data: {
    name?: string; parent_group?: string; opening_balance?: number;
    email?: string; phone?: string; address?: string; country?: string; state?: string; gstin?: string;
  }) => {
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
    party_ledger?: string;
    account_ledger?: string;
    sales_ledger?: string;
    purchase_ledger?: string;
    dr_ledger?: string;
    cr_ledger?: string;
    from_account?: string;
    to_account?: string;
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

// ─── Export utility ──────────────────────────────────────────────────────────
// Triggers a file download using the File System Access API (Chrome/Edge) with
// a fallback to a standard anchor-based download for other browsers.

export type ExportFormat = 'csv' | 'xlsx' | 'json' | 'pdf';

const MIME: Record<ExportFormat, string> = {
  csv:  'text/csv',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  json: 'application/json',
  pdf:  'application/pdf',
};

const EXT_TYPES: Record<ExportFormat, { description: string; accept: Record<string, string[]> }> = {
  csv:  { description: 'CSV file',       accept: { 'text/csv': ['.csv'] } },
  xlsx: { description: 'Excel file',     accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] } },
  json: { description: 'JSON file',      accept: { 'application/json': ['.json'] } },
  pdf:  { description: 'PDF document',   accept: { 'application/pdf': ['.pdf'] } },
};

export async function downloadExport(
  url: string,
  params: Record<string, string | undefined>,
  filename: string,
  format: ExportFormat,
): Promise<void> {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v != null && v !== '')
  ) as Record<string, string>;

  // ── Step 1: acquire file handle FIRST (must happen synchronously within the
  //   user-gesture microtask — calling fetch first loses the gesture context and
  //   the browser silently falls back to auto-download without a directory prompt)
  let fileHandle: any = null;
  if ('showSaveFilePicker' in window) {
    try {
      fileHandle = await (window as any).showSaveFilePicker({
        suggestedName: filename,
        types: [{ description: EXT_TYPES[format].description, accept: EXT_TYPES[format].accept }],
      });
    } catch (e: any) {
      if (e?.name === 'AbortError') return; // user hit Cancel — don't fetch at all
      // SecurityError or other — fall through to anchor download
    }
  }

  // ── Step 2: fetch as ArrayBuffer — most compatible format for both paths
  const response = await apiClient.get(url, {
    params: cleanParams,
    responseType: 'arraybuffer',
  });
  const buffer: ArrayBuffer = response.data;

  // ── Step 3a: write to the chosen file (File System Access path)
  if (fileHandle) {
    const writable = await fileHandle.createWritable();
    await writable.write(buffer);
    await writable.close();
    return;
  }

  // ── Step 3b: fallback — standard anchor download (browser's default Downloads folder)
  const blob = new Blob([buffer], { type: MIME[format] });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

// ─── Reports (extended) ───────────────────────────────────────────────────────

export const reportsExtApi = {
  searchParties: async (
    q: string,
    partyType: 'customer' | 'vendor',
  ): Promise<{ id: string; name: string; gstin: string }[]> => {
    const res = await apiClient.get('/api/reports/parties/search', {
      params: { q, party_type: partyType },
    });
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
