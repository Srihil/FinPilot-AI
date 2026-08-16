import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Search, Loader2, AlertCircle, Trash2, Filter, Eraser, Sparkles, ChevronRight, Info } from 'lucide-react';
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
  { label: '✨ Custom', value: 'CUSTOM' },
];

// Parent type → human description of what it does
const PARENT_DESC: Record<string, { color: string; meaning: string }> = {
  Sales:       { color: 'bg-green-100 text-green-800',  meaning: 'Records a sale — increases customer receivable' },
  Purchase:    { color: 'bg-orange-100 text-orange-800', meaning: 'Records a purchase — increases supplier payable' },
  Receipt:     { color: 'bg-blue-100 text-blue-800',    meaning: 'Money received from a party into bank/cash' },
  Payment:     { color: 'bg-red-100 text-red-800',      meaning: 'Money paid out to a party from bank/cash' },
  Journal:     { color: 'bg-purple-100 text-purple-800', meaning: 'Internal ledger adjustment — no cash movement' },
  Contra:      { color: 'bg-cyan-100 text-cyan-800',    meaning: 'Transfer between your own bank/cash accounts' },
  'Credit Note':{ color: 'bg-yellow-100 text-yellow-800', meaning: 'Sales return — reverses a sale entry' },
  'Debit Note': { color: 'bg-pink-100 text-pink-800',   meaning: 'Purchase return — reverses a purchase entry' },
};

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
  const [showWipeConfirm, setShowWipeConfirm] = useState(false);

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

  const wipeMut = useMutation({
    mutationFn: () => managementApi.wipeAllVouchers(),
    onSuccess: (res) => {
      toast({ title: 'All vouchers wiped', description: res.message });
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      setShowWipeConfirm(false);
    },
    onError: () => {
      toast({ title: 'Error', description: 'Failed to wipe vouchers', variant: 'destructive' });
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
          variant="destructive"
          size="sm"
          className="gap-2"
          onClick={() => setShowWipeConfirm(true)}
        >
          <Eraser className="w-4 h-4" /> Wipe All Vouchers
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

      {voucherType === 'CUSTOM' ? (
        /* ── Custom voucher cards view ──────────────────────────────────── */
        <div className="space-y-3">
          {isLoading ? (
            [...Array(4)].map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
          ) : data?.items.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 gap-3">
                <div className="w-14 h-14 rounded-full bg-indigo-50 flex items-center justify-center">
                  <Sparkles className="w-7 h-7 text-indigo-400" />
                </div>
                <p className="font-medium text-slate-700">No custom voucher entries yet</p>
                <p className="text-sm text-slate-400 text-center max-w-sm">
                  Use <strong>Create with AI</strong> and say something like "Create a GST Bill for ABC Traders for ₹25,000"
                  to create an entry using a custom voucher type.
                </p>
              </CardContent>
            </Card>
          ) : data?.items.map(v => {
            const parentMeta = PARENT_DESC[v.parent_type || ''];
            return (
              <div key={v.id} className="rounded-xl border border-indigo-100 bg-white p-4 shadow-sm hover:shadow-md transition-all">
                <div className="flex items-start justify-between gap-4">
                  {/* Left: type + parent chain */}
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    {/* Custom type badge */}
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 text-white text-xs font-semibold shrink-0">
                      <Sparkles className="w-3 h-3" />
                      {v.custom_type_name || v.voucher_type}
                    </span>
                    {v.parent_type && (
                      <>
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        {/* Parent badge with color */}
                        <span className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium shrink-0',
                          parentMeta?.color || 'bg-slate-100 text-slate-600'
                        )}>
                          based on {v.parent_type}
                        </span>
                      </>
                    )}
                  </div>
                  {/* Right: sync + delete */}
                  <div className="flex items-center gap-2 shrink-0">
                    <SyncBadge status={v.tally_sync_status} source={v.source} />
                    {v.tally_sync_status === 'delete_pending' ? (
                      <span className="text-xs text-orange-600 bg-orange-50 px-2 py-1 rounded">Cancelling…</span>
                    ) : (
                      <button
                        onClick={() => setDeleteItem(v)}
                        className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* What this type does */}
                {parentMeta && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                    <Info className="w-3 h-3 shrink-0" />
                    <span>{parentMeta.meaning}</span>
                  </div>
                )}

                {/* Details row */}
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Party</p>
                    <p className="text-sm font-medium text-slate-800 truncate">{v.party_name || v.title || '—'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Amount</p>
                    <p className="text-sm font-semibold text-slate-900">{formatCurrency(v.amount)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Date</p>
                    <p className="text-sm text-slate-700">{v.date ? formatDate(v.date) : '—'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Narration</p>
                    <p className="text-sm text-slate-600 truncate">{v.title || '—'}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── Standard table view ────────────────────────────────────────── */
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
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>Page {page} of {totalPages} ({data?.total ?? 0} total)</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* Wipe All Vouchers Dialog */}
      <Dialog open={showWipeConfirm} onOpenChange={setShowWipeConfirm}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-red-600 flex items-center gap-2">
              <Eraser className="w-4 h-4" /> Wipe All Vouchers
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-slate-700">
            <p>This will permanently delete <strong>every invoice and expense</strong> from FinPilot for your company.</p>
            <div className="bg-red-50 border border-red-200 p-3 rounded text-red-700 text-xs space-y-1">
              <p className="font-semibold">Only voucher data is deleted.</p>
              <p>Ledgers, customers, vendors, stock groups, units, godowns — all safe.</p>
            </div>
            <p className="text-xs text-slate-500 bg-slate-50 p-2 rounded">After wiping, go to <strong>TallyPrime → Sync Center → Sync</strong> to import fresh data.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowWipeConfirm(false)}>Cancel</Button>
            <Button variant="destructive" onClick={() => wipeMut.mutate()} disabled={wipeMut.isPending}>
              {wipeMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Eraser className="w-4 h-4 mr-2" />}
              Yes, Wipe Everything
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
