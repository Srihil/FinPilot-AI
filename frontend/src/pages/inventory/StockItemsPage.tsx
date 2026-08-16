import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Package, Plus, Search, Loader2, AlertCircle, Pencil, Trash2 } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import { formatCurrency } from '../../utils/format';
import type { TallyStockItem, TallyUnit } from '../../types';

export default function StockItemsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyStockItem | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyStockItem | null>(null);

  const [formName, setFormName] = useState('');
  const [formGroup, setFormGroup] = useState('');
  const [formUnit, setFormUnit] = useState('Nos');
  const [formRate, setFormRate] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-items', page, search],
    queryFn: () => managementApi.stockItems({ page, page_size: 20, search: search || undefined }),
  });

  const { data: unitsData } = useQuery({
    queryKey: ['units-all'],
    queryFn: () => managementApi.units({ page_size: 100 }),
    staleTime: 60_000,
  });

  const createMut = useMutation({
    mutationFn: () => managementApi.createStockItem({
      name: formName.trim(),
      stock_group: formGroup || undefined,
      unit: formUnit || 'Nos',
      rate: formRate ? parseFloat(formRate) : 0,
    }),
    onSuccess: () => {
      toast({ title: 'Stock item created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['stock-items'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateStockItem(editItem!.id, {
      name: formName || undefined,
      stock_group: formGroup || undefined,
      unit: formUnit || undefined,
      rate: formRate ? parseFloat(formRate) : undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Updated' });
      qc.invalidateQueries({ queryKey: ['stock-items'] });
      setEditItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteStockItem(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['stock-items'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  function resetForm() { setFormName(''); setFormGroup(''); setFormUnit(''); setFormRate(''); }
  function openEdit(item: TallyStockItem) {
    setFormName(item.name); setFormGroup(item.stock_group || '');
    setFormUnit(item.unit || 'Nos'); setFormRate(item.rate ? String(item.rate) : '');
    setEditItem(item);
  }

  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Package className="w-6 h-6 text-indigo-600" /> Stock Items
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Stock items synced with TallyPrime</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Stock Item
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search items…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
      </div>

      <Card><CardContent className="p-0">
        {isLoading ? <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        : isError ? <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
        : <table className="w-full text-sm">
            <thead><tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Group</th>
              <th className="px-4 py-3 text-left">Unit</th>
              <th className="px-4 py-3 text-right">Rate</th>
              <th className="px-4 py-3 text-center">Sync</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr></thead>
            <tbody>
              {data?.items.length === 0
                ? <tr><td colSpan={6} className="text-center py-10 text-slate-400">No stock items found. Create one or sync from TallyPrime.</td></tr>
                : data?.items.map(item => (
                  <tr key={item.id} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium">{item.name}</td>
                    <td className="px-4 py-3 text-slate-500">{item.stock_group || '—'}</td>
                    <td className="px-4 py-3 text-slate-500">{item.unit || '—'}</td>
                    <td className="px-4 py-3 text-right">{item.rate ? formatCurrency(item.rate) : '—'}</td>
                    <td className="px-4 py-3 text-center"><SyncBadge status={item.tally_sync_status} source={item.source} /></td>
                    <td className="px-4 py-3 text-right"><div className="flex items-center justify-end gap-2">
                      <button onClick={() => openEdit(item)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500"><Pencil className="w-3.5 h-3.5" /></button>
                      <button onClick={() => setDeleteItem(item)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div></td>
                  </tr>
                ))}
            </tbody>
          </table>}
      </CardContent></Card>

      {totalPages > 1 && <div className="flex justify-between text-sm text-slate-500"><span>Page {page} of {totalPages}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Prev</Button><Button variant="outline" size="sm" disabled={page>=totalPages} onClick={()=>setPage(p=>p+1)}>Next</Button></div></div>}

      <Dialog open={showCreate} onOpenChange={setShowCreate}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>New Stock Item</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Name *</Label><Input value={formName} onChange={e=>setFormName(e.target.value)} placeholder="e.g. Laptop" /></div>
          <div><Label>Stock Group</Label><Input value={formGroup} onChange={e=>setFormGroup(e.target.value)} placeholder="e.g. Electronics (leave empty for root)" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Unit</Label>
              <select value={formUnit} onChange={e=>setFormUnit(e.target.value)} className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                <option value="">— No unit —</option>
                {unitsData?.items.map((u: TallyUnit) => (
                  <option key={u.id} value={u.name}>{u.name} {u.symbol ? `(${u.symbol})` : ''}</option>
                ))}
              </select>
              {(!unitsData?.items.length) && <p className="text-xs text-amber-600 mt-1">No units yet — create units first.</p>}
            </div>
            <div><Label>Rate (₹)</Label><Input type="number" value={formRate} onChange={e=>setFormRate(e.target.value)} placeholder="0" /></div>
          </div>
        </div>
        <DialogFooter><Button variant="outline" onClick={()=>setShowCreate(false)}>Cancel</Button><Button onClick={()=>createMut.mutate()} disabled={!formName.trim()||createMut.isPending}>{createMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Create</Button></DialogFooter>
      </DialogContent></Dialog>

      <Dialog open={!!editItem} onOpenChange={()=>setEditItem(null)}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>Edit Stock Item</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input value={formName} onChange={e=>setFormName(e.target.value)}/></div>
          <div><Label>Stock Group</Label><Input value={formGroup} onChange={e=>setFormGroup(e.target.value)}/></div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Unit</Label>
              <select value={formUnit} onChange={e=>setFormUnit(e.target.value)} className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                <option value="">— No unit —</option>
                {unitsData?.items.map((u: TallyUnit) => (
                  <option key={u.id} value={u.name}>{u.name} {u.symbol ? `(${u.symbol})` : ''}</option>
                ))}
              </select>
            </div>
            <div><Label>Rate (₹)</Label><Input type="number" value={formRate} onChange={e=>setFormRate(e.target.value)}/></div>
          </div>
        </div>
        <DialogFooter><Button variant="outline" onClick={()=>setEditItem(null)}>Cancel</Button><Button onClick={()=>updateMut.mutate()} disabled={updateMut.isPending}>{updateMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Save</Button></DialogFooter>
      </DialogContent></Dialog>

      <Dialog open={!!deleteItem} onOpenChange={()=>setDeleteItem(null)}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle className="text-red-600">Delete Stock Item</DialogTitle></DialogHeader>
        <p className="text-sm">Delete <strong>{deleteItem?.name}</strong>? This will also remove it from TallyPrime.</p>
        <DialogFooter><Button variant="outline" onClick={()=>setDeleteItem(null)}>Cancel</Button><Button variant="destructive" onClick={()=>deleteMut.mutate()} disabled={deleteMut.isPending}>{deleteMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Delete</Button></DialogFooter>
      </DialogContent></Dialog>
    </div>
  );
}
