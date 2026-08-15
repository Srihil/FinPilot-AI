import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Package, Plus, Search, Loader2, AlertCircle, Pencil, Trash2 } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from '../../components/ui/use-toast';
import { productsApi } from '../../api/endpoints';
import { formatCurrency } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { Product } from '../../types';

export default function StockItemsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<Product | null>(null);
  const [deleteItem, setDeleteItem] = useState<Product | null>(null);

  const [formName, setFormName] = useState('');
  const [formUnit, setFormUnit] = useState('Nos');
  const [formSell, setFormSell] = useState('');
  const [formCost, setFormCost] = useState('');
  const [formQty, setFormQty] = useState('');
  const [formSKU, setFormSKU] = useState('');
  const [formCategory, setFormCategory] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-items', page, search],
    queryFn: () => productsApi.list({ page, page_size: PAGE_SIZE, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => productsApi.create({
      name: formName.trim(),
      unit: formUnit || 'Nos',
      selling_price: formSell ? parseFloat(formSell) : 0,
      purchase_price: formCost ? parseFloat(formCost) : 0,
      stock_quantity: formQty ? parseFloat(formQty) : 0,
      sku: formSKU || undefined,
      category: formCategory || undefined,
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
    mutationFn: () => productsApi.update(editItem!.id, {
      name: formName || undefined,
      unit: formUnit || undefined,
      selling_price: formSell ? parseFloat(formSell) : undefined,
      purchase_price: formCost ? parseFloat(formCost) : undefined,
      stock_quantity: formQty ? parseFloat(formQty) : undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Updated' });
      qc.invalidateQueries({ queryKey: ['stock-items'] });
      setEditItem(null); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => productsApi.delete(deleteItem!.id),
    onSuccess: () => {
      toast({ title: 'Deleted' });
      qc.invalidateQueries({ queryKey: ['stock-items'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  function resetForm() {
    setFormName(''); setFormUnit('Nos'); setFormSell(''); setFormCost('');
    setFormQty(''); setFormSKU(''); setFormCategory('');
  }

  function openEdit(p: Product) {
    setFormName(p.name);
    setFormUnit(p.unit || 'Nos');
    setFormSell(p.selling_price ? String(p.selling_price) : '');
    setFormCost(p.purchase_price ? String(p.purchase_price) : '');
    setFormQty(p.stock_quantity ? String(p.stock_quantity) : '');
    setFormSKU(p.sku || '');
    setFormCategory(p.category || '');
    setEditItem(p);
  }

  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Package className="w-6 h-6 text-indigo-600" /> Stock Items
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Products and stock items synced with TallyPrime</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Stock Item
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search items…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load items.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">SKU</th>
                  <th className="px-4 py-3 text-left">Unit</th>
                  <th className="px-4 py-3 text-right">Stock</th>
                  <th className="px-4 py-3 text-right">Sell Price</th>
                  <th className="px-4 py-3 text-right">Cost</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-10 text-slate-400">No stock items found. Create one or sync from TallyPrime.</td></tr>
                ) : data?.items.map(p => {
                  const isLow = Number(p.stock_quantity) <= Number(p.reorder_threshold);
                  return (
                    <tr key={p.id} className="border-b hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-800">{p.name}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs font-mono">{p.sku || '—'}</td>
                      <td className="px-4 py-3 text-slate-500">{p.unit || '—'}</td>
                      <td className={cn('px-4 py-3 text-right font-medium', isLow ? 'text-red-600' : 'text-slate-800')}>
                        {Number(p.stock_quantity).toFixed(0)}
                        {isLow && <span className="ml-1 text-xs text-red-500">Low</span>}
                      </td>
                      <td className="px-4 py-3 text-right">{formatCurrency(Number(p.selling_price))}</td>
                      <td className="px-4 py-3 text-right">{formatCurrency(Number(p.purchase_price))}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={cn(
                          'px-2 py-0.5 rounded-full text-xs font-medium',
                          p.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500',
                        )}>{p.is_active ? 'Active' : 'Inactive'}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button onClick={() => openEdit(p)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500"><Pencil className="w-3.5 h-3.5" /></button>
                          <button onClick={() => setDeleteItem(p)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>Page {page} of {totalPages} ({data?.total ?? 0} total)</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Stock Item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name *</Label><Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. Laptop" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Unit</Label><Input value={formUnit} onChange={e => setFormUnit(e.target.value)} placeholder="Nos" /></div>
              <div><Label>SKU</Label><Input value={formSKU} onChange={e => setFormSKU(e.target.value)} placeholder="LAP-001" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Selling Price</Label><Input type="number" value={formSell} onChange={e => setFormSell(e.target.value)} placeholder="0" /></div>
              <div><Label>Cost Price</Label><Input type="number" value={formCost} onChange={e => setFormCost(e.target.value)} placeholder="0" /></div>
            </div>
            <div><Label>Opening Stock</Label><Input type="number" value={formQty} onChange={e => setFormQty(e.target.value)} placeholder="0" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />} Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Stock Item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name</Label><Input value={formName} onChange={e => setFormName(e.target.value)} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Unit</Label><Input value={formUnit} onChange={e => setFormUnit(e.target.value)} /></div>
              <div><Label>Stock Qty</Label><Input type="number" value={formQty} onChange={e => setFormQty(e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Sell Price</Label><Input type="number" value={formSell} onChange={e => setFormSell(e.target.value)} /></div>
              <div><Label>Cost Price</Label><Input type="number" value={formCost} onChange={e => setFormCost(e.target.value)} /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />} Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="text-red-600">Delete Stock Item</DialogTitle></DialogHeader>
          <p className="text-sm">Delete <strong>{deleteItem?.name}</strong>? This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteItem(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
              {deleteMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />} Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
