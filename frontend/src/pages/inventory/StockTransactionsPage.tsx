import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftRight, Plus, Search, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import { formatDate } from '../../utils/format';
import apiClient from '../../api/client';
import { SyncBadge } from '../../components/ui/SyncBadge';

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

const api = {
  list: (params: Record<string, unknown>) => apiClient.get('/api/inventory/stock-transactions', { params }).then(r => r.data),
  create: (d: object) => apiClient.post('/api/inventory/stock-transactions', d).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/api/inventory/stock-transactions/${id}`).then(r => r.data),
};

export default function StockTransactionsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<StockTxn | null>(null);

  const [formType, setFormType] = useState('STOCK_JOURNAL');
  const [formDate, setFormDate] = useState('');
  const [formParty, setFormParty] = useState('');
  const [formFromGodown, setFormFromGodown] = useState('');
  const [formToGodown, setFormToGodown] = useState('');
  const [formNarration, setFormNarration] = useState('');
  const [formItemName, setFormItemName] = useState('');
  const [formQty, setFormQty] = useState('');
  const [formUnit, setFormUnit] = useState('Nos');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-transactions', page, typeFilter, search],
    queryFn: () => api.list({ page, page_size: 20, transaction_type: typeFilter || undefined, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => api.create({
      transaction_type: formType,
      transaction_date: formDate || undefined,
      party_name: formParty || undefined,
      from_godown: formFromGodown || undefined,
      to_godown: formToGodown || undefined,
      narration: formNarration || undefined,
      entries: formItemName ? [{ stock_item_name: formItemName.trim(), quantity: parseFloat(formQty) || 0, unit: formUnit || 'Nos' }] : [],
    }),
    onSuccess: () => { toast({ title: 'Stock transaction created' }); qc.invalidateQueries({ queryKey: ['stock-transactions'] }); setShowCreate(false); resetForm(); },
    onError: (e: { response?: { data?: { detail?: string } } }) => toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api.delete(deleteItem!.id),
    onSuccess: () => { toast({ title: 'Deleted' }); qc.invalidateQueries({ queryKey: ['stock-transactions'] }); setDeleteItem(null); },
    onError: (e: { response?: { data?: { detail?: string } } }) => toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  function resetForm() { setFormType('STOCK_JOURNAL'); setFormDate(''); setFormParty(''); setFormFromGodown(''); setFormToGodown(''); setFormNarration(''); setFormItemName(''); setFormQty(''); setFormUnit('Nos'); }
  const totalPages = data?.total_pages ?? 1;

  const showParty = ['DELIVERY_NOTE', 'RECEIPT_NOTE', 'REJECTION_IN', 'REJECTION_OUT'].includes(formType);
  const showGodowns = ['STOCK_JOURNAL', 'PHYSICAL_STOCK'].includes(formType);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><ArrowLeftRight className="w-6 h-6 text-indigo-600" /> Stock Transactions</h1>
          <p className="text-sm text-slate-500 mt-0.5">Stock journals, physical stock, delivery & receipt notes</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2"><Plus className="w-4 h-4" /> New Transaction</Button>
      </div>

      {/* Type filter tabs */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => { setTypeFilter(''); setPage(1); }} className={cn('px-3 py-1.5 rounded-full text-xs font-medium', !typeFilter ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>All</button>
        {TRANSACTION_TYPES.map(t => (
          <button key={t.value} onClick={() => { setTypeFilter(t.value); setPage(1); }} className={cn('px-3 py-1.5 rounded-full text-xs font-medium', typeFilter === t.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}>{t.label}</button>
        ))}
      </div>

      <div className="relative max-w-sm"><Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" /><Input placeholder="Search transactions…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" /></div>

      <Card><CardContent className="p-0">
        {isLoading ? <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        : isError ? <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
        : <table className="w-full text-sm">
            <thead><tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <th className="px-4 py-3 text-left">Number</th><th className="px-4 py-3 text-left">Type</th><th className="px-4 py-3 text-left">Date</th>
              <th className="px-4 py-3 text-left">Party / Narration</th><th className="px-4 py-3 text-center">Items</th><th className="px-4 py-3 text-left">Sync</th><th className="px-4 py-3 text-right">Actions</th>
            </tr></thead>
            <tbody>
              {data?.items?.length === 0 ? <tr><td colSpan={7} className="text-center py-10 text-slate-400">No stock transactions yet.</td></tr>
              : data?.items?.map((t: StockTxn) => (
                <tr key={t.id} className="border-b hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{t.transaction_number}</td>
                  <td className="px-4 py-3"><span className={cn('px-2 py-0.5 rounded text-xs font-medium', TYPE_COLORS[t.transaction_type] || 'bg-slate-100 text-slate-600')}>{t.transaction_type_label}</span></td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{t.transaction_date ? formatDate(t.transaction_date) : '—'}</td>
                  <td className="px-4 py-3 text-slate-700 truncate max-w-xs">{t.party_name || t.narration || '—'}</td>
                  <td className="px-4 py-3 text-center text-slate-500">{t.entries?.length ?? 0}</td>
                  <td className="px-4 py-3"><SyncBadge status={t.tally_sync_status} /></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => setDeleteItem(t)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>}
      </CardContent></Card>

      {totalPages > 1 && <div className="flex justify-between text-sm text-slate-500"><span>Page {page} of {totalPages}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Prev</Button><Button variant="outline" size="sm" disabled={page>=totalPages} onClick={()=>setPage(p=>p+1)}>Next</Button></div></div>}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}><DialogContent className="max-w-lg"><DialogHeader><DialogTitle>New Stock Transaction</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Transaction Type *</Label>
            <select value={formType} onChange={e=>setFormType(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm">
              {TRANSACTION_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div><Label>Date</Label><Input type="date" value={formDate} onChange={e=>setFormDate(e.target.value)}/></div>
          {showParty && <div><Label>Party</Label><Input value={formParty} onChange={e=>setFormParty(e.target.value)} placeholder="Customer or Vendor name"/></div>}
          {showGodowns && <div className="grid grid-cols-2 gap-3">
            <div><Label>From Godown</Label><Input value={formFromGodown} onChange={e=>setFormFromGodown(e.target.value)} placeholder="Source"/></div>
            <div><Label>To Godown</Label><Input value={formToGodown} onChange={e=>setFormToGodown(e.target.value)} placeholder="Destination"/></div>
          </div>}
          <div className="border-t pt-3">
            <Label>Stock Item Entry</Label>
            <div className="grid grid-cols-3 gap-2 mt-1">
              <div className="col-span-2"><Input value={formItemName} onChange={e=>setFormItemName(e.target.value)} placeholder="Stock item name"/></div>
              <div><Input type="number" value={formQty} onChange={e=>setFormQty(e.target.value)} placeholder="Qty"/></div>
            </div>
            <div className="mt-2"><Input value={formUnit} onChange={e=>setFormUnit(e.target.value)} placeholder="Unit (e.g. Nos, Kg)"/></div>
          </div>
          <div><Label>Narration</Label><Input value={formNarration} onChange={e=>setFormNarration(e.target.value)} placeholder="Description"/></div>
          <p className="text-xs text-slate-400">Transaction will be synced to TallyPrime automatically if a connector is online.</p>
        </div>
        <DialogFooter><Button variant="outline" onClick={()=>setShowCreate(false)}>Cancel</Button>
          <Button onClick={()=>createMut.mutate()} disabled={createMut.isPending}>{createMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Create</Button>
        </DialogFooter>
      </DialogContent></Dialog>

      <Dialog open={!!deleteItem} onOpenChange={()=>setDeleteItem(null)}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle className="text-red-600">Delete Transaction</DialogTitle></DialogHeader>
        <p className="text-sm">Delete <strong>{deleteItem?.transaction_number}</strong>?</p>
        <DialogFooter><Button variant="outline" onClick={()=>setDeleteItem(null)}>Cancel</Button><Button variant="destructive" onClick={()=>deleteMut.mutate()} disabled={deleteMut.isPending}>{deleteMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Delete</Button></DialogFooter>
      </DialogContent></Dialog>
    </div>
  );
}
