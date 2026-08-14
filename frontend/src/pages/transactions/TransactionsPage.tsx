import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, Filter, Plus, Sparkles, PenLine, AlertTriangle, CheckCircle, Loader2, ChevronRight } from 'lucide-react';
import { invoicesApi, expensesApi, assistantApi } from '../../api/endpoints';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { StatusBadge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { formatCurrency, formatDate, extractApiError } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import type { Transaction, Expense } from '../../types';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Pagination({ page, totalPages, onPageChange }: { page: number; totalPages: number; onPageChange: (p: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 mt-4">
      <Button variant="outline" size="sm" onClick={() => onPageChange(page - 1)} disabled={page === 1}>Previous</Button>
      <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
      <Button variant="outline" size="sm" onClick={() => onPageChange(page + 1)} disabled={page === totalPages}>Next</Button>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
        <Filter className="w-6 h-6 text-slate-400" />
      </div>
      <p className="text-slate-500 text-sm">{message}</p>
    </div>
  );
}

// ─── Create Transaction Dialog ────────────────────────────────────────────────

interface ProposedTransaction {
  transaction_type: string;
  vendor_name?: string;
  customer_name?: string;
  category?: string;
  amount: number;
  tax_amount: number;
  description: string;
  date?: string;
  reference_number?: string;
  vendor_id?: string;
  vendor_matched?: string;
  confidence: number;
}

interface ValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

function AIProposalStep({
  onProposed,
}: {
  onProposed: (proposed: ProposedTransaction, validation: ValidationResult) => void;
}) {
  const [text, setText] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const EXAMPLES = [
    'Create an expense of ₹12,500 for office supplies from ABC Traders',
    'Record a payment of ₹45,000 for electricity bill for July',
    'Add a travel expense of ₹8,200 for client visit to Delhi',
    'Create an expense of ₹25,000 for software subscription (annual)',
  ];

  const handleExtract = async () => {
    if (!text.trim()) return;
    setIsLoading(true);
    try {
      const result = await assistantApi.proposeTransaction(text);
      onProposed(result.proposed, result.validation);
    } catch (err) {
      toast({ title: 'Extraction failed', description: extractApiError(err), variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
        <div className="flex gap-2 mb-1">
          <Sparkles className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
          <p className="text-sm font-medium text-indigo-800">Describe the transaction in plain English</p>
        </div>
        <p className="text-xs text-indigo-600 ml-6">
          AI will extract the structured data. You'll review everything before it's saved.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Transaction description</Label>
        <Textarea
          placeholder="e.g. Create an expense of ₹12,500 for office supplies from ABC Traders"
          value={text}
          onChange={e => setText(e.target.value)}
          rows={3}
          className="resize-none"
          onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) handleExtract(); }}
        />
        <p className="text-xs text-slate-400">Ctrl+Enter to extract</p>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Try an example</p>
        <div className="space-y-1">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => setText(ex)}
              className="w-full text-left text-xs text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 px-2.5 py-1.5 rounded-lg transition-colors flex items-center gap-1.5"
            >
              <ChevronRight className="w-3 h-3 shrink-0" />
              {ex}
            </button>
          ))}
        </div>
      </div>

      <Button onClick={handleExtract} loading={isLoading} disabled={!text.trim()} className="w-full">
        <Sparkles className="w-4 h-4 mr-2" />
        {isLoading ? 'Extracting…' : 'Extract & Preview'}
      </Button>
    </div>
  );
}

function ProposalPreview({
  proposed,
  validation,
  onConfirm,
  onBack,
  isSubmitting,
}: {
  proposed: ProposedTransaction;
  validation: ValidationResult;
  onConfirm: (edited: ProposedTransaction) => void;
  onBack: () => void;
  isSubmitting: boolean;
}) {
  const [edited, setEdited] = useState<ProposedTransaction>({ ...proposed });

  const field = (label: string, value: string | number | undefined, key: keyof ProposedTransaction, type = 'text') => (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        type={type}
        value={String(edited[key] ?? '')}
        onChange={e => setEdited(prev => ({ ...prev, [key]: type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value }))}
        className="h-8 text-sm"
      />
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Validation status */}
      {validation.errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1">
          {validation.errors.map(e => (
            <div key={e} className="flex gap-2 text-xs text-red-700">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {e}
            </div>
          ))}
        </div>
      )}
      {validation.warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
          {validation.warnings.map(w => (
            <div key={w} className="flex gap-2 text-xs text-amber-700">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              {w}
            </div>
          ))}
        </div>
      )}
      {validation.is_valid && validation.warnings.length === 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 flex gap-2 text-xs text-emerald-700">
          <CheckCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          All fields validated. Review and confirm.
        </div>
      )}

      {/* Editable fields */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Transaction Type</Label>
          <Select value={edited.transaction_type} onValueChange={v => setEdited(p => ({ ...p, transaction_type: v }))}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="expense">Expense</SelectItem>
              <SelectItem value="sales_invoice">Sales Invoice</SelectItem>
              <SelectItem value="purchase_invoice">Purchase Invoice</SelectItem>
              <SelectItem value="payment_received">Payment Received</SelectItem>
              <SelectItem value="payment_made">Payment Made</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Category</Label>
          <Select value={edited.category || ''} onValueChange={v => setEdited(p => ({ ...p, category: v }))}>
            <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select category" /></SelectTrigger>
            <SelectContent>
              {['Office Supplies','Utilities','Rent','Salaries','Travel','Marketing',
                'Software','Equipment','Maintenance','Professional Services',
                'Raw Materials','Shipping','Insurance','Miscellaneous'].map(c => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {field('Vendor / Party', edited.vendor_name, 'vendor_name')}
        {field('Amount (₹)', edited.amount, 'amount', 'number')}
        {field('Tax Amount (₹)', edited.tax_amount, 'tax_amount', 'number')}
        {field('Reference Number', edited.reference_number, 'reference_number')}
      </div>

      <div className="space-y-1">
        <Label className="text-xs">Description</Label>
        <Textarea
          value={edited.description}
          onChange={e => setEdited(p => ({ ...p, description: e.target.value }))}
          rows={2}
          className="resize-none text-sm"
        />
      </div>

      {/* Total */}
      <div className="bg-slate-50 rounded-lg p-3 flex items-center justify-between">
        <span className="text-sm text-slate-600">Total (amount + tax)</span>
        <span className="text-lg font-bold text-slate-900">
          {formatCurrency((edited.amount || 0) + (edited.tax_amount || 0))}
        </span>
      </div>

      <div className="flex gap-2 pt-1">
        <Button variant="outline" onClick={onBack} className="flex-1">Back</Button>
        <Button
          onClick={() => onConfirm(edited)}
          loading={isSubmitting}
          disabled={!validation.is_valid && validation.errors.length > 0}
          className="flex-2"
        >
          <CheckCircle className="w-4 h-4 mr-2" />
          Create Draft
        </Button>
      </div>
    </div>
  );
}

function ManualCreateForm({ onClose }: { onClose: () => void }) {
  const [type, setType] = useState<'expense' | 'invoice'>('expense');
  const [form, setForm] = useState({
    title: '', category: '', amount: '', tax_amount: '0',
    vendor_id: '', description: '', reference_number: '',
    invoice_number: '', customer_id: '',
  });
  const queryClient = useQueryClient();

  const expenseMutation = useMutation({
    mutationFn: (data: Parameters<typeof expensesApi.create>[0]) => expensesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses'] });
      toast({ title: 'Expense draft created', description: 'Submit for approval when ready.', variant: 'success' });
      onClose();
    },
    onError: (err) => toast({ title: 'Failed', description: extractApiError(err), variant: 'destructive' }),
  });

  const handleSubmit = () => {
    if (!form.title || !form.amount) {
      toast({ title: 'Missing fields', description: 'Title and amount are required.', variant: 'destructive' });
      return;
    }
    expenseMutation.mutate({
      title: form.title,
      category: form.category || 'Miscellaneous',
      amount: parseFloat(form.amount),
      tax_amount: parseFloat(form.tax_amount) || 0,
      expense_date: new Date().toISOString(),
      description: form.description,
      reference_number: form.reference_number || undefined,
      vendor_id: form.vendor_id || undefined,
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(['expense', 'invoice'] as const).map(t => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={cn(
              'flex-1 py-2 px-3 rounded-lg text-sm font-medium border-2 transition-all',
              type === t ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 text-slate-600 hover:border-slate-300'
            )}
          >
            {t === 'expense' ? '💸 Expense' : '📄 Invoice'}
          </button>
        ))}
      </div>

      {type === 'invoice' && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700">
          For invoice creation, use the AI-assisted tab for the best experience.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2 space-y-1">
          <Label className="text-xs">Title *</Label>
          <Input placeholder="e.g. July Electricity Bill" value={form.title}
            onChange={e => setForm(p => ({ ...p, title: e.target.value }))} className="h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Category</Label>
          <Select value={form.category} onValueChange={v => setForm(p => ({ ...p, category: v }))}>
            <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Select…" /></SelectTrigger>
            <SelectContent>
              {['Office Supplies','Utilities','Rent','Salaries','Travel','Marketing',
                'Software','Equipment','Maintenance','Professional Services',
                'Raw Materials','Shipping','Insurance','Miscellaneous'].map(c => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Reference No.</Label>
          <Input placeholder="INV-001" value={form.reference_number}
            onChange={e => setForm(p => ({ ...p, reference_number: e.target.value }))} className="h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Amount (₹) *</Label>
          <Input type="number" placeholder="0.00" value={form.amount}
            onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} className="h-8 text-sm" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Tax Amount (₹)</Label>
          <Input type="number" placeholder="0.00" value={form.tax_amount}
            onChange={e => setForm(p => ({ ...p, tax_amount: e.target.value }))} className="h-8 text-sm" />
        </div>
        <div className="col-span-2 space-y-1">
          <Label className="text-xs">Description</Label>
          <Textarea placeholder="Optional notes…" value={form.description}
            onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={2} className="resize-none text-sm" />
        </div>
      </div>

      {form.amount && (
        <div className="bg-slate-50 rounded-lg p-3 flex items-center justify-between">
          <span className="text-sm text-slate-600">Total</span>
          <span className="text-lg font-bold text-slate-900">
            {formatCurrency((parseFloat(form.amount) || 0) + (parseFloat(form.tax_amount) || 0))}
          </span>
        </div>
      )}

      <Button onClick={handleSubmit} loading={expenseMutation.isPending} className="w-full">
        <CheckCircle className="w-4 h-4 mr-2" />
        Create Draft
      </Button>
      <p className="text-xs text-slate-400 text-center">
        This creates a draft — submit for approval before it's committed.
      </p>
    </div>
  );
}

function CreateTransactionDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<'ai' | 'manual'>('ai');
  const [proposed, setProposed] = useState<ProposedTransaction | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryClient = useQueryClient();

  const handleClose = () => {
    setProposed(null);
    setValidation(null);
    setMode('ai');
    onClose();
  };

  const handleProposed = (p: ProposedTransaction, v: ValidationResult) => {
    setProposed(p);
    setValidation(v);
  };

  const handleConfirm = async (edited: ProposedTransaction) => {
    setIsSubmitting(true);
    try {
      if (edited.transaction_type === 'expense' || edited.transaction_type === 'payment_made') {
        await expensesApi.create({
          title: edited.description || edited.vendor_name || 'Expense',
          category: edited.category || 'Miscellaneous',
          amount: edited.amount,
          tax_amount: edited.tax_amount,
          expense_date: edited.date || new Date().toISOString(),
          description: edited.description,
          vendor_id: edited.vendor_id,
          reference_number: edited.reference_number,
        });
        queryClient.invalidateQueries({ queryKey: ['expenses'] });
      }
      toast({
        title: 'Draft created',
        description: 'Transaction saved as draft. Go to Approvals to submit for review.',
        variant: 'success',
      });
      handleClose();
    } catch (err) {
      toast({ title: 'Failed to create', description: extractApiError(err), variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <Plus className="w-4 h-4 text-white" />
            </div>
            Create Transaction
          </DialogTitle>
        </DialogHeader>

        {/* Mode switcher — only show when not in proposal review */}
        {!proposed && (
          <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
            <button
              onClick={() => setMode('ai')}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-sm font-medium transition-all',
                mode === 'ai' ? 'bg-white shadow-sm text-indigo-700' : 'text-slate-500 hover:text-slate-700'
              )}
            >
              <Sparkles className="w-3.5 h-3.5" /> AI-Assisted
            </button>
            <button
              onClick={() => setMode('manual')}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md text-sm font-medium transition-all',
                mode === 'manual' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-700'
              )}
            >
              <PenLine className="w-3.5 h-3.5" /> Manual
            </button>
          </div>
        )}

        {/* Content */}
        {proposed && validation ? (
          <ProposalPreview
            proposed={proposed}
            validation={validation}
            onConfirm={handleConfirm}
            onBack={() => { setProposed(null); setValidation(null); }}
            isSubmitting={isSubmitting}
          />
        ) : mode === 'ai' ? (
          <AIProposalStep onProposed={handleProposed} />
        ) : (
          <ManualCreateForm onClose={handleClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

// ─── Tables ───────────────────────────────────────────────────────────────────

function InvoicesTable() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['invoices', page, search, status],
    queryFn: () => invoicesApi.list({ page, page_size: 20, status: status || undefined }),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search invoices…" className="pl-9" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All statuses</SelectItem>
            <SelectItem value="DRAFT">Draft</SelectItem>
            <SelectItem value="PENDING_APPROVAL">Pending Approval</SelectItem>
            <SelectItem value="APPROVED">Approved</SelectItem>
            <SelectItem value="PAID">Paid</SelectItem>
            <SelectItem value="OVERDUE">Overdue</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12" />)}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                {['Date','Reference','Customer','Type','Amount','Status'].map(h => (
                  <th key={h} className={cn("py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide",
                    h === 'Amount' ? 'text-right' : 'text-left')}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data?.items?.length ? data.items.map((tx: Transaction) => (
                <tr key={tx.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                  <td className="py-3 px-4 text-slate-600">{formatDate(tx.invoice_date || tx.date)}</td>
                  <td className="py-3 px-4 font-medium text-slate-900">{tx.invoice_number || tx.ref_number}</td>
                  <td className="py-3 px-4 text-slate-600">{tx.customer_name || '-'}</td>
                  <td className="py-3 px-4"><StatusBadge status={tx.invoice_type || tx.type} /></td>
                  <td className="py-3 px-4 text-right font-semibold">{formatCurrency(tx.total_amount)}</td>
                  <td className="py-3 px-4"><StatusBadge status={tx.status} /></td>
                </tr>
              )) : (
                <tr><td colSpan={6}><EmptyState message="No invoices found" /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />}
    </div>
  );
}

function ExpensesTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['expenses', page, status],
    queryFn: () => expensesApi.list({ page, page_size: 20, status: status || undefined }),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue placeholder="All statuses" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="">All statuses</SelectItem>
            <SelectItem value="DRAFT">Draft</SelectItem>
            <SelectItem value="PENDING_APPROVAL">Pending Approval</SelectItem>
            <SelectItem value="APPROVED">Approved</SelectItem>
            <SelectItem value="PAID">Paid</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {isLoading ? (
        <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12" />)}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                {['Date','Title','Vendor','Category','Amount','Status'].map(h => (
                  <th key={h} className={cn("py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide",
                    h === 'Amount' ? 'text-right' : 'text-left')}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data?.items?.length ? data.items.map((exp: Expense) => (
                <tr key={exp.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                  <td className="py-3 px-4 text-slate-600">{formatDate(exp.expense_date || exp.date)}</td>
                  <td className="py-3 px-4 font-medium text-slate-900">{exp.title}</td>
                  <td className="py-3 px-4 text-slate-600">{exp.vendor_name || '-'}</td>
                  <td className="py-3 px-4 text-slate-600">{exp.category || '-'}</td>
                  <td className="py-3 px-4 text-right font-semibold">{formatCurrency(exp.total_amount)}</td>
                  <td className="py-3 px-4"><StatusBadge status={exp.status} /></td>
                </tr>
              )) : (
                <tr><td colSpan={6}><EmptyState message="No expenses found" /></td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={page} totalPages={data.total_pages} onPageChange={setPage} />}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TransactionsPage() {
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">All Transactions</h2>
          <p className="text-sm text-slate-500">Manage invoices, expenses and payments</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Transaction
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          <Tabs defaultValue="invoices">
            <TabsList className="mb-6">
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="invoices">Invoices</TabsTrigger>
              <TabsTrigger value="expenses">Expenses</TabsTrigger>
              <TabsTrigger value="payments">Payments</TabsTrigger>
            </TabsList>
            <TabsContent value="all"><InvoicesTable /></TabsContent>
            <TabsContent value="invoices"><InvoicesTable /></TabsContent>
            <TabsContent value="expenses"><ExpensesTable /></TabsContent>
            <TabsContent value="payments">
              <EmptyState message="No payments recorded yet" />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <CreateTransactionDialog open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  );
}
