// Auth Types
export interface User {
  id: string;
  email: string;
  full_name: string;
  company_name: string;
  role: 'ADMIN' | 'ACCOUNTANT' | 'VIEWER';
  is_active: boolean;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  confirm_password: string;
  full_name: string;
  company_name: string;
  accept_terms: boolean;
}

// Dashboard Types
export interface DashboardOverview {
  total_revenue: number;
  total_expenses: number;
  net_profit: number;
  outstanding_receivables: number;
  outstanding_payables: number;
  revenue_growth: number;
  expense_growth: number;
  recent_transactions: Transaction[];
  pending_approvals_count: number;
}

export interface DashboardCharts {
  monthly_data: MonthlyData[];
  expense_categories: CategoryData[];
  top_customers: CustomerRevenue[];
}

export interface MonthlyData {
  month: string;
  revenue: number;
  expenses: number;
  profit: number;
}

export interface CategoryData {
  name: string;
  value: number;
}

export interface CustomerRevenue {
  customer_name: string;
  revenue: number;
}

// Transaction Types
export type TransactionStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'PAID' | 'OVERDUE' | 'CANCELLED';
export type TransactionType = 'INVOICE' | 'EXPENSE' | 'PAYMENT' | 'CREDIT_NOTE';
export type InvoiceType = 'SALES' | 'PURCHASE';

export interface Transaction {
  id: string;
  type?: TransactionType;
  invoice_type?: InvoiceType;
  ref_number?: string;
  invoice_number?: string;
  date?: string;
  invoice_date?: string;
  due_date?: string;
  customer_id?: string;
  customer_name?: string;
  vendor_id?: string;
  vendor_name?: string;
  amount?: number;
  tax_amount?: number;
  total_amount: number;
  status: TransactionStatus;
  description?: string;
  created_at: string;
  updated_at?: string;
}

export interface Invoice extends Transaction {
  line_items: LineItem[];
  notes?: string;
}

export interface LineItem {
  id?: string;
  product_id?: string;
  description: string;
  quantity: number;
  unit_price: number;
  tax_rate?: number;
  amount: number;
}

export interface Expense {
  id: string;
  ref_number?: string;
  date?: string;
  expense_date?: string;
  vendor_id?: string;
  vendor_name?: string;
  title?: string;
  category?: string;
  amount: number;
  tax_amount?: number;
  total_amount: number;
  status: TransactionStatus;
  description?: string;
  reference_number?: string;
  receipt_url?: string;
  created_at: string;
}

// Customer Types
export interface Customer {
  id: string;
  company_id: string;
  name: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  country?: string;
  pincode?: string;
  gst_number?: string;
  pan_number?: string;
  credit_limit?: number;
  payment_terms_days?: number;
  total_revenue: number;
  outstanding_balance: number;
  is_active: boolean;
  notes?: string;
  created_at: string;
}

// Vendor Types
export interface Vendor {
  id: string;
  company_id: string;
  name: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  country?: string;
  pincode?: string;
  gst_number?: string;
  pan_number?: string;
  payment_terms_days?: number;
  total_purchases: number;
  outstanding_payable: number;
  is_active: boolean;
  notes?: string;
  created_at: string;
}

// Product/Inventory Types
export interface Product {
  id: string;
  sku: string;
  name: string;
  description?: string;
  category: string;
  unit: string;
  unit_price: number;
  cost_price?: number;
  stock_quantity: number;
  low_stock_threshold: number;
  is_low_stock: boolean;
  total_value: number;
  status: 'ACTIVE' | 'INACTIVE';
  created_at: string;
}

// Approval Types
export interface Approval {
  id: string;
  transaction_id: string;
  transaction_type: TransactionType;
  transaction_ref: string;
  amount: number;
  requested_by: string;
  requested_by_name: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  notes?: string;
  validation_warnings?: string[];
  created_at: string;
  reviewed_at?: string;
  reviewed_by?: string;
}

// Analytics Types
export interface AnalyticsOverview {
  revenue: number;
  expenses: number;
  net_profit: number;
  profit_margin: number;
  outstanding_receivables: number;
  outstanding_payables: number;
  customer_count: number;
  vendor_count: number;
}

export interface AnalyticsCharts {
  monthly: MonthlyData[];
  customer_revenue: CustomerRevenue[];
  expense_categories: CategoryData[];
  invoice_status: { status: string; count: number }[];
  receivables_aging: { bucket: string; amount: number }[];
}

export interface VendorSpend {
  vendor_name: string;
  amount: number;
}

// Audit Log Types
export interface AuditLog {
  id: string;
  user_id: string;
  user_name: string;
  action: string;
  entity_type: string;
  entity_id?: string;
  description: string;
  status: 'SUCCESS' | 'FAILURE';
  ip_address?: string;
  created_at: string;
}

// Assistant Types
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  conversation_id?: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  is_demo?: boolean;
  provider?: string;
  error?: string;
  tool_calls?: unknown[];
  tool_results?: unknown[];
}

// Upload Types
export interface UploadResult {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  errors: UploadError[];
  preview_data: Record<string, unknown>[];
}

export interface UploadError {
  row: number;
  field: string;
  message: string;
}

// Report Types
export interface Report {
  id: string;
  report_type: string;
  title: string;
  period_start?: string;
  period_end?: string;
  download_url?: string;
  created_at: string;
}

// Settings Types
export interface CompanySettings {
  name: string;
  email: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  pincode?: string;
  gstin?: string;
  pan?: string;
  logo_url?: string;
  financial_year_start: string;
  currency: string;
}

export interface AIProvider {
  id: string;
  name: string;
  description: string;
  configured: boolean;
}

export interface AISettings {
  provider: 'demo' | 'groq' | 'openrouter' | 'ollama';
  is_demo_mode: boolean;
  available_providers: AIProvider[];
}

// Pagination Types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Common Types
export interface ApiError {
  detail: string;
  status_code?: number;
}

// ─── Management / Tally Master Types ──────────────────────────────────────────

export type TallySyncStatus = 'pending' | 'synced' | 'failed';
export type TallySource = 'tally_sync' | 'finpilot';

export interface TallyLedger {
  id: string;
  name: string;
  parent_group?: string;
  opening_balance: number;
  closing_balance: number;
  source: TallySource;
  tally_sync_status: TallySyncStatus;
  synced_at?: string;
  created_at: string;
}

export interface TallyStockGroup {
  id: string;
  name: string;
  parent?: string;
  source: TallySource;
  tally_sync_status: TallySyncStatus;
  synced_at?: string;
  created_at: string;
}

export interface TallyUnit {
  id: string;
  name: string;
  symbol?: string;
  decimal_places: number;
  unit_type: string;
  source: TallySource;
  tally_sync_status: TallySyncStatus;
  synced_at?: string;
  created_at: string;
}

export interface TallyGodown {
  id: string;
  name: string;
  parent?: string;
  source: TallySource;
  tally_sync_status: TallySyncStatus;
  synced_at?: string;
  created_at: string;
}

export interface ManagementOverview {
  totals: {
    customers: number;
    vendors: number;
    products: number;
    ledgers: number;
    stock_groups: number;
    units: number;
    godowns: number;
    vouchers: number;
  };
  sync: {
    pending_jobs: number;
    failed_jobs: number;
    last_sync: string | null;
  };
  tally: {
    connected: boolean;
    online: boolean;
    company: string | null;
    connector_name: string | null;
    device: string | null;
    last_heartbeat: string | null;
  };
}

export interface VoucherItem {
  id: string;
  voucher_number: string;
  date?: string;
  voucher_type: string;
  party?: string;
  amount: number;
  status: string;
  source: TallySource;
  tally_sync_status: TallySyncStatus;
  created_at: string;
  entity_type: 'invoice' | 'expense';
  title?: string;
}

export interface SyncHealth {
  total_jobs: number;
  successful: number;
  failed: number;
  pending: number;
  retrying: number;
  last_successful_sync: string | null;
  recent_jobs: Array<{
    id: string;
    operation: string;
    status: string;
    retry_count: number;
    error_message: string | null;
    created_at: string;
    completed_at: string | null;
  }>;
}
