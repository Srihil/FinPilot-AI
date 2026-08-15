import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Search, Loader2, AlertCircle, Trash2, Filter, Eraser } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import { formatCurrency, formatDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { VoucherItem } from '../../types';

const VOUCHER_TYPES = [
  { label: 'All Vouchers', value: '' },
  { label: 'Sales', value: 'SALES' },
  { label: 'Purchase', value: 'PURCHASE' },
  { label: 'Receipt', value: 'RECEIPT' },
  { label: 'Payment', value: 'PAYMENT' },
  { label: 'Journal', value: 'JOURNAL' },
  { label: 'Contra', value: 'CONTRA' },
  { label: 'Credit Note', value: 'CREDIT_NOTE' },
  { label: 'Debit Note', value: 'DEBIT_NOTE' },
];

function statusColor(status: string) {
  const map: Record<string, string> = {
    DRAFT: 'bg-slate-100 text-slate-600',
    APPROVED: 'bg-green-100 text-green-700',
    PAID: 'bg-emerald-100 text-emerald-700',
    OVERDUE: 'bg-red-100 text-red-700',
    SENT: 'bg-blue-100 text-blue-700',
  };
  return map[status] || 'bg-slate-100 text-slate-600';
}

export default function VouchersPage() {
  const { type: urlType } = useParams<{ type?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [deleteItem, setDeleteItem] = useState<VoucherItem | null>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const voucherType = urlType?.toUpperCase() || '';

  const { data, isLoading, isError } = useQuery({
    queryKey: ['vouchers', page, voucherType, search, dateFrom, dateTo],
    queryFn: () => managementApi.vouchers({
      page,
      page_size: 20,
      voucher_type: voucherType || undefined,
      search: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteVoucher(
      deleteItem!.entity_type as 'invoice' | 'expense',
      deleteItem!.id,
    ),
    onSuccess: (res: { status?: string; message?: string }) => {
      const isPending = res.status === 'pending';
      toast({
        title: isPending ? 'Cancel sent to TallyPrime' : 'Deleted',
        description: res.message,
        variant: isPending ? 'default' : 'default',
      });
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' });
    },
  });

  const clearMut = useMutation({
    mutationFn: () => managementApi.clearLocalVouchers(),
    onSuccess: (res) => {
      toast({ title: 'Local data cleared', description: res.message });
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      setShowClearConfirm(false);
    },
    onError: () => {
      toast({ title: 'Error', description: 'Failed to clear local data', variant: 'destructive' });
    },
  });

  const totalPages = data?.total_pages ?? 1;
  const activeType = VOUCHER_TYPES.find(v => v.value === voucherType);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-600" />
            {activeType?.label || 'All Vouchers'}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Transactions and vouchers</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 text-red-600 border-red-200 hover:bg-red-50"
          onClick={() => setShowClearConfirm(true)}
        >
          <Eraser className="w-4 h-4" /> Clear Local Data
        </Button>
      </div>

      {/* Voucher type tabs */}
      <div className="flex flex-wrap gap-2">
        {VOUCHER_TYPES.map(vt => (
          <button
            key={vt.value}
            onClick={() => {
              setPage(1);
              navigate(vt.value ? `/accounting/vouchers/${vt.value.toLowerCase()}` : '/accounting/vouchers');
            }}
            className={cn(
              'px-3 py-1.5 rounded-full text-xs font-medium transition-all',
              voucherType === vt.value
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
            )}
          >
            {vt.label}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input placeholder="Search vouchers…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Filter className="w-4 h-4 text-slate-400" />
          <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-36 text-xs" />
          <span className="text-slate-400">to</span>
          <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-36 text-xs" />
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-slate-400 hover:text-slate-600">
              Clear
            </button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load vouchers.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Number</th>
                  <th className="px-4 py-3 text-left">Date</th>
                  <th className="px-4 py-3 text-left">Type</th>
                  <th className="px-4 py-3 text-left">Party</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-center">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-10 text-slate-400">No vouchers found.</td></tr>
                ) : data?.items.map(v => (
                  <tr key={v.id} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{v.voucher_number}</td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{v.date ? formatDate(v.date) : '—'}</td>
                    <td className="px-4 py-3">
                      <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-xs">{v.voucher_type}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{v.party_name || v.title || '—'}</td>
                    <td className="px-4 py-3 text-right font-medium">{formatCurrency(v.amount)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium', statusColor(v.status))}>{v.status}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <SyncBadge status={v.tally_sync_status} source={v.source} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {v.tally_sync_status === 'delete_pending' ? (
                        <span className="text-xs text-orange-600 bg-orange-50 px-2 py-1 rounded">Cancelling…</span>
                      ) : (
                        <button
                          onClick={() => setDeleteItem(v)}
                          className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                          title="Delete voucher"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
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

      {/* Clear Local Data Dialog */}
      <Dialog open={showClearConfirm} onOpenChange={setShowClearConfirm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="text-red-600 flex items-center gap-2"><Eraser className="w-4 h-4" /> Clear Local Data</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm text-slate-700">
            <p>This will permanently delete all <strong>locally-created</strong> invoices and expenses that were never synced to or imported from TallyPrime.</p>
            <div className="bg-amber-50 border border-amber-200 p-3 rounded text-amber-700 text-xs space-y-1">
              <p className="font-semibold">Safe to run before a full sync.</p>
              <p>Records already synced to TallyPrime or imported from TallyPrime will NOT be deleted.</p>
            </div>
            <p className="text-xs text-slate-500">After clearing, go to <strong>TallyPrime → Sync Center</strong> and click Sync to pull real data.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowClearConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => clearMut.mutate()} disabled={clearMut.isPending}>
              {clearMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Eraser className="w-4 h-4 mr-2" />}
              Clear Local Data
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle className="text-red-600">Delete Voucher</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm">Delete voucher <strong>{deleteItem?.voucher_number}</strong>?</p>
            {deleteItem?.tally_sync_status === 'synced' ? (
              <div className="text-xs bg-amber-50 border border-amber-200 p-3 rounded space-y-1">
                <p className="font-semibold text-amber-700">This voucher is synced to TallyPrime.</p>
                <p className="text-amber-600">
                  A cancellation request will be sent to TallyPrime. The voucher will be removed from
                  FinPilot <strong>only after TallyPrime confirms</strong> the cancellation.
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded">
                This record is local-only — it will be removed from FinPilot immediately.
                {deleteItem?.tally_sync_status === 'pending' && (
                  <span className="block mt-1 text-amber-600">Note: A Tally sync was pending. If it was already processed, cancel the voucher in TallyPrime manually.</span>
                )}
              </p>
            )}
            {(deleteItem as { paid_amount?: number })?.paid_amount && (deleteItem as { paid_amount?: number }).paid_amount! > 0 && (
              <p className="text-xs text-red-600 bg-red-50 p-2 rounded">
                ⚠ This invoice has payments recorded. Remove payments before deleting.
              </p>
            )}
          </div>
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
