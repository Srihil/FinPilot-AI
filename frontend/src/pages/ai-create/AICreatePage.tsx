import { useState, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Wand2, Zap, Loader2, CheckCircle, AlertCircle, RefreshCw,
  Activity, X, Clock, CheckCircle2, XCircle, RotateCcw, ChevronRight, Plus, Trash2,
} from 'lucide-react';
import { aiCreateApi, tallyApi, managementApi, type TallyJobItem } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { toast } from '../../components/ui/use-toast';
import { Combobox } from '../../components/ui/Combobox';
import type { TallyGodown, TallyStockItem, TallyUnit, TallyLedger } from '../../types';

// ─── Quick chips ─────────────────────────────────────────────────────────────

const QUICK_GROUPS = [
  {
    label: 'Accounting Masters',
    chips: ['Create Ledger account', 'Create account Group', 'Add Customer ledger', 'Add Vendor ledger'],
  },
  {
    label: 'Inventory Masters',
    chips: ['Add Stock Item / product', 'Create Stock Group', 'Create Unit of measure', 'Add Godown / warehouse'],
  },
  {
    label: 'Vouchers (Transactions)',
    chips: [
      'Create Sales Invoice', 'Record Purchase Bill', 'Record Receipt from customer',
      'Record Payment to vendor', 'Journal Entry', 'Credit Note (sales return)',
      'Debit Note (purchase return)', 'Contra / bank transfer',
      'Create GST Bill entry', 'Custom voucher type entry',
    ],
  },
  {
    label: 'Stock Transactions',
    chips: [
      'Transfer stock between godowns',
      'Record physical stock count',
      'Create Delivery Note for customer',
      'Create Receipt Note from supplier',
      'Rejection In — customer returns goods',
      'Rejection Out — return goods to supplier',
    ],
  },
];

const ENTITY_COLORS: Record<string, string> = {
  customer: 'bg-emerald-100 text-emerald-800',
  vendor: 'bg-blue-100 text-blue-800',
  ledger: 'bg-teal-100 text-teal-800',
  group: 'bg-teal-100 text-teal-800',
  sales_invoice: 'bg-indigo-100 text-indigo-800',
  purchase_bill: 'bg-orange-100 text-orange-800',
  invoice: 'bg-indigo-100 text-indigo-800',
  expense: 'bg-purple-100 text-purple-800',
  stock_item: 'bg-slate-100 text-slate-800',
  product: 'bg-slate-100 text-slate-800',
  stock_group: 'bg-slate-100 text-slate-800',
  unit: 'bg-slate-100 text-slate-800',
  godown: 'bg-amber-100 text-amber-800',
  receipt: 'bg-green-100 text-green-800',
  payment: 'bg-red-100 text-red-800',
  journal: 'bg-violet-100 text-violet-800',
  credit_note: 'bg-yellow-100 text-yellow-800',
  debit_note: 'bg-pink-100 text-pink-800',
  contra: 'bg-cyan-100 text-cyan-800',
  custom_voucher:  'bg-orange-100 text-orange-800',
  stock_journal:   'bg-indigo-100 text-indigo-800',
  physical_stock:  'bg-blue-100 text-blue-800',
  delivery_note:   'bg-green-100 text-green-800',
  receipt_note:    'bg-teal-100 text-teal-800',
  rejection_in:    'bg-orange-100 text-orange-800',
  rejection_out:   'bg-red-100 text-red-800',
};

// ─── Tally activity helpers ───────────────────────────────────────────────────

const OP_LABELS: Record<string, string> = {
  CREATE_LEDGER: 'Create Ledger',
  CREATE_STOCK_ITEM: 'Create Stock Item',
  CREATE_STOCK_GROUP: 'Create Stock Group',
  CREATE_UNIT: 'Create Unit',
  CREATE_GODOWN: 'Create Godown',
  CREATE_GROUP: 'Create Account Group',
  CREATE_SALES_VOUCHER: 'Create Sales Invoice',
  CREATE_PURCHASE_VOUCHER: 'Create Purchase Bill',
  CREATE_RECEIPT_VOUCHER: 'Create Receipt',
  CREATE_PAYMENT_VOUCHER: 'Create Payment',
  CREATE_JOURNAL_VOUCHER: 'Create Journal Entry',
  CREATE_CREDIT_NOTE: 'Create Credit Note',
  CREATE_DEBIT_NOTE: 'Create Debit Note',
  CREATE_CONTRA_VOUCHER: 'Bank / Cash Transfer',
  SYNC_FULL: 'Full Sync',
  SYNC_PARTIAL: 'Partial Sync',
  CREATE_STOCK_JOURNAL:  'Create Stock Journal',
  CREATE_PHYSICAL_STOCK: 'Create Physical Stock',
  CREATE_DELIVERY_NOTE:  'Create Delivery Note',
  CREATE_RECEIPT_NOTE:   'Create Receipt Note',
  CREATE_REJECTION_IN:   'Create Rejection In',
  CREATE_REJECTION_OUT:  'Create Rejection Out',
};

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function interpretError(error: string | null | undefined, operation: string): string {
  if (!error) return '';
  const e = error.toLowerCase();

  if (e.includes('bad unit name')) {
    return 'TallyPrime rejected the unit symbol — it must be a short abbreviation with no spaces (e.g. "Nos", "Kgs", "Pcs"). Open TallyPrime → Inventory Masters → Units of Measure, create the unit manually, then retry.';
  }
  if (e.includes('stock group') && e.includes('does not exist')) {
    const m = error.match(/'([^']+)'/);
    const grp = m?.[1] ?? 'the specified group';
    if (grp.toLowerCase() === 'primary') {
      return '"Primary" is not a named group in this TallyPrime company — the root is implicit. Create the stock group directly without a parent, or create a named parent group first via TallyPrime → Inventory Masters → Stock Groups.';
    }
    return `Parent stock group "${grp}" was not found in TallyPrime. Go to Inventory Masters → Stock Groups and create "${grp}" first, then retry.`;
  }
  if (e.includes('stock item') && e.includes('does not exist')) {
    const m = error.match(/'([^']+)'/);
    const item = m?.[1] ?? 'the stock item';
    return `TallyPrime could not find stock item "${item}". The name must match exactly (including capitalisation) what appears in TallyPrime → Inventory → Stock Items. Edit the item name in the preview and retry.`;
  }
  if (e.includes('ledger') && e.includes('does not exist')) {
    const m = error.match(/'([^']+)'/);
    const led = m?.[1] ?? 'the ledger';
    return `Ledger "${led}" does not exist in TallyPrime. Go to Accounts → Ledgers, create a ledger named "${led}" under the correct group, then retry.`;
  }
  if (e.includes('group') && e.includes('does not exist')) {
    const m = error.match(/'([^']+)'/);
    const grp = m?.[1] ?? 'the group';
    return `Account group "${grp}" was not found. Create it under Accounts → Groups in TallyPrime first.`;
  }
  if (e.includes('already exists') || e.includes('duplicate')) {
    return 'This entry already exists in TallyPrime — no action needed, it was already there.';
  }
  if (e.includes('no company') || e.includes('company not open')) {
    return 'No company file is open in TallyPrime. Open your company and retry.';
  }
  return error.replace(/^TallyPrime error:\s*/i, '').trim();
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; label: string; Icon: typeof Clock; spin?: boolean }> = {
    PENDING:  { cls: 'bg-amber-100 text-amber-800',   label: 'Pending',    Icon: Clock },
    CLAIMED:  { cls: 'bg-blue-100 text-blue-800',     label: 'Processing', Icon: Loader2, spin: true },
    RETRYING: { cls: 'bg-orange-100 text-orange-800', label: 'Retrying',   Icon: RotateCcw },
    SUCCESS:  { cls: 'bg-emerald-100 text-emerald-800', label: 'Success',  Icon: CheckCircle2 },
    FAILED:   { cls: 'bg-red-100 text-red-800',       label: 'Failed',     Icon: XCircle },
  };
  const c = cfg[status] ?? { cls: 'bg-slate-100 text-slate-700', label: status, Icon: Clock };
  const Icon = c.Icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${c.cls}`}>
      <Icon className={`w-3 h-3 ${c.spin ? 'animate-spin' : ''}`} />
      {c.label}
    </span>
  );
}

function JobCard({ job }: { job: TallyJobItem }) {
  const opLabel = OP_LABELS[job.operation] ?? job.operation.replace(/_/g, ' ');
  const smart = interpretError(job.error_message, job.operation);
  const isActive = job.status === 'PENDING' || job.status === 'CLAIMED' || job.status === 'RETRYING';

  return (
    <div className={`rounded-xl border p-3.5 space-y-2 transition-all
      ${job.status === 'FAILED' ? 'border-red-200 bg-red-50/60' :
        job.status === 'SUCCESS' ? 'border-emerald-200 bg-emerald-50/40' :
        isActive ? 'border-indigo-200 bg-indigo-50/40' :
        'border-slate-200 bg-white'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-slate-800 leading-tight">{opLabel}</p>
        <StatusBadge status={job.status} />
      </div>

      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Clock className="w-3 h-3 shrink-0" />
        <span>{timeAgo(job.created_at)}</span>
        {job.retry_count > 0 && (
          <span className="ml-auto text-orange-600 font-medium">retry {job.retry_count}</span>
        )}
      </div>

      {job.status === 'FAILED' && smart && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-100 border border-red-200">
          <AlertCircle className="w-3.5 h-3.5 text-red-600 shrink-0 mt-0.5" />
          <p className="text-xs text-red-800 leading-relaxed">{smart}</p>
        </div>
      )}

      {job.status === 'SUCCESS' && (
        <p className="text-xs text-emerald-700 font-medium flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Synced to TallyPrime successfully
        </p>
      )}
    </div>
  );
}

function ActivityDrawer({
  open,
  onClose,
  jobs,
  isLoading,
}: {
  open: boolean;
  onClose: () => void;
  jobs: TallyJobItem[];
  isLoading: boolean;
}) {
  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/40 z-40 transition-opacity duration-300
          ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-[400px] max-w-[95vw] bg-white shadow-2xl z-50
          flex flex-col transform transition-transform duration-300 ease-out
          ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shrink-0">
          <div className="flex items-center gap-2.5">
            <Activity className="w-5 h-5" />
            <div>
              <p className="font-semibold text-sm">Tally Sync Activity</p>
              <p className="text-indigo-200 text-xs">Latest command at the top</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/20 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="rounded-xl border p-3.5 space-y-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-3 w-24" />
                </div>
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                <Activity className="w-6 h-6 text-slate-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700">No activity yet</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Jobs appear here once you create something with AI
                </p>
              </div>
            </div>
          ) : (
            jobs.map(job => <JobCard key={job.id} job={job} />)
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t bg-slate-50 shrink-0">
          <p className="text-[11px] text-slate-400 text-center">
            Auto-refreshes every 5 seconds while open
          </p>
        </div>
      </div>
    </>
  );
}

// ─── Types ────────────────────────────────────────────────────────────────────

type ExtractionResult = {
  entity_type: string;
  data: Record<string, unknown>;
  confidence: number;
  missing_fields: string[];
};

type CreationResult = {
  id: string;
  entity_type: string;
  tally_queued: boolean;
};

function fieldLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const STOCK_TXN_TYPES = new Set([
  'stock_journal', 'physical_stock', 'delivery_note', 'receipt_note', 'rejection_in', 'rejection_out',
]);

const GODOWN_FIELDS = new Set(['from_godown', 'to_godown', 'godown']);
const PARTY_FIELDS  = new Set(['party_name', 'party_ledger']);

// ─── StockTxnEntriesEditor ────────────────────────────────────────────────────

interface StockEntry {
  stock_item_name: string;
  quantity: number | string;
  unit: string;
  rate: number | string;
  godown: string;
}

function StockTxnEntriesEditor({
  entries,
  onChange,
  stockItemNames,
  unitNames,
  godownNames,
  stockItemMap,
}: {
  entries: StockEntry[];
  onChange: (entries: StockEntry[]) => void;
  stockItemNames: string[];
  unitNames: string[];
  godownNames: string[];
  stockItemMap: Map<string, { unit: string; rate: number }>;
}) {
  const rows: StockEntry[] = entries.length > 0 ? entries : [{ stock_item_name: '', quantity: '', unit: '', rate: 0, godown: '' }];

  function setField(idx: number, field: keyof StockEntry, value: string | number) {
    const next = rows.map((r, i) => i === idx ? { ...r, [field]: value } : r);
    onChange(next);
  }

  function handleItem(idx: number, name: string) {
    const lookup = stockItemMap.get(name.toLowerCase());
    const next = rows.map((r, i) => i === idx ? {
      ...r,
      stock_item_name: name,
      unit: lookup?.unit || r.unit,
      rate: lookup && lookup.rate > 0 ? lookup.rate : r.rate,
    } : r);
    onChange(next);
  }

  function addRow() { onChange([...rows, { stock_item_name: '', quantity: '', unit: '', rate: 0, godown: '' }]); }
  function removeRow(idx: number) { onChange(rows.length === 1 ? rows : rows.filter((_, i) => i !== idx)); }

  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 border-b text-xs text-slate-500 uppercase tracking-wide">
            <th className="px-2 py-2 text-left">Stock Item</th>
            <th className="px-2 py-2 text-right w-20">Qty</th>
            <th className="px-2 py-2 text-left w-36">Unit</th>
            <th className="px-2 py-2 text-right w-28">Rate (₹)</th>
            <th className="px-2 py-2 w-7" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-b last:border-0">
              <td className="px-1.5 py-1">
                <Combobox options={stockItemNames} value={String(row.stock_item_name || '')}
                  onChange={v => handleItem(idx, v)} placeholder="Search items…" />
              </td>
              <td className="px-1.5 py-1">
                <Input type="number" min="0" value={String(row.quantity || '')}
                  onChange={e => setField(idx, 'quantity', e.target.value)}
                  placeholder="0" className="text-right text-xs" />
              </td>
              <td className="px-1.5 py-1">
                <Combobox options={unitNames} value={String(row.unit || '')}
                  onChange={v => setField(idx, 'unit', v)} placeholder="Unit…" />
              </td>
              <td className="px-1.5 py-1">
                <Input type="number" min="0" value={String(row.rate || '')}
                  onChange={e => setField(idx, 'rate', e.target.value)}
                  placeholder="0" className="text-right text-xs" />
              </td>
              <td className="px-1 py-1 text-center">
                <button onClick={() => removeRow(idx)}
                  className="p-1 rounded hover:bg-red-50 text-slate-300 hover:text-red-500"
                  disabled={rows.length === 1}>
                  <Trash2 className="w-3 h-3" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-3 py-2 border-t bg-slate-50">
        <button onClick={addRow}
          className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-3 h-3" /> Add Item
        </button>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AICreatePage() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [editableData, setEditableData] = useState<Record<string, unknown>>({});
  const [created, setCreated] = useState<CreationResult | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isStockTxn = extraction ? STOCK_TXN_TYPES.has(extraction.entity_type) : false;

  // Master data — only fetched when showing a stock txn preview
  const { data: godownsData } = useQuery({
    queryKey: ['godowns-all'],
    queryFn: () => managementApi.godowns({ page_size: 200 }),
    staleTime: 60_000,
    enabled: isStockTxn,
  });
  const { data: stockItemsData } = useQuery({
    queryKey: ['stock-items-all'],
    queryFn: () => managementApi.stockItems({ page_size: 500 }),
    staleTime: 60_000,
    enabled: isStockTxn,
  });
  const { data: unitsData } = useQuery({
    queryKey: ['units-all'],
    queryFn: () => managementApi.units({ page_size: 100 }),
    staleTime: 60_000,
    enabled: isStockTxn,
  });
  const { data: ledgersData } = useQuery({
    queryKey: ['ledgers-all'],
    queryFn: () => managementApi.ledgers({ page_size: 500 }),
    staleTime: 60_000,
    enabled: isStockTxn,
  });

  const godownNames  = useMemo(() => (godownsData?.items  ?? [] as TallyGodown[]).map(g => g.name),  [godownsData]);
  const stockItemNames = useMemo(() => (stockItemsData?.items ?? [] as TallyStockItem[]).map(i => i.name), [stockItemsData]);
  const unitNames    = useMemo(() => (unitsData?.items    ?? [] as TallyUnit[]).map(u => u.name),    [unitsData]);
  const ledgerNames  = useMemo(() => (ledgersData?.items  ?? [] as TallyLedger[]).map(l => l.name),  [ledgersData]);
  const stockItemMap = useMemo(() => {
    const m = new Map<string, { unit: string; rate: number }>();
    for (const item of (stockItemsData?.items ?? [] as TallyStockItem[])) {
      m.set(item.name.toLowerCase(), { unit: item.unit || '', rate: item.rate || 0 });
    }
    return m;
  }, [stockItemsData]);

  // ── Tally activity polling ────────────────────────────────────────────────
  const { data: activityData, isLoading: activityLoading } = useQuery({
    queryKey: ['tally-activity'],
    queryFn: () => tallyApi.activity(30),
    refetchInterval: drawerOpen ? 5000 : 20000,
    retry: false,
  });

  const jobs = activityData?.items ?? [];
  const pendingCount = jobs.filter(j =>
    j.status === 'PENDING' || j.status === 'CLAIMED' || j.status === 'RETRYING'
  ).length;
  const failedCount = jobs.filter(j => j.status === 'FAILED').length;

  // Dot colour for the trigger: red > amber > green > grey
  const dotCls =
    failedCount > 0 ? 'bg-red-500 animate-pulse' :
    pendingCount > 0 ? 'bg-amber-400 animate-pulse' :
    jobs.some(j => j.status === 'SUCCESS') ? 'bg-emerald-400' :
    'bg-slate-300';

  // ── Mutations ─────────────────────────────────────────────────────────────
  const extractMutation = useMutation({
    mutationFn: () => aiCreateApi.extractEntity(text),
    onSuccess: result => {
      setExtraction(result);
      setEditableData({ ...result.data });
      setCreated(null);
    },
    onError: () => {
      toast({ title: 'Extraction failed', description: 'Could not contact AI service.', variant: 'destructive' });
    },
  });

  const createMutation = useMutation({
    mutationFn: () => aiCreateApi.createEntity(extraction!.entity_type, editableData),
    onSuccess: result => {
      setCreated(result);
      // Invalidate all caches so navigating to any management page shows the new entry immediately
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      qc.invalidateQueries({ queryKey: ['invoices'] });
      qc.invalidateQueries({ queryKey: ['expenses'] });
      qc.invalidateQueries({ queryKey: ['customers'] });
      qc.invalidateQueries({ queryKey: ['vendors'] });
      qc.invalidateQueries({ queryKey: ['products'] });
      qc.invalidateQueries({ queryKey: ['ledgers'] });
      qc.invalidateQueries({ queryKey: ['stock-transactions'] });
      toast({
        title: `${fieldLabel(result.entity_type)} created`,
        description: result.tally_queued
          ? 'Queued for Tally sync — check status in the activity drawer.'
          : 'Saved to FinPilot (no Tally connector active).',
        variant: 'success',
      });
    },
    onError: (err: unknown) => {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Something went wrong.';
      toast({ title: 'Creation failed', description: message, variant: 'destructive' });
    },
  });

  function handleReset() {
    setText('');
    setExtraction(null);
    setEditableData({});
    setCreated(null);
  }

  const isLoading = extractMutation.isPending;
  const isCreating = createMutation.isPending;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Wand2 className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-slate-900">Create with AI</h1>
        </div>
        <p className="text-slate-500 text-sm">
          Describe anything in plain English — AI extracts the details
        </p>
      </div>

      {/* ── Input card ─────────────────────────────────────────────────────── */}
      {!created && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div>
              <Label htmlFor="ai-input" className="text-sm font-medium text-slate-700 mb-1.5 block">
                What would you like to create?
              </Label>
              <textarea
                id="ai-input"
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) extractMutation.mutate(); }}
                rows={4}
                placeholder="e.g. Add customer ABC Traders, email abc@traders.com, GST 27AABCU9603R1ZX..."
                className="w-full px-3 py-2 rounded-md border border-slate-200 text-sm text-slate-900
                  placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>

            {/* Quick-start chips */}
            <div className="space-y-3">
              {QUICK_GROUPS.map(group => (
                <div key={group.label}>
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                    {group.label}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {group.chips.map(chip => (
                      <button
                        key={chip}
                        onClick={() => setText(chip)}
                        className="text-xs px-2.5 py-1 rounded-full border border-slate-200 text-slate-600
                          hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700 transition-colors"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <Button onClick={() => extractMutation.mutate()} disabled={!text.trim() || isLoading} className="w-full">
              {isLoading ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Extracting...</>
              ) : (
                <><Wand2 className="w-4 h-4 mr-2" />Extract with AI</>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Loading skeleton ────────────────────────────────────────────────── */}
      {isLoading && (
        <Card>
          <CardHeader><Skeleton className="h-5 w-32" /></CardHeader>
          <CardContent className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="space-y-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-9 w-full" />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* ── Extraction preview ──────────────────────────────────────────────── */}
      {extraction && !isLoading && !created && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Preview</CardTitle>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full
                ${ENTITY_COLORS[extraction.entity_type] ?? 'bg-slate-100 text-slate-700'}`}>
                {fieldLabel(extraction.entity_type)}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <div className="flex-1 bg-slate-100 rounded-full h-1.5">
                <div
                  className="bg-indigo-500 h-1.5 rounded-full transition-all"
                  style={{ width: `${Math.round(extraction.confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs text-slate-500 shrink-0">
                {Math.round(extraction.confidence * 100)}% confidence
              </span>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="grid gap-3">
              {Object.entries(editableData).map(([key, val]) => {
                // ── Stock transaction: specialized rendering ───────────────
                if (isStockTxn) {
                  // Entries → table editor
                  if (key === 'entries') {
                    return (
                      <div key={key} className="space-y-1">
                        <Label className="text-xs font-medium text-slate-600">Stock Items (Entries)</Label>
                        <StockTxnEntriesEditor
                          entries={Array.isArray(val) ? (val as StockEntry[]) : []}
                          onChange={rows => setEditableData(prev => ({ ...prev, entries: rows }))}
                          stockItemNames={stockItemNames}
                          unitNames={unitNames}
                          godownNames={godownNames}
                          stockItemMap={stockItemMap}
                        />
                      </div>
                    );
                  }
                  // Godown fields → Combobox
                  if (GODOWN_FIELDS.has(key)) {
                    return (
                      <div key={key} className="space-y-1">
                        <Label className="text-xs font-medium text-slate-600">{fieldLabel(key)}</Label>
                        <Combobox
                          options={godownNames}
                          value={String(val || '')}
                          onChange={v => setEditableData(prev => ({ ...prev, [key]: v }))}
                          placeholder="Select godown…"
                        />
                      </div>
                    );
                  }
                  // Party fields → Combobox with ledgers
                  if (PARTY_FIELDS.has(key)) {
                    return (
                      <div key={key} className="space-y-1">
                        <Label className="text-xs font-medium text-slate-600">{fieldLabel(key)}</Label>
                        <Combobox
                          options={ledgerNames}
                          value={String(val || '')}
                          onChange={v => setEditableData(prev => ({ ...prev, [key]: v }))}
                          placeholder="Search ledgers…"
                        />
                      </div>
                    );
                  }
                }

                // ── Default: plain input / textarea ───────────────────────
                const isComplex = Array.isArray(val) || (typeof val === 'object' && val !== null);
                const displayVal = isComplex ? JSON.stringify(val) : (val != null ? String(val) : '');
                return (
                  <div key={key} className="space-y-1">
                    <Label htmlFor={`field-${key}`} className="text-xs font-medium text-slate-600">
                      {fieldLabel(key)}
                    </Label>
                    {isComplex ? (
                      <textarea
                        id={`field-${key}`}
                        rows={3}
                        value={displayVal}
                        onChange={e => {
                          try { setEditableData(prev => ({ ...prev, [key]: JSON.parse(e.target.value) })); }
                          catch { setEditableData(prev => ({ ...prev, [key]: e.target.value })); }
                        }}
                        className="w-full px-3 py-2 rounded-md border border-slate-200 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
                      />
                    ) : (
                      <Input
                        id={`field-${key}`}
                        value={displayVal}
                        onChange={e => setEditableData(prev => ({ ...prev, [key]: e.target.value }))}
                        className="text-sm"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {extraction.missing_fields?.length > 0 && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-medium text-amber-800">Missing information</p>
                  <p className="text-xs text-amber-700 mt-0.5">{extraction.missing_fields.join(', ')}</p>
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <Button variant="outline" size="sm" onClick={handleReset} className="flex-1">
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                Start Over
              </Button>
              <Button onClick={() => createMutation.mutate()} disabled={isCreating} size="sm" className="flex-1">
                {isCreating ? (
                  <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Creating...</>
                ) : (
                  <><Zap className="w-3.5 h-3.5 mr-1.5" />Create &amp; Sync to Tally</>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Success state ───────────────────────────────────────────────────── */}
      {created && (
        <Card className="border-emerald-200 bg-emerald-50">
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-8 h-8 text-emerald-600 shrink-0" />
              <div>
                <p className="font-semibold text-emerald-900">
                  {fieldLabel(created.entity_type)} created successfully
                </p>
                <p className="text-sm text-emerald-700 mt-0.5">
                  {created.tally_queued
                    ? 'Queued for sync to TallyPrime — tap the activity drawer to track status.'
                    : 'Saved to FinPilot (connect TallyPrime to sync).'}
                </p>
                {created.id && (
                  <p className="text-xs text-emerald-600 mt-1 font-mono">ID: {created.id}</p>
                )}
              </div>
            </div>

            {created.tally_queued && (
              <button
                onClick={() => setDrawerOpen(true)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-lg
                  border border-emerald-300 bg-white/60 hover:bg-white/80 transition-colors text-sm
                  text-emerald-800 font-medium"
              >
                <span className="flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  View Tally sync status
                </span>
                <ChevronRight className="w-4 h-4" />
              </button>
            )}

            <Button
              onClick={handleReset}
              variant="outline"
              className="w-full border-emerald-300 text-emerald-800 hover:bg-emerald-100"
            >
              <Wand2 className="w-4 h-4 mr-2" />
              Create Another
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Activity drawer trigger (always visible) ────────────────────────── */}
      <button
        onClick={() => setDrawerOpen(true)}
        className="fixed right-0 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center gap-1.5
          bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white
          px-2 py-5 rounded-l-xl shadow-xl transition-all duration-150 group"
        title="View Tally sync activity"
      >
        {/* Status dot */}
        <span className={`w-2 h-2 rounded-full ${dotCls}`} />
        <Activity className="w-4 h-4" />
        <span
          className="text-[10px] font-bold tracking-widest uppercase"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          Activity
        </span>
        {failedCount > 0 && (
          <span className="absolute -top-1.5 -left-1.5 w-5 h-5 rounded-full bg-red-500 text-white
            text-[10px] font-bold flex items-center justify-center shadow">
            {failedCount}
          </span>
        )}
      </button>

      {/* ── Activity drawer ─────────────────────────────────────────────────── */}
      <ActivityDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        jobs={jobs}
        isLoading={activityLoading}
      />
    </div>
  );
}
