import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShoppingCart, Plus, Search, Loader2, AlertCircle, Trash2 } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from '../../components/ui/use-toast';
import { ordersApi } from '../../api/endpoints';
import { formatCurrency, formatDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { Order } from '../../types';

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'bg-slate-100 text-slate-600',
  CONFIRMED: 'bg-blue-100 text-blue-700',
  FULFILLED: 'bg-green-100 text-green-700',
  CANCELLED: 'bg-red-100 text-red-700',
};

const ORDER_STATUSES = ['DRAFT', 'CONFIRMED', 'FULFILLED', 'CANCELLED'];

export default function OrdersPage() {
  const { type } = useParams<{ type?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const orderType = type === 'purchase' ? 'PURCHASE' : 'SALES';
  const title = orderType === 'SALES' ? 'Sales Orders' : 'Purchase Orders';

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<Order | null>(null);

  const [formParty, setFormParty] = useState('');
  const [formDate, setFormDate] = useState('');
  const [formDue, setFormDue] = useState('');
  const [formNarration, setFormNarration] = useState('');
  const [formAmount, setFormAmount] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['orders', orderType, page, search],
    queryFn: () => ordersApi.list({ order_type: orderType, page, page_size: 20, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => ordersApi.create({
      order_type: orderType,
      party_name: formParty.trim() || undefined,
      order_date: formDate || undefined,
      due_date: formDue || undefined,
      narration: formNarration.trim() || undefined,
      items: formAmount ? [{
        description: formNarration || `${orderType === 'SALES' ? 'Sales' : 'Purchase'} order`,
        quantity: 1,
        unit_price: parseFloat(formAmount),
      }] : [],
    }),
    onSuccess: () => {
      toast({ title: `${title.slice(0, -1)} created` });
      qc.invalidateQueries({ queryKey: ['orders', orderType] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => ordersApi.delete(deleteItem!.id),
    onSuccess: () => {
      toast({ title: 'Deleted' });
      qc.invalidateQueries({ queryKey: ['orders', orderType] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => ordersApi.update(id, { status: status as Order['status'] }),
    onSuccess: () => { toast({ title: 'Status updated' }); qc.invalidateQueries({ queryKey: ['orders', orderType] }); },
  });

  function resetForm() { setFormParty(''); setFormDate(''); setFormDue(''); setFormNarration(''); setFormAmount(''); }
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ShoppingCart className="w-6 h-6 text-indigo-600" /> {title}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {orderType === 'SALES' ? 'Customer sales orders' : 'Vendor purchase orders'}
            {' '}— stored locally (TallyPrime order sync available via TDL)
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate(orderType === 'SALES' ? '/orders/purchase' : '/orders/sales')}
            className="px-3 py-1.5 rounded-full text-xs border border-slate-200 text-slate-600 hover:bg-slate-50"
          >
            Switch to {orderType === 'SALES' ? 'Purchase' : 'Sales'} Orders
          </button>
          <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
            <Plus className="w-4 h-4" /> New {orderType === 'SALES' ? 'Sales' : 'Purchase'} Order
          </Button>
        </div>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search orders…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
      </div>

      <Card><CardContent className="p-0">
        {isLoading ? <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        : isError ? <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
        : <table className="w-full text-sm">
            <thead><tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <th className="px-4 py-3 text-left">Order #</th>
              <th className="px-4 py-3 text-left">Party</th>
              <th className="px-4 py-3 text-left">Date</th>
              <th className="px-4 py-3 text-right">Amount</th>
              <th className="px-4 py-3 text-center">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr></thead>
            <tbody>
              {data?.items.length === 0 ? <tr><td colSpan={6} className="text-center py-10 text-slate-400">No {title.toLowerCase()} found. Create one.</td></tr>
              : data?.items.map(o => (
                <tr key={o.id} className="border-b hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{o.order_number}</td>
                  <td className="px-4 py-3 text-slate-700">{o.party_name || '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{o.order_date ? formatDate(o.order_date) : '—'}</td>
                  <td className="px-4 py-3 text-right font-medium">{formatCurrency(o.total_amount)}</td>
                  <td className="px-4 py-3 text-center">
                    <select
                      value={o.status}
                      onChange={e => updateStatus.mutate({ id: o.id, status: e.target.value })}
                      className={cn('text-xs font-medium px-2 py-0.5 rounded-full border-0 cursor-pointer', STATUS_COLORS[o.status] || 'bg-slate-100 text-slate-600')}
                    >
                      {ORDER_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => setDeleteItem(o)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>}
      </CardContent></Card>

      {totalPages > 1 && <div className="flex justify-between text-sm text-slate-500"><span>Page {page} of {totalPages}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Prev</Button><Button variant="outline" size="sm" disabled={page>=totalPages} onClick={()=>setPage(p=>p+1)}>Next</Button></div></div>}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New {orderType === 'SALES' ? 'Sales' : 'Purchase'} Order</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>{orderType === 'SALES' ? 'Customer' : 'Vendor'} Name</Label><Input value={formParty} onChange={e=>setFormParty(e.target.value)} placeholder={orderType === 'SALES' ? 'Customer name' : 'Vendor name'}/></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Order Date</Label><Input type="date" value={formDate} onChange={e=>setFormDate(e.target.value)}/></div>
              <div><Label>Due Date</Label><Input type="date" value={formDue} onChange={e=>setFormDue(e.target.value)}/></div>
            </div>
            <div><Label>Amount</Label><Input type="number" value={formAmount} onChange={e=>setFormAmount(e.target.value)} placeholder="0"/></div>
            <div><Label>Narration</Label><Input value={formNarration} onChange={e=>setFormNarration(e.target.value)} placeholder="Description or notes"/></div>
            <p className="text-xs text-slate-400">Orders are stored locally in FinPilot. TallyPrime order sync requires TDL configuration.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={()=>setShowCreate(false)}>Cancel</Button>
            <Button onClick={()=>createMut.mutate()} disabled={createMut.isPending}>{createMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Create Order</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={()=>setDeleteItem(null)}>
        <DialogContent className="max-w-sm"><DialogHeader><DialogTitle className="text-red-600">Delete Order</DialogTitle></DialogHeader>
          <p className="text-sm">Delete order <strong>{deleteItem?.order_number}</strong>?</p>
          <DialogFooter><Button variant="outline" onClick={()=>setDeleteItem(null)}>Cancel</Button><Button variant="destructive" onClick={()=>deleteMut.mutate()} disabled={deleteMut.isPending}>{deleteMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Delete</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
