import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText, Search, Loader2, AlertCircle, Trash2, Filter, Eraser,
  Sparkles, ChevronRight, ChevronDown, Info, Plus, Pencil,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import { formatCurrency, formatDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { VoucherItem, TallyLedger, VoucherTypeItem } from '../../types';

// ─── Type config ─────────────────────────────────────────────────────────────

const VOUCHER_TYPE_TABS = [
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

const CREATE_TYPES = [
  { value: 'RECEIPT',     label: 'Receipt' },
  { value: 'PAYMENT',     label: 'Payment' },
  { value: 'SALES',       label: 'Sales' },
  { value: 'PURCHASE',    label: 'Purchase' },
  { value: 'JOURNAL',     label: 'Journal' },
  { value: 'CONTRA',      label: 'Contra' },
  { value: 'CREDIT_NOTE', label: 'Credit Note' },
  { value: 'DEBIT_NOTE',  label: 'Debit Note' },
  { value: 'CUSTOM',      label: '✨ Custom' },
];

const TYPE_FIELDS: Record<string, {
  showParty?: boolean;  partyLabel?: string;
  showAccount?: boolean;
  showSalesLedger?: boolean;
  showPurchaseLedger?: boolean;
  showDrCr?: boolean;
  showFromTo?: boolean;
  showCustomType?: boolean;
  description: string;
}> = {
  RECEIPT:     { showParty: true, partyLabel: 'Party (from whom)',   showAccount: true, description: 'Money received into bank/cash' },
  PAYMENT:     { showParty: true, partyLabel: 'Party (to whom)',     showAccount: true, description: 'Money paid out from bank/cash' },
  SALES:       { showParty: true, partyLabel: 'Customer',            showSalesLedger: true, description: 'Records a sale transaction' },
  PURCHASE:    { showParty: true, partyLabel: 'Vendor / Supplier',   showPurchaseLedger: true, description: 'Records a purchase transaction' },
  JOURNAL:     { showDrCr: true,  description: 'Internal ledger adjustment — no cash movement' },
  CONTRA:      { showFromTo: true, description: 'Transfer between your own bank/cash accounts' },
  CREDIT_NOTE: { showParty: true, partyLabel: 'Customer',            showSalesLedger: true, description: 'Sales return — reverses a sale entry' },
  DEBIT_NOTE:  { showParty: true, partyLabel: 'Vendor / Supplier',   showPurchaseLedger: true, description: 'Purchase return — reverses a purchase entry' },
  CUSTOM:      { showCustomType: true, showParty: true, partyLabel: 'Party Ledger', description: 'Custom voucher type defined in TallyPrime' },
};

const PARENT_DESC: Record<string, { color: string; meaning: string }> = {
  Sales:        { color: 'bg-green-100 text-green-800',   meaning: 'Records a sale — increases customer receivable' },
  Purchase:     { color: 'bg-orange-100 text-orange-800', meaning: 'Records a purchase — increases supplier payable' },
  Receipt:      { color: 'bg-blue-100 text-blue-800',     meaning: 'Money received from a party into bank/cash' },
  Payment:      { color: 'bg-red-100 text-red-800',       meaning: 'Money paid out to a party from bank/cash' },
  Journal:      { color: 'bg-purple-100 text-purple-800', meaning: 'Internal ledger adjustment — no cash movement' },
  Contra:       { color: 'bg-cyan-100 text-cyan-800',     meaning: 'Transfer between your own bank/cash accounts' },
  'Credit Note':{ color: 'bg-yellow-100 text-yellow-800', meaning: 'Sales return — reverses a sale entry' },
  'Debit Note': { color: 'bg-pink-100 text-pink-800',     meaning: 'Purchase return — reverses a purchase entry' },
};

const VOUCHER_TYPE_BADGE: Record<string, string> = {
  SALES: 'bg-green-100 text-green-800', PURCHASE: 'bg-orange-100 text-orange-800',
  RECEIPT: 'bg-blue-100 text-blue-800', PAYMENT: 'bg-red-100 text-red-800',
  JOURNAL: 'bg-purple-100 text-purple-800', CONTRA: 'bg-cyan-100 text-cyan-800',
  CREDIT_NOTE: 'bg-yellow-100 text-yellow-800', DEBIT_NOTE: 'bg-pink-100 text-pink-800',
};

function statusColor(status: string) {
  const map: Record<string, string> = {
    DRAFT: 'bg-slate-100 text-slate-600', APPROVED: 'bg-green-100 text-green-700',
    PAID: 'bg-emerald-100 text-emerald-700', OVERDUE: 'bg-red-100 text-red-700',
    SENT: 'bg-blue-100 text-blue-700',
  };
  return map[status] || 'bg-slate-100 text-slate-600';
}

// ─── Extended voucher type (extra fields from API) ────────────────────────────

type VoucherItemExt = VoucherItem & {
  party_ledger?: string | null;
  account_ledger?: string | null;
  dr_ledger?: string | null;
  cr_ledger?: string | null;
  from_account?: string | null;
  to_account?: string | null;
};

// ─── Field label ──────────────────────────────────────────────────────────────

function DetailField({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">{label}</p>
      <p className="font-medium text-slate-800">{value}</p>
    </div>
  );
}

// ─── Expanded row detail ──────────────────────────────────────────────────────

function VoucherDetail({ v }: { v: VoucherItemExt }) {
  const vt = v.voucher_type;

  return (
    <div className="bg-slate-50 border-t border-slate-100 px-6 py-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">

        {/* Always shown */}
        <DetailField label="Narration / Title" value={v.title || undefined} />
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Date</p>
          <p className="text-slate-700">{v.date ? formatDate(v.date) : '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Amount</p>
          <p className="font-semibold text-slate-900">{formatCurrency(v.amount)}</p>
        </div>

        {/* Type-specific ledger fields */}
        {vt === 'CONTRA' ? (
          <>
            <DetailField label="From Account" value={v.from_account} />
            <DetailField label="To Account"   value={v.to_account} />
          </>
        ) : vt === 'JOURNAL' ? (
          <>
            <DetailField label="Dr Ledger" value={v.dr_ledger} />
            <DetailField label="Cr Ledger" value={v.cr_ledger} />
          </>
        ) : vt === 'RECEIPT' || vt === 'PAYMENT' ? (
          <>
            <DetailField label="Party"           value={v.party_ledger || v.party_name} />
            <DetailField label="Account (Bank/Cash)" value={v.account_ledger} />
          </>
        ) : vt === 'SALES' || vt === 'CREDIT_NOTE' ? (
          <>
            <DetailField label="Customer" value={v.party_name} />
          </>
        ) : vt === 'PURCHASE' || vt === 'DEBIT_NOTE' ? (
          <>
            <DetailField label="Vendor / Supplier" value={v.party_name} />
          </>
        ) : (
          <DetailField label="Party" value={v.party_name} />
        )}

        {v.paid_amount != null && v.paid_amount > 0 && (
          <div>
            <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Paid</p>
            <p className="font-medium text-emerald-700">{formatCurrency(v.paid_amount)}</p>
          </div>
        )}
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Source</p>
          <p className="text-slate-600">{v.source === 'tally_sync' ? 'TallyPrime' : 'FinPilot'}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Created</p>
          <p className="text-slate-600 text-xs">{v.created_at ? formatDate(v.created_at) : '—'}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Date hint ───────────────────────────────────────────────────────────────

function DateHint() {
  return (
    <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-1.5">
      <Info className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
      <p className="text-xs text-amber-700">
        Use the <strong>Current Date</strong> from TallyPrime's Gateway of Tally — not your PC's date.
      </p>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function VouchersPage() {
  const { type: urlType } = useParams<{ type?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [deleteItem, setDeleteItem] = useState<VoucherItem | null>(null);
  const [editItem, setEditItem] = useState<VoucherItem | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // ── Create form ──────────────────────────────────────────────────────────
  const [formType, setFormType] = useState('RECEIPT');
  const [formDate, setFormDate] = useState('');
  const [formAmount, setFormAmount] = useState('');
  const [formNarration, setFormNarration] = useState('');
  const [formPartyLedger, setFormPartyLedger] = useState('');
  const [formAccountLedger, setFormAccountLedger] = useState('Cash');
  const [formSalesLedger, setFormSalesLedger] = useState('Sales');
  const [formPurchaseLedger, setFormPurchaseLedger] = useState('Purchases');
  const [formDrLedger, setFormDrLedger] = useState('');
  const [formCrLedger, setFormCrLedger] = useState('');
  const [formFromAccount, setFormFromAccount] = useState('');
  const [formToAccount, setFormToAccount] = useState('');
  const [formCustomTypeName, setFormCustomTypeName] = useState('');

  // ── Edit form ────────────────────────────────────────────────────────────
  const [editDate, setEditDate] = useState('');
  const [editAmount, setEditAmount] = useState('');
  const [editNarration, setEditNarration] = useState('');
  const [editPartyLedger, setEditPartyLedger] = useState('');
  const [editAccountLedger, setEditAccountLedger] = useState('Cash');
  const [editSalesLedger, setEditSalesLedger] = useState('Sales');
  const [editPurchaseLedger, setEditPurchaseLedger] = useState('Purchases');
  const [editDrLedger, setEditDrLedger] = useState('');
  const [editCrLedger, setEditCrLedger] = useState('');
  const [editFromAccount, setEditFromAccount] = useState('');
  const [editToAccount, setEditToAccount] = useState('');

  const voucherType = urlType?.toUpperCase() || '';

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data, isLoading, isError } = useQuery({
    queryKey: ['vouchers', page, voucherType, search, dateFrom, dateTo],
    queryFn: () => managementApi.vouchers({
      page, page_size: 20,
      voucher_type: voucherType || undefined,
      search: search || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
  });

  const { data: ledgersData } = useQuery({
    queryKey: ['ledgers-all'],
    queryFn: () => managementApi.ledgers({ page_size: 100 }),
    staleTime: 60_000,
  });
  const { data: voucherTypesData } = useQuery({
    queryKey: ['voucher-types-all'],
    queryFn: () => managementApi.voucherTypes({ page_size: 100 }),
    staleTime: 60_000,
  });

  const ledgerNames = useMemo(
    () => (ledgersData?.items ?? [] as TallyLedger[]).map(l => l.name),
    [ledgersData],
  );
  const customTypeNames = useMemo(
    () => (voucherTypesData?.items ?? [] as VoucherTypeItem[])
      .filter(vt => vt.parent != null).map(vt => vt.name),
    [voucherTypesData],
  );

  // ── Helpers ──────────────────────────────────────────────────────────────

  function resetForm() {
    setFormType('RECEIPT'); setFormDate(''); setFormAmount(''); setFormNarration('');
    setFormPartyLedger(''); setFormAccountLedger('Cash'); setFormSalesLedger('Sales');
    setFormPurchaseLedger('Purchases'); setFormDrLedger(''); setFormCrLedger('');
    setFormFromAccount(''); setFormToAccount(''); setFormCustomTypeName('');
  }

  function openEdit(v: VoucherItem) {
    const vx = v as VoucherItemExt;
    setEditItem(v);
    setEditDate(v.date?.slice(0, 10) ?? '');
    setEditAmount(String(v.amount));
    setEditNarration(v.title ?? '');
    setEditPartyLedger(vx.party_ledger ?? v.party_name ?? '');
    setEditAccountLedger(vx.account_ledger ?? 'Cash');
    setEditSalesLedger('Sales');
    setEditPurchaseLedger('Purchases');
    setEditDrLedger(vx.dr_ledger ?? '');
    setEditCrLedger(vx.cr_ledger ?? '');
    setEditFromAccount(vx.from_account ?? '');
    setEditToAccount(vx.to_account ?? '');
  }

  function toggleExpand(id: string) {
    setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: () => {
      const ft = formType.toUpperCase();
      return managementApi.createVoucher({
        voucher_type: ft, date: formDate,
        amount: parseFloat(formAmount) || 0,
        narration: formNarration || undefined,
        party_ledger: formPartyLedger || undefined,
        account_ledger: formAccountLedger || undefined,
        sales_ledger: formSalesLedger || undefined,
        purchase_ledger: formPurchaseLedger || undefined,
        dr_ledger: formDrLedger || undefined,
        cr_ledger: formCrLedger || undefined,
        from_account: formFromAccount || undefined,
        to_account: formToAccount || undefined,
        custom_voucher_type_name: ft === 'CUSTOM' ? formCustomTypeName : undefined,
      });
    },
    onSuccess: () => {
      toast({ title: 'Voucher created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateVoucher(
      editItem!.entity_type, editItem!.id,
      {
        date: editDate || undefined,
        amount: editAmount ? parseFloat(editAmount) : undefined,
        narration: editNarration || undefined,
        party_ledger: editPartyLedger || undefined,
        account_ledger: editAccountLedger || undefined,
        sales_ledger: editSalesLedger || undefined,
        purchase_ledger: editPurchaseLedger || undefined,
        dr_ledger: editDrLedger || undefined,
        cr_ledger: editCrLedger || undefined,
        from_account: editFromAccount || undefined,
        to_account: editToAccount || undefined,
      },
    ),
    onSuccess: () => {
      toast({ title: 'Voucher updated', description: 'Changes saved.' });
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      setEditItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteVoucher(
      deleteItem!.entity_type as 'invoice' | 'expense', deleteItem!.id,
    ),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Cancel sent to TallyPrime' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['vouchers'] }); setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' }),
  });

  const clearMut = useMutation({
    mutationFn: () => managementApi.clearLocalVouchers(),
    onSuccess: (res) => {
      toast({ title: 'Local data cleared', description: res.message });
      qc.invalidateQueries({ queryKey: ['vouchers'] }); setShowClearConfirm(false);
    },
    onError: () => toast({ title: 'Error', description: 'Failed to clear local data', variant: 'destructive' }),
  });

  // ── Derived ───────────────────────────────────────────────────────────────

  const totalPages = data?.total_pages ?? 1;
  const activeType = VOUCHER_TYPE_TABS.find(v => v.value === voucherType);
  const ft = formType.toUpperCase();
  const ftFields = TYPE_FIELDS[ft] ?? { description: '' };

  // For edit dialog: determine fields from editItem's voucher_type
  const editVT = editItem?.voucher_type?.toUpperCase().replace(' ', '_') ?? '';
  const editFields = TYPE_FIELDS[editVT] ?? { showParty: true, partyLabel: 'Party', description: '' };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FileText className="w-6 h-6 text-indigo-600" />
            {activeType?.label || 'All Vouchers'}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Transactions and vouchers</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Voucher
        </Button>
      </div>

      {/* Type tabs */}
      <div className="flex flex-wrap gap-2">
        {VOUCHER_TYPE_TABS.map(vt => (
          <button key={vt.value}
            onClick={() => { setPage(1); navigate(vt.value ? `/accounting/vouchers/${vt.value.toLowerCase()}` : '/accounting/vouchers'); }}
            className={cn('px-3 py-1.5 rounded-full text-xs font-medium transition-all',
              voucherType === vt.value ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200')}
          >{vt.label}</button>
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
            <button onClick={() => { setDateFrom(''); setDateTo(''); }} className="text-slate-400 hover:text-slate-600 text-xs">Clear</button>
          )}
        </div>
      </div>

      {voucherType === 'CUSTOM' ? (
        /* ── Custom cards ─────────────────────────────────────────────── */
        <div className="space-y-3">
          {isLoading ? (
            [...Array(4)].map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
          ) : data?.items.length === 0 ? (
            <Card><CardContent className="flex flex-col items-center justify-center py-16 gap-3">
              <div className="w-14 h-14 rounded-full bg-indigo-50 flex items-center justify-center">
                <Sparkles className="w-7 h-7 text-indigo-400" />
              </div>
              <p className="font-medium text-slate-700">No custom voucher entries yet</p>
              <p className="text-sm text-slate-400 text-center max-w-sm">
                Click <strong>New Voucher</strong> above and choose <strong>✨ Custom</strong> to create one.
              </p>
            </CardContent></Card>
          ) : data?.items.map(v => {
            const parentMeta = PARENT_DESC[v.parent_type || ''];
            return (
              <div key={v.id} className="rounded-xl border border-indigo-100 bg-white p-4 shadow-sm hover:shadow-md transition-all">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 text-white text-xs font-semibold shrink-0">
                      <Sparkles className="w-3 h-3" />{v.custom_type_name || v.voucher_type}
                    </span>
                    {v.parent_type && (
                      <>
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className={cn('px-2 py-0.5 rounded text-xs font-medium shrink-0', parentMeta?.color || 'bg-slate-100 text-slate-600')}>
                          based on {v.parent_type}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <SyncBadge status={v.tally_sync_status} source={v.source} />
                    {v.tally_sync_status === 'delete_pending' ? (
                      <span className="text-xs text-orange-600 bg-orange-50 px-2 py-1 rounded">Cancelling…</span>
                    ) : (
                      <>
                        <button onClick={() => openEdit(v)} className="p-1.5 rounded hover:bg-indigo-50 text-slate-400 hover:text-indigo-600" title="Edit">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => setDeleteItem(v)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600" title="Delete">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {parentMeta && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-slate-500">
                    <Info className="w-3 h-3 shrink-0" /><span>{parentMeta.meaning}</span>
                  </div>
                )}
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div><p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Party</p><p className="text-sm font-medium text-slate-800 truncate">{v.party_name || v.title || '—'}</p></div>
                  <div><p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Amount</p><p className="text-sm font-semibold text-slate-900">{formatCurrency(v.amount)}</p></div>
                  <div><p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Date</p><p className="text-sm text-slate-700">{v.date ? formatDate(v.date) : '—'}</p></div>
                  <div><p className="text-[10px] text-slate-400 uppercase tracking-wide mb-0.5">Narration</p><p className="text-sm text-slate-600 truncate">{v.title || '—'}</p></div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── Standard table ───────────────────────────────────────────── */
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
                    <th className="w-8" />
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
                    <tr><td colSpan={9} className="text-center py-10 text-slate-400">No vouchers found.</td></tr>
                  ) : data?.items.map(v => {
                    const isOpen = expanded.has(v.id);
                    return (
                      <>
                        <tr key={v.id} onClick={() => toggleExpand(v.id)}
                          className={cn('border-b cursor-pointer transition-colors', isOpen ? 'bg-indigo-50/60' : 'hover:bg-slate-50')}>
                          <td className="pl-3 pr-1 py-3 text-slate-400">
                            {isOpen ? <ChevronDown className="w-4 h-4 text-indigo-500" /> : <ChevronRight className="w-4 h-4" />}
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-slate-700">{v.voucher_number}</td>
                          <td className="px-4 py-3 text-slate-500 text-xs">{v.date ? formatDate(v.date) : '—'}</td>
                          <td className="px-4 py-3">
                            <span className={cn('px-2 py-0.5 rounded text-xs font-medium', VOUCHER_TYPE_BADGE[v.voucher_type] || 'bg-slate-100 text-slate-600')}>
                              {v.voucher_type}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-700">{v.party_name || v.title || '—'}</td>
                          <td className="px-4 py-3 text-right font-medium">{formatCurrency(v.amount)}</td>
                          <td className="px-4 py-3 text-center">
                            <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium', statusColor(v.status))}>{v.status}</span>
                          </td>
                          <td className="px-4 py-3 text-center" onClick={e => e.stopPropagation()}>
                            <SyncBadge status={v.tally_sync_status} source={v.source} />
                          </td>
                          <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                            {v.tally_sync_status === 'delete_pending' ? (
                              <span className="text-xs text-orange-600 bg-orange-50 px-2 py-1 rounded">Cancelling…</span>
                            ) : (
                              <div className="flex items-center justify-end gap-1">
                                <button onClick={() => openEdit(v)} className="p-1.5 rounded hover:bg-indigo-50 text-slate-400 hover:text-indigo-600" title="Edit">
                                  <Pencil className="w-3.5 h-3.5" />
                                </button>
                                <button onClick={() => setDeleteItem(v)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600" title="Delete">
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr key={`${v.id}-detail`} className="border-b">
                            <td colSpan={9} className="p-0"><VoucherDetail v={v} /></td>
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

      {/* ═══════════════════════════════════════════════════════════════════
          CREATE DIALOG
      ═══════════════════════════════════════════════════════════════════ */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-xl" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-lg">
              <Plus className="w-5 h-5 text-indigo-600" /> New Voucher
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-5 max-h-[70vh] overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">

            {/* ── Type selector ── */}
            <div>
              <Label>Voucher Type</Label>
              <select
                value={formType}
                onChange={e => setFormType(e.target.value)}
                className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {CREATE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              {ftFields.description && (
                <p className="text-xs text-slate-400 mt-1.5 flex items-center gap-1.5">
                  <Info className="w-3 h-3" />{ftFields.description}
                </p>
              )}
            </div>

            <div className="border-t border-slate-100" />

            {/* ── Custom type name ── */}
            {ftFields.showCustomType && (
              <div>
                <Label>Voucher Type Name <span className="text-red-500">*</span></Label>
                <Combobox options={customTypeNames} value={formCustomTypeName} onChange={setFormCustomTypeName} placeholder="Select custom type…" className="mt-1.5" />
              </div>
            )}

            {/* ── Date + Amount in 2-col grid ── */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Date <span className="text-red-500">*</span></Label>
                <Input type="date" value={formDate} onChange={e => setFormDate(e.target.value)} className="mt-1.5" />
                <DateHint />
              </div>
              <div>
                <Label>Amount <span className="text-red-500">*</span></Label>
                <div className="relative mt-1.5">
                  <span className="absolute left-3 top-2.5 text-slate-400 text-sm">₹</span>
                  <Input
                    type="number" min="0" step="0.01" placeholder="0.00"
                    value={formAmount} onChange={e => setFormAmount(e.target.value)}
                    className="pl-7"
                  />
                </div>
              </div>
            </div>

            {/* ── Party ledger ── */}
            {ftFields.showParty && (
              <div>
                <Label>{ftFields.partyLabel || 'Party Ledger'} <span className="text-red-500">*</span></Label>
                <Combobox options={ledgerNames} value={formPartyLedger} onChange={setFormPartyLedger} placeholder="Select ledger…" className="mt-1.5" />
              </div>
            )}

            {/* ── Sales / Purchase ledger ── */}
            {ftFields.showSalesLedger && (
              <div>
                <Label>Sales Ledger <span className="text-red-500">*</span></Label>
                <Combobox options={ledgerNames} value={formSalesLedger} onChange={setFormSalesLedger} placeholder="Sales" className="mt-1.5" />
              </div>
            )}
            {ftFields.showPurchaseLedger && (
              <div>
                <Label>Purchase Ledger <span className="text-red-500">*</span></Label>
                <Combobox options={ledgerNames} value={formPurchaseLedger} onChange={setFormPurchaseLedger} placeholder="Purchases" className="mt-1.5" />
              </div>
            )}

            {/* ── Account (Bank / Cash) ── */}
            {ftFields.showAccount && (
              <div>
                <Label>Account (Bank / Cash) <span className="text-red-500">*</span></Label>
                <Combobox options={ledgerNames} value={formAccountLedger} onChange={setFormAccountLedger} placeholder="Cash" className="mt-1.5" />
              </div>
            )}

            {/* ── Journal: Dr + Cr ── */}
            {ftFields.showDrCr && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Dr Ledger <span className="text-red-500">*</span></Label>
                  <Combobox options={ledgerNames} value={formDrLedger} onChange={setFormDrLedger} placeholder="Debit ledger…" className="mt-1.5" />
                </div>
                <div>
                  <Label>Cr Ledger <span className="text-red-500">*</span></Label>
                  <Combobox options={ledgerNames} value={formCrLedger} onChange={setFormCrLedger} placeholder="Credit ledger…" className="mt-1.5" />
                </div>
              </div>
            )}

            {/* ── Contra: From + To ── */}
            {ftFields.showFromTo && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>From Account <span className="text-red-500">*</span></Label>
                  <Combobox options={ledgerNames} value={formFromAccount} onChange={setFormFromAccount} placeholder="Source…" className="mt-1.5" />
                </div>
                <div>
                  <Label>To Account <span className="text-red-500">*</span></Label>
                  <Combobox options={ledgerNames} value={formToAccount} onChange={setFormToAccount} placeholder="Destination…" className="mt-1.5" />
                </div>
              </div>
            )}

            {/* ── Narration ── */}
            <div className="pb-1">
              <Label>Narration</Label>
              <Input value={formNarration} onChange={e => setFormNarration(e.target.value)} placeholder="Description / remarks" className="mt-1.5" />
            </div>
          </div>

          <DialogFooter className="mt-4 gap-2">
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={createMut.isPending} className="gap-2">
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              Create &amp; Sync
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ═══════════════════════════════════════════════════════════════════
          EDIT DIALOG
      ═══════════════════════════════════════════════════════════════════ */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-xl" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-lg">
              <Pencil className="w-4 h-4 text-indigo-600" /> Edit Voucher
            </DialogTitle>
          </DialogHeader>

          {editItem && (
            <div className="space-y-5 max-h-[70vh] overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">

              {/* ── Voucher info badge ── */}
              <div className="flex items-center gap-2 p-3 bg-slate-50 rounded-lg border border-slate-200">
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-slate-400 mb-0.5">Voucher</p>
                  <p className="font-mono font-semibold text-slate-800 text-sm truncate">{editItem.voucher_number}</p>
                </div>
                <span className={cn('px-2.5 py-1 rounded-full text-xs font-semibold shrink-0',
                  VOUCHER_TYPE_BADGE[editVT] || 'bg-slate-100 text-slate-600')}>
                  {editItem.voucher_type}
                </span>
                <SyncBadge status={editItem.tally_sync_status} source={editItem.source} />
              </div>

              <div className="border-t border-slate-100" />

              {/* ── Date + Amount grid ── */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Date</Label>
                  <Input type="date" value={editDate} onChange={e => setEditDate(e.target.value)} className="mt-1.5" />
                  <DateHint />
                </div>
                <div>
                  <Label>Amount</Label>
                  <div className="relative mt-1.5">
                    <span className="absolute left-3 top-2.5 text-slate-400 text-sm">₹</span>
                    <Input
                      type="number" min="0" step="0.01" placeholder="0.00"
                      value={editAmount} onChange={e => setEditAmount(e.target.value)}
                      className="pl-7"
                    />
                  </div>
                </div>
              </div>

              {/* ── Narration ── */}
              <div>
                <Label>Narration</Label>
                <Input value={editNarration} onChange={e => setEditNarration(e.target.value)} placeholder="Description / remarks" className="mt-1.5" />
              </div>

              <div className="border-t border-slate-100" />

              {/* ── Type-specific ledger dropdowns ── */}
              {editFields.showParty && (
                <div>
                  <Label>{editFields.partyLabel || 'Party Ledger'}</Label>
                  <Combobox options={ledgerNames} value={editPartyLedger} onChange={setEditPartyLedger} placeholder="Select party ledger…" className="mt-1.5" />
                </div>
              )}

              {editFields.showSalesLedger && (
                <div>
                  <Label>Sales Ledger</Label>
                  <Combobox options={ledgerNames} value={editSalesLedger} onChange={setEditSalesLedger} placeholder="Sales" className="mt-1.5" />
                </div>
              )}
              {editFields.showPurchaseLedger && (
                <div>
                  <Label>Purchase Ledger</Label>
                  <Combobox options={ledgerNames} value={editPurchaseLedger} onChange={setEditPurchaseLedger} placeholder="Purchases" className="mt-1.5" />
                </div>
              )}

              {editFields.showAccount && (
                <div>
                  <Label>Account (Bank / Cash)</Label>
                  <Combobox options={ledgerNames} value={editAccountLedger} onChange={setEditAccountLedger} placeholder="Cash" className="mt-1.5" />
                </div>
              )}

              {editFields.showDrCr && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Dr Ledger</Label>
                    <Combobox options={ledgerNames} value={editDrLedger} onChange={setEditDrLedger} placeholder="Debit ledger…" className="mt-1.5" />
                  </div>
                  <div>
                    <Label>Cr Ledger</Label>
                    <Combobox options={ledgerNames} value={editCrLedger} onChange={setEditCrLedger} placeholder="Credit ledger…" className="mt-1.5" />
                  </div>
                </div>
              )}

              {editFields.showFromTo && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>From Account</Label>
                    <Combobox options={ledgerNames} value={editFromAccount} onChange={setEditFromAccount} placeholder="Source…" className="mt-1.5" />
                  </div>
                  <div>
                    <Label>To Account</Label>
                    <Combobox options={ledgerNames} value={editToAccount} onChange={setEditToAccount} placeholder="Destination…" className="mt-1.5" />
                  </div>
                </div>
              )}

              {/* ── Sync warning ── */}
              {editItem.tally_sync_status === 'synced' && (
                <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <Info className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
                  <div className="text-xs text-amber-700 space-y-0.5">
                    <p className="font-semibold">Synced to TallyPrime</p>
                    <p>Saving will re-queue this voucher for sync. TallyPrime will update the existing entry using its REMOTEID.</p>
                  </div>
                </div>
              )}
              <div className="pb-1" />
            </div>
          )}

          <DialogFooter className="mt-4 gap-2">
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending} className="gap-2">
              {updateMut.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              Save Changes
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
              <p>Records already synced to TallyPrime will NOT be deleted.</p>
            </div>
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
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="text-red-600">Delete Voucher</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-sm">Delete voucher <strong>{deleteItem?.voucher_number}</strong>?</p>
            {deleteItem?.tally_sync_status === 'synced' ? (
              <div className="text-xs bg-amber-50 border border-amber-200 p-3 rounded space-y-1">
                <p className="font-semibold text-amber-700">This voucher is synced to TallyPrime.</p>
                <p className="text-amber-600">A cancellation request will be sent. The voucher will be removed once TallyPrime confirms.</p>
              </div>
            ) : (
              <p className="text-xs text-slate-500 bg-slate-50 p-3 rounded">
                Local-only record — will be removed from FinPilot immediately.
                {deleteItem?.tally_sync_status === 'pending' && (
                  <span className="block mt-1 text-amber-600">A Tally sync was pending. If already processed, cancel in TallyPrime manually.</span>
                )}
              </p>
            )}
            {(deleteItem as { paid_amount?: number })?.paid_amount != null &&
              (deleteItem as { paid_amount?: number }).paid_amount! > 0 && (
              <p className="text-xs text-red-600 bg-red-50 p-2 rounded">⚠ This invoice has payments recorded. Remove payments before deleting.</p>
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
