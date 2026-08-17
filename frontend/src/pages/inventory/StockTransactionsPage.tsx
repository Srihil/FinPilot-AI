import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftRight, Plus, Search, Loader2, AlertCircle, Trash2, X,
  ChevronDown, ChevronRight, MoveRight, Package, MapPin, User2,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import { formatDate, formatCurrency } from '../../utils/format';
import apiClient from '../../api/client';
import { managementApi } from '../../api/endpoints';
import type { TallyGodown, TallyStockItem, TallyUnit, TallyLedger } from '../../types';


// ─── Types ────────────────────────────────────────────────────────────────────

interface StockEntry {
  stock_item_name: string;
  quantity: number;
  unit?: string;
  rate?: number;
  godown?: string;
}

interface StockTxn {
  id: string;
  transaction_number: string;
  transaction_type: string;
  transaction_type_label: string;
  transaction_date?: string;
  narration?: string;
  party_name?: string;
  from_godown?: string;
  to_godown?: string;
  entries: StockEntry[];
  tally_sync_status: string;
}

interface EntryRow {
  stock_item_name: string;
  quantity: string;
  unit: string;
  rate: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TYPE_META: Record<string, { color: string; label: string }> = {
  STOCK_JOURNAL:   { color: 'bg-indigo-100 text-indigo-700 border border-indigo-200',  label: 'Stock Journal' },
  PHYSICAL_STOCK:  { color: 'bg-sky-100 text-sky-700 border border-sky-200',           label: 'Physical Stock' },
  DELIVERY_NOTE:   { color: 'bg-emerald-100 text-emerald-700 border border-emerald-200', label: 'Delivery Note' },
  RECEIPT_NOTE:    { color: 'bg-teal-100 text-teal-700 border border-teal-200',        label: 'Receipt Note' },
  REJECTION_IN:    { color: 'bg-orange-100 text-orange-700 border border-orange-200',  label: 'Rejections In' },
  REJECTION_OUT:   { color: 'bg-red-100 text-red-700 border border-red-200',           label: 'Rejections Out' },
};

const TRANSACTION_TYPES = [
  { value: 'STOCK_JOURNAL',  label: 'Stock Journal' },
  { value: 'PHYSICAL_STOCK', label: 'Physical Stock' },
  { value: 'DELIVERY_NOTE',  label: 'Delivery Note' },
  { value: 'RECEIPT_NOTE',   label: 'Receipt Note' },
  { value: 'REJECTION_IN',   label: 'Rejections In' },
  { value: 'REJECTION_OUT',  label: 'Rejections Out' },
];

const PARTY_TYPES = new Set(['DELIVERY_NOTE', 'RECEIPT_NOTE', 'REJECTION_IN', 'REJECTION_OUT']);
const BLANK_ENTRY: EntryRow = { stock_item_name: '', quantity: '', unit: '', rate: '' };

const api = {
  list:   (p: Record<string, unknown>) => apiClient.get('/api/inventory/stock-transactions', { params: p }).then(r => r.data),
  create: (d: object) => apiClient.post('/api/inventory/stock-transactions', d).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/api/inventory/stock-transactions/${id}`).then(r => r.data),
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function entryPreview(entries: StockEntry[]): string {
  if (!entries?.length) return '—';
  return entries
    .slice(0, 2)
    .map(e => {
      const qty  = e.quantity ? `${e.quantity}` : '';
      const unit = e.unit ? ` ${e.unit}` : '';
      return `${qty}${unit} ${e.stock_item_name}`.trim();
    })
    .join(', ') + (entries.length > 2 ? ` +${entries.length - 2} more` : '');
}

function totalAmount(entries: StockEntry[]): number {
  return entries.reduce((s, e) => s + (e.quantity || 0) * (e.rate || 0), 0);
}

// ─── Expanded detail row ──────────────────────────────────────────────────────

function TxnDetail({ txn }: { txn: StockTxn }) {
  const hasGodowns = txn.transaction_type === 'STOCK_JOURNAL' || txn.transaction_type === 'PHYSICAL_STOCK';
  const hasParty   = PARTY_TYPES.has(txn.transaction_type);
  const total      = totalAmount(txn.entries);

  return (
    <div className="bg-slate-50 border-t border-slate-100 px-6 py-4 space-y-4">
      {/* Meta row */}
      <div className="flex flex-wrap gap-4 text-sm">
        {hasParty && txn.party_name && (
          <div className="flex items-center gap-1.5 text-slate-600">
            <User2 className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-medium text-slate-800">{txn.party_name}</span>
          </div>
        )}
        {txn.transaction_type === 'STOCK_JOURNAL' && (
          <div className="flex items-center gap-2 text-slate-600">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-medium text-slate-800">{txn.from_godown || '—'}</span>
            <MoveRight className="w-4 h-4 text-indigo-400" />
            <span className="font-medium text-slate-800">{txn.to_godown || '—'}</span>
          </div>
        )}
        {txn.transaction_type === 'PHYSICAL_STOCK' && txn.from_godown && (
          <div className="flex items-center gap-1.5 text-slate-600">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500">Godown:</span>
            <span className="font-medium text-slate-800">{txn.from_godown}</span>
          </div>
        )}
        {hasParty && txn.from_godown && (
          <div className="flex items-center gap-1.5 text-slate-600">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500">Godown:</span>
            <span className="font-medium text-slate-800">{txn.from_godown}</span>
          </div>
        )}
        {txn.narration && (
          <div className="text-slate-400 italic text-xs self-center">{txn.narration}</div>
        )}
      </div>

      {/* Entries table */}
      {txn.entries?.length > 0 && (
        <div className="rounded-lg border border-slate-200 overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-100 text-xs text-slate-500 uppercase tracking-wide border-b">
                <th className="px-4 py-2 text-left">Stock Item</th>
                <th className="px-4 py-2 text-right w-24">Quantity</th>
                <th className="px-4 py-2 text-left w-20">Unit</th>
                <th className="px-4 py-2 text-right w-28">Rate</th>
                <th className="px-4 py-2 text-right w-28">Amount</th>
                {txn.entries.some(e => e.godown) && (
                  <th className="px-4 py-2 text-left w-32">Godown</th>
                )}
              </tr>
            </thead>
            <tbody>
              {txn.entries.map((e, i) => {
                const amount = (e.quantity || 0) * (e.rate || 0);
                return (
                  <tr key={i} className="border-b last:border-0 hover:bg-slate-50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <Package className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                        <span className="font-medium text-slate-800">{e.stock_item_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold text-slate-800">
                      {e.quantity ?? '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      {e.unit
                        ? <span className="bg-slate-100 text-slate-600 text-xs px-1.5 py-0.5 rounded font-mono">{e.unit}</span>
                        : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right text-slate-600">
                      {e.rate ? formatCurrency(e.rate) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold text-slate-800">
                      {amount > 0 ? formatCurrency(amount) : <span className="text-slate-300">—</span>}
                    </td>
                    {txn.entries.some(en => en.godown) && (
                      <td className="px-4 py-2.5 text-xs text-slate-500">{e.godown || '—'}</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
            {total > 0 && (
              <tfoot>
                <tr className="bg-slate-50 border-t">
                  <td colSpan={txn.entries.some(e => e.godown) ? 5 : 4} className="px-4 py-2 text-right text-xs text-slate-500 font-medium uppercase">Total</td>
                  <td className="px-4 py-2 text-right font-bold text-slate-900">{formatCurrency(total)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StockTransactionsPage() {
  const qc = useQueryClient();
  const [search, setSearch]     = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage]         = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<StockTxn | null>(null);
  const [expanded, setExpanded]  = useState<Set<string>>(new Set());

  // Form state
  const [formType, setFormType]             = useState('STOCK_JOURNAL');
  const [formDate, setFormDate]             = useState(() => new Date().toISOString().slice(0, 10));
  const [formParty, setFormParty]           = useState('');
  const [formFromGodown, setFormFromGodown] = useState('');
  const [formToGodown, setFormToGodown]     = useState('');
  const [formNarration, setFormNarration]   = useState('');
  const [entries, setEntries]               = useState<EntryRow[]>([{ ...BLANK_ENTRY }]);

  // Master data — page_size must respect backend le= caps:
  // godowns le=100, ledgers le=100, units le=100, stock-items le=500
  const { data: godownsData }    = useQuery({ queryKey: ['godowns-all'],    queryFn: () => managementApi.godowns({ page_size: 100 }),    staleTime: 60_000 });
  const { data: stockItemsData } = useQuery({ queryKey: ['stock-items-all'], queryFn: () => managementApi.stockItems({ page_size: 500 }), staleTime: 60_000 });
  const { data: unitsData }      = useQuery({ queryKey: ['units-all'],      queryFn: () => managementApi.units({ page_size: 100 }),      staleTime: 60_000 });
  const { data: ledgersData }    = useQuery({ queryKey: ['ledgers-all'],    queryFn: () => managementApi.ledgers({ page_size: 100 }),    staleTime: 60_000 });

  const godownNames    = useMemo(() => (godownsData?.items    ?? [] as TallyGodown[]).map(g => g.name),  [godownsData]);
  const stockItemNames = useMemo(() => (stockItemsData?.items ?? [] as TallyStockItem[]).map(i => i.name), [stockItemsData]);
  const unitNames      = useMemo(() => (unitsData?.items      ?? [] as TallyUnit[]).map(u => u.name),    [unitsData]);
  const ledgerNames    = useMemo(() => (ledgersData?.items    ?? [] as TallyLedger[]).map(l => l.name),  [ledgersData]);

  const stockItemMap = useMemo(() => {
    const m = new Map<string, { unit: string; rate: number }>();
    for (const item of (stockItemsData?.items ?? [] as TallyStockItem[])) {
      m.set(item.name.toLowerCase(), { unit: item.unit || '', rate: item.rate || 0 });
    }
    return m;
  }, [stockItemsData]);

  // List
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-transactions', page, typeFilter, search],
    queryFn: () => api.list({ page, page_size: 20, transaction_type: typeFilter || undefined, search: search || undefined }),
  });

  // Create
  const createMut = useMutation({
    mutationFn: () => {
      const validEntries = entries
        .filter(e => e.stock_item_name.trim())
        .map(e => ({ stock_item_name: e.stock_item_name.trim(), quantity: parseFloat(e.quantity) || 0, unit: e.unit || '', rate: parseFloat(e.rate) || 0 }));
      return api.create({
        transaction_type: formType,
        transaction_date: formDate || undefined,
        party_name: formParty || undefined,
        from_godown: formFromGodown || undefined,
        to_godown: formToGodown || undefined,
        narration: formNarration || undefined,
        entries: validEntries,
      });
    },
    onSuccess: () => {
      toast({ title: 'Stock transaction created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['stock-transactions'] });
      qc.invalidateQueries({ queryKey: ['stock-items-tree'] });
      setShowCreate(false);
      resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  // Delete
  const deleteMut = useMutation({
    mutationFn: () => api.delete(deleteItem!.id),
    onSuccess: (data: { status?: string; message?: string }) => {
      toast({ title: data.status === 'pending' ? 'Cancellation sent to TallyPrime' : 'Deleted', description: data.message });
      qc.invalidateQueries({ queryKey: ['stock-transactions'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  function resetForm() {
    setFormType('STOCK_JOURNAL'); setFormDate(new Date().toISOString().slice(0, 10)); setFormParty('');
    setFormFromGodown(''); setFormToGodown(''); setFormNarration('');
    setEntries([{ ...BLANK_ENTRY }]);
  }

  function handleEntryField(idx: number, field: keyof EntryRow, value: string) {
    setEntries(prev => prev.map((e, i) => i === idx ? { ...e, [field]: value } : e));
  }

  function handleEntryItem(idx: number, name: string) {
    const lookup = stockItemMap.get(name.toLowerCase());
    setEntries(prev => prev.map((e, i) => i === idx ? {
      ...e, stock_item_name: name,
      unit: lookup?.unit || e.unit,
      rate: lookup && lookup.rate > 0 ? String(lookup.rate) : e.rate,
    } : e));
  }

  function toggleExpand(id: string) {
    setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  const totalPages   = data?.total_pages ?? 1;
  const showParty    = PARTY_TYPES.has(formType);
  const showToGodown = formType === 'STOCK_JOURNAL';
  const fromLabel    = formType === 'STOCK_JOURNAL' ? 'From Godown' : 'Godown';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ArrowLeftRight className="w-6 h-6 text-indigo-600" /> Stock Transactions
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Click any row to see item details</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Transaction
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input placeholder="Search…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9 w-56" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button onClick={() => { setTypeFilter(''); setPage(1); }}
            className={cn('px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
              !typeFilter ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>All</button>
          {TRANSACTION_TYPES.map(t => (
            <button key={t.value} onClick={() => { setTypeFilter(t.value); setPage(1); }}
              className={cn('px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                typeFilter === t.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="w-8" />
                  <th className="px-4 py-3 text-left">Number</th>
                  <th className="px-4 py-3 text-left w-36">Type</th>
                  <th className="px-4 py-3 text-left w-28">Date</th>
                  <th className="px-4 py-3 text-left">Route / Party</th>
                  <th className="px-4 py-3 text-left">Items</th>
                  <th className="px-4 py-3 text-center w-24">Sync</th>
                  <th className="px-4 py-3 text-right w-16">Actions</th>
                </tr>
              </thead>
              <tbody>
                {!data?.items?.length ? (
                  <tr><td colSpan={8} className="text-center py-14 text-slate-400">No stock transactions yet.</td></tr>
                ) : data.items.map((t: StockTxn) => {
                  const meta    = TYPE_META[t.transaction_type] ?? { color: 'bg-slate-100 text-slate-600', label: t.transaction_type_label };
                  const isOpen  = expanded.has(t.id);
                  const isParty = PARTY_TYPES.has(t.transaction_type);
                  const total   = totalAmount(t.entries);

                  // Route string shown in collapsed row
                  const routeCell = t.transaction_type === 'STOCK_JOURNAL'
                    ? <span className="flex items-center gap-1.5 text-xs text-slate-600">
                        <span className="font-medium">{t.from_godown || '—'}</span>
                        <MoveRight className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                        <span className="font-medium">{t.to_godown || '—'}</span>
                      </span>
                    : isParty
                      ? <span className="flex items-center gap-1.5 text-xs text-slate-600">
                          <User2 className="w-3 h-3 text-slate-400" />
                          <span className="font-medium">{t.party_name || '—'}</span>
                          {t.from_godown && <><MapPin className="w-3 h-3 text-slate-400 ml-1" /><span className="text-slate-400">{t.from_godown}</span></>}
                        </span>
                      : <span className="text-xs text-slate-500 flex items-center gap-1.5">
                          <MapPin className="w-3 h-3 text-slate-400" />
                          {t.from_godown || '—'}
                        </span>;

                  return (
                    <>
                      <tr
                        key={t.id}
                        onClick={() => toggleExpand(t.id)}
                        className={cn(
                          'border-b cursor-pointer transition-colors',
                          isOpen ? 'bg-indigo-50/60' : 'hover:bg-slate-50'
                        )}
                      >
                        {/* Expand chevron */}
                        <td className="pl-3 pr-1 py-3 text-slate-400">
                          {isOpen
                            ? <ChevronDown className="w-4 h-4 text-indigo-500" />
                            : <ChevronRight className="w-4 h-4" />}
                        </td>

                        {/* Number */}
                        <td className="px-4 py-3 font-mono text-xs text-slate-700 font-medium whitespace-nowrap">
                          {t.transaction_number}
                        </td>

                        {/* Type badge */}
                        <td className="px-4 py-3">
                          <span className={cn('px-2 py-0.5 rounded-full text-xs font-semibold', meta.color)}>
                            {meta.label}
                          </span>
                        </td>

                        {/* Date */}
                        <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                          {t.transaction_date ? formatDate(t.transaction_date) : '—'}
                        </td>

                        {/* Route / Party */}
                        <td className="px-4 py-3">{routeCell}</td>

                        {/* Items preview */}
                        <td className="px-4 py-3">
                          {t.entries?.length ? (
                            <div className="space-y-0.5">
                              <p className="text-xs text-slate-700 font-medium leading-snug">
                                {entryPreview(t.entries)}
                              </p>
                              {total > 0 && (
                                <p className="text-xs text-slate-400">{formatCurrency(total)}</p>
                              )}
                            </div>
                          ) : <span className="text-slate-300 text-xs">No items</span>}
                        </td>

                        {/* Sync */}
                        <td className="px-4 py-3 text-center" onClick={e => e.stopPropagation()}>
                          <SyncBadge status={t.tally_sync_status} />
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => setDeleteItem(t)}
                            className="p-1.5 rounded hover:bg-red-50 text-slate-300 hover:text-red-500 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>

                      {/* Expanded detail */}
                      {isOpen && (
                        <tr key={`${t.id}-detail`} className="border-b">
                          <td colSpan={8} className="p-0">
                            <TxnDetail txn={t} />
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-between items-center text-sm text-slate-500">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* ── Create Dialog ──────────────────────────────────────────────────── */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader><DialogTitle>New Stock Transaction</DialogTitle></DialogHeader>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Transaction Type *</Label>
                <select value={formType} onChange={e => setFormType(e.target.value)}
                  className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                  {TRANSACTION_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <Label>Date</Label>
                <Input type="date" value={formDate} onChange={e => setFormDate(e.target.value)} className="mt-1" />
                <p className="text-xs text-slate-400 mt-1">Must be within your TallyPrime active period (press F2 in TallyPrime to check).</p>
              </div>
            </div>

            {showParty && (
              <div>
                <Label>Party (Customer / Supplier)</Label>
                <Combobox
                  options={ledgerNames} value={formParty} onChange={setFormParty}
                  placeholder="Select party…" className="mt-1"
                />
              </div>
            )}

            <div className={cn('grid gap-3', showToGodown ? 'grid-cols-2' : 'grid-cols-1')}>
              <div>
                <Label>{fromLabel}</Label>
                <Combobox
                  options={godownNames} value={formFromGodown} onChange={setFormFromGodown}
                  placeholder="Select godown…" className="mt-1"
                />
              </div>
              {showToGodown && (
                <div>
                  <Label>To Godown</Label>
                  <Combobox
                    options={godownNames} value={formToGodown} onChange={setFormToGodown}
                    placeholder="Select destination…" className="mt-1"
                  />
                </div>
              )}
            </div>

            {/* Entries */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Stock Items</Label>
                <button onClick={() => setEntries(prev => [...prev, { ...BLANK_ENTRY }])}
                  className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                  <Plus className="w-3.5 h-3.5" /> Add Item
                </button>
              </div>
              <div className="border rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 border-b text-xs text-slate-500 uppercase tracking-wide">
                      <th className="px-3 py-2 text-left">Stock Item</th>
                      <th className="px-3 py-2 text-right w-24">Qty</th>
                      <th className="px-3 py-2 text-left w-36">Unit</th>
                      <th className="px-3 py-2 text-right w-28">Rate (₹)</th>
                      <th className="px-3 py-2 w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry, idx) => (
                      <tr key={idx} className="border-b last:border-0">
                        <td className="px-2 py-1.5">
                          <Combobox
                            options={stockItemNames} value={entry.stock_item_name}
                            onChange={v => handleEntryItem(idx, v)}
                            placeholder="Select item…"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <Input type="number" min="0" value={entry.quantity}
                            onChange={e => handleEntryField(idx, 'quantity', e.target.value)}
                            placeholder="0" className="text-right" />
                        </td>
                        <td className="px-2 py-1.5">
                          <Combobox
                            options={unitNames} value={entry.unit}
                            onChange={v => handleEntryField(idx, 'unit', v)}
                            placeholder="Unit…"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <Input type="number" min="0" value={entry.rate}
                            onChange={e => handleEntryField(idx, 'rate', e.target.value)}
                            placeholder="0" className="text-right" />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <button onClick={() => setEntries(prev => prev.length === 1 ? prev : prev.filter((_, i) => i !== idx))}
                            className="p-1 rounded hover:bg-red-50 text-slate-300 hover:text-red-500" disabled={entries.length === 1}>
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-400 mt-1.5">Unit and Rate auto-fill when you select a synced stock item.</p>
            </div>

            <div>
              <Label>Narration</Label>
              <Input value={formNarration} onChange={e => setFormNarration(e.target.value)} placeholder="Description / remarks" className="mt-1" />
            </div>
          </div>

          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Create &amp; Sync
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="text-red-600">Delete Transaction</DialogTitle></DialogHeader>
          <p className="text-sm">Delete <strong>{deleteItem?.transaction_number}</strong>?</p>
          {deleteItem?.tally_sync_status === 'synced' && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              This transaction is synced in TallyPrime. It will be cancelled there first, then removed here automatically.
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteItem(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
              {deleteMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
