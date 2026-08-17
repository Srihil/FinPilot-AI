import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftRight, Plus, Search, Loader2, AlertCircle, Trash2, X } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Combobox } from '../../components/ui/Combobox';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import { formatDate } from '../../utils/format';
import apiClient from '../../api/client';
import { managementApi } from '../../api/endpoints';
import { SyncBadge } from '../../components/ui/SyncBadge';
import type { TallyGodown, TallyStockItem, TallyUnit, TallyLedger } from '../../types';

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
  entries: Array<{ stock_item_name: string; quantity: number; unit?: string; rate?: number }>;
  tally_sync_status: string;
}

interface EntryRow {
  stock_item_name: string;
  quantity: string;
  unit: string;
  rate: string;
}

const TYPE_COLORS: Record<string, string> = {
  STOCK_JOURNAL:   'bg-indigo-100 text-indigo-700',
  PHYSICAL_STOCK:  'bg-blue-100 text-blue-700',
  DELIVERY_NOTE:   'bg-green-100 text-green-700',
  RECEIPT_NOTE:    'bg-teal-100 text-teal-700',
  REJECTION_IN:    'bg-orange-100 text-orange-700',
  REJECTION_OUT:   'bg-red-100 text-red-700',
};

const TRANSACTION_TYPES = [
  { value: 'STOCK_JOURNAL', label: 'Stock Journal' },
  { value: 'PHYSICAL_STOCK', label: 'Physical Stock' },
  { value: 'DELIVERY_NOTE', label: 'Delivery Note' },
  { value: 'RECEIPT_NOTE', label: 'Receipt Note' },
  { value: 'REJECTION_IN', label: 'Rejections In' },
  { value: 'REJECTION_OUT', label: 'Rejections Out' },
];

const PARTY_TYPES = new Set(['DELIVERY_NOTE', 'RECEIPT_NOTE', 'REJECTION_IN', 'REJECTION_OUT']);

const api = {
  list: (params: Record<string, unknown>) => apiClient.get('/api/inventory/stock-transactions', { params }).then(r => r.data),
  create: (d: object) => apiClient.post('/api/inventory/stock-transactions', d).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/api/inventory/stock-transactions/${id}`).then(r => r.data),
};

const BLANK_ENTRY: EntryRow = { stock_item_name: '', quantity: '', unit: '', rate: '' };

export default function StockTransactionsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<StockTxn | null>(null);

  // Form state
  const [formType, setFormType] = useState('STOCK_JOURNAL');
  const [formDate, setFormDate] = useState('');
  const [formParty, setFormParty] = useState('');
  const [formFromGodown, setFormFromGodown] = useState('');
  const [formToGodown, setFormToGodown] = useState('');
  const [formNarration, setFormNarration] = useState('');
  const [entries, setEntries] = useState<EntryRow[]>([{ ...BLANK_ENTRY }]);

  // Master data for dropdowns
  const { data: godownsData } = useQuery({
    queryKey: ['godowns-all'],
    queryFn: () => managementApi.godowns({ page_size: 200 }),
    staleTime: 60_000,
  });
  const { data: stockItemsData } = useQuery({
    queryKey: ['stock-items-all'],
    queryFn: () => managementApi.stockItems({ page_size: 500 }),
    staleTime: 60_000,
  });
  const { data: unitsData } = useQuery({
    queryKey: ['units-all'],
    queryFn: () => managementApi.units({ page_size: 100 }),
    staleTime: 60_000,
  });
  const { data: ledgersData } = useQuery({
    queryKey: ['ledgers-all'],
    queryFn: () => managementApi.ledgers({ page_size: 500 }),
    staleTime: 60_000,
  });

  const godownNames = useMemo(() =>
    (godownsData?.items ?? [] as TallyGodown[]).map(g => g.name), [godownsData]);
  const stockItemNames = useMemo(() =>
    (stockItemsData?.items ?? [] as TallyStockItem[]).map(i => i.name), [stockItemsData]);
  const unitNames = useMemo(() =>
    (unitsData?.items ?? [] as TallyUnit[]).map(u => u.name), [unitsData]);
  const ledgerNames = useMemo(() =>
    (ledgersData?.items ?? [] as TallyLedger[]).map(l => l.name), [ledgersData]);

  // Quick lookup for auto-fill
  const stockItemMap = useMemo(() => {
    const m = new Map<string, { unit: string; rate: number }>();
    for (const item of (stockItemsData?.items ?? [] as TallyStockItem[])) {
      m.set(item.name.toLowerCase(), { unit: item.unit || '', rate: item.rate || 0 });
    }
    return m;
  }, [stockItemsData]);

  // List query
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-transactions', page, typeFilter, search],
    queryFn: () => api.list({ page, page_size: 20, transaction_type: typeFilter || undefined, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => {
      const validEntries = entries
        .filter(e => e.stock_item_name.trim())
        .map(e => ({
          stock_item_name: e.stock_item_name.trim(),
          quantity: parseFloat(e.quantity) || 0,
          unit: e.unit || '',
          rate: parseFloat(e.rate) || 0,
        }));
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

  const deleteMut = useMutation({
    mutationFn: () => api.delete(deleteItem!.id),
    onSuccess: (data: { deleted?: boolean; status?: string; message?: string }) => {
      if (data.status === 'pending') {
        toast({ title: 'Cancellation sent to TallyPrime', description: data.message });
      } else {
        toast({ title: 'Deleted successfully' });
      }
      qc.invalidateQueries({ queryKey: ['stock-transactions'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  function resetForm() {
    setFormType('STOCK_JOURNAL');
    setFormDate('');
    setFormParty('');
    setFormFromGodown('');
    setFormToGodown('');
    setFormNarration('');
    setEntries([{ ...BLANK_ENTRY }]);
  }

  function handleEntryField(idx: number, field: keyof EntryRow, value: string) {
    setEntries(prev => prev.map((e, i) => i === idx ? { ...e, [field]: value } : e));
  }

  function handleEntryItem(idx: number, name: string) {
    const lookup = stockItemMap.get(name.toLowerCase());
    setEntries(prev => prev.map((e, i) => i === idx ? {
      ...e,
      stock_item_name: name,
      unit: lookup?.unit || e.unit,
      rate: lookup && lookup.rate > 0 ? String(lookup.rate) : e.rate,
    } : e));
  }

  function addEntry() {
    setEntries(prev => [...prev, { ...BLANK_ENTRY }]);
  }

  function removeEntry(idx: number) {
    setEntries(prev => prev.length === 1 ? prev : prev.filter((_, i) => i !== idx));
  }

  const totalPages = data?.total_pages ?? 1;
  const showParty = PARTY_TYPES.has(formType);
  const showToGodown = formType === 'STOCK_JOURNAL';
  const fromGodownLabel = formType === 'STOCK_JOURNAL' ? 'From Godown' : 'Godown';

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ArrowLeftRight className="w-6 h-6 text-indigo-600" /> Stock Transactions
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Stock journals, physical stock, delivery & receipt notes</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Transaction
        </Button>
      </div>

      {/* Type filter tabs */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => { setTypeFilter(''); setPage(1); }}
          className={cn('px-3 py-1.5 rounded-full text-xs font-medium', !typeFilter ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>All</button>
        {TRANSACTION_TYPES.map(t => (
          <button key={t.value} onClick={() => { setTypeFilter(t.value); setPage(1); }}
            className={cn('px-3 py-1.5 rounded-full text-xs font-medium', typeFilter === t.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search transactions…" value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Number</th>
                  <th className="px-4 py-3 text-left">Type</th>
                  <th className="px-4 py-3 text-left">Date</th>
                  <th className="px-4 py-3 text-left">Party / Narration</th>
                  <th className="px-4 py-3 text-center">Items</th>
                  <th className="px-4 py-3 text-left">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items?.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-10 text-slate-400">No stock transactions yet.</td></tr>
                ) : data?.items?.map((t: StockTxn) => (
                  <tr key={t.id} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{t.transaction_number}</td>
                    <td className="px-4 py-3">
                      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', TYPE_COLORS[t.transaction_type] || 'bg-slate-100 text-slate-600')}>
                        {t.transaction_type_label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{t.transaction_date ? formatDate(t.transaction_date) : '—'}</td>
                    <td className="px-4 py-3 text-slate-700 truncate max-w-xs">{t.party_name || t.narration || '—'}</td>
                    <td className="px-4 py-3 text-center text-slate-500">{t.entries?.length ?? 0}</td>
                    <td className="px-4 py-3"><SyncBadge status={t.tally_sync_status} /></td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => setDeleteItem(t)}
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex justify-between text-sm text-slate-500">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* ── Create Dialog ─────────────────────────────────────────────────── */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Stock Transaction</DialogTitle></DialogHeader>
          <div className="space-y-4">

            {/* Type + Date */}
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
              </div>
            </div>

            {/* Party (for delivery/receipt/rejection) */}
            {showParty && (
              <div>
                <Label>Party (Customer / Supplier)</Label>
                <Combobox
                  options={ledgerNames}
                  value={formParty}
                  onChange={setFormParty}
                  placeholder="Search ledgers…"
                  className="mt-1"
                />
              </div>
            )}

            {/* Godowns */}
            <div className={cn('grid gap-3', showToGodown ? 'grid-cols-2' : 'grid-cols-1')}>
              <div>
                <Label>{fromGodownLabel}</Label>
                <Combobox
                  options={godownNames}
                  value={formFromGodown}
                  onChange={setFormFromGodown}
                  placeholder="Select godown…"
                  className="mt-1"
                />
              </div>
              {showToGodown && (
                <div>
                  <Label>To Godown</Label>
                  <Combobox
                    options={godownNames}
                    value={formToGodown}
                    onChange={setFormToGodown}
                    placeholder="Select destination…"
                    className="mt-1"
                  />
                </div>
              )}
            </div>

            {/* Entries table */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <Label>Stock Items</Label>
                <button onClick={addEntry}
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
                      <th className="px-3 py-2 text-left w-28">Unit</th>
                      <th className="px-3 py-2 text-right w-28">Rate (₹)</th>
                      <th className="px-3 py-2 w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry, idx) => (
                      <tr key={idx} className="border-b last:border-0">
                        <td className="px-2 py-1.5">
                          <Combobox
                            options={stockItemNames}
                            value={entry.stock_item_name}
                            onChange={v => handleEntryItem(idx, v)}
                            placeholder="Search stock items…"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <Input
                            type="number"
                            min="0"
                            value={entry.quantity}
                            onChange={e => handleEntryField(idx, 'quantity', e.target.value)}
                            placeholder="0"
                            className="text-right"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <Combobox
                            options={unitNames}
                            value={entry.unit}
                            onChange={v => handleEntryField(idx, 'unit', v)}
                            placeholder="Unit…"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <Input
                            type="number"
                            min="0"
                            value={entry.rate}
                            onChange={e => handleEntryField(idx, 'rate', e.target.value)}
                            placeholder="0"
                            className="text-right"
                          />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <button onClick={() => removeEntry(idx)}
                            className="p-1 rounded hover:bg-red-50 text-slate-300 hover:text-red-500"
                            disabled={entries.length === 1}>
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-slate-400 mt-1.5">
                Unit and Rate are auto-filled from synced stock item data. You can edit them if needed.
              </p>
            </div>

            {/* Narration */}
            <div>
              <Label>Narration</Label>
              <Input value={formNarration} onChange={e => setFormNarration(e.target.value)}
                placeholder="Description / remarks" className="mt-1" />
            </div>

            <p className="text-xs text-slate-400">
              Transaction will be synced to TallyPrime automatically if a connector is online.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Create
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
