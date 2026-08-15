import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Layers, Users, Building2, Package, BookOpen, FolderOpen, Scale, Warehouse,
  FileText, Plus, Search, ChevronRight, Loader2, AlertCircle,
  CheckCircle, Clock, WifiOff, Wifi, Activity, BarChart3, Database, ChevronLeft,
  Edit, Trash2, AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from '../../components/ui/use-toast';
import { customersApi, vendorsApi, productsApi, managementApi } from '../../api/endpoints';
import { formatCurrency, formatDate } from '../../utils/format';
import { cn } from '../../utils/cn';
import type {
  Customer, Vendor, Product,
  TallyLedger, TallyStockGroup, TallyUnit, TallyGodown,
  ManagementOverview, VoucherItem,
} from '../../types';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relTime(iso: string | null | undefined) {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString();
}

function fmtOp(op: string) {
  return op.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());
}

// ─── Sync status badge ────────────────────────────────────────────────────────

function SyncBadge({ status, source }: { status: string; source?: string }) {
  const cfg: Record<string, { cls: string; label: string }> = {
    synced:         { cls: 'bg-emerald-100 text-emerald-700', label: 'Synced' },
    pending:        { cls: 'bg-amber-100 text-amber-700', label: 'Pending' },
    failed:         { cls: 'bg-red-100 text-red-700', label: 'Failed' },
    finpilot:       { cls: 'bg-indigo-100 text-indigo-700', label: 'FinPilot' },
    tally_sync:     { cls: 'bg-teal-100 text-teal-700', label: 'TallyPrime' },
    delete_pending: { cls: 'bg-orange-100 text-orange-700', label: 'Deleting…' },
    delete_failed:  { cls: 'bg-red-100 text-red-700', label: 'Delete Failed' },
  };
  const key = source === 'tally_sync' ? 'tally_sync' : status;
  const c = cfg[key] ?? { cls: 'bg-slate-100 text-slate-600', label: status };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.cls}`}>
      {c.label}
    </span>
  );
}

function JobStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    SUCCESS:   'bg-emerald-100 text-emerald-700',
    FAILED:    'bg-red-100 text-red-700',
    PENDING:   'bg-amber-100 text-amber-700',
    CLAIMED:   'bg-blue-100 text-blue-700',
    RUNNING:   'bg-indigo-100 text-indigo-700',
    RETRYING:  'bg-orange-100 text-orange-700',
    CANCELLED: 'bg-slate-100 text-slate-600',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cfg[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {status}
    </span>
  );
}

// ─── Stat card ────────────────────────────────────────────────────────────────

// ─── Shared Delete Dialog ─────────────────────────────────────────────────────

function DeleteDialog({ name, entityLabel, wasSynced, onConfirm, onClose, loading }: {
  name: string; entityLabel: string; wasSynced: boolean;
  onConfirm: () => void; onClose: () => void; loading: boolean;
}) {
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <Trash2 className="w-4 h-4" /> Delete {entityLabel}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="text-sm text-slate-700">
            Delete <strong>"{name}"</strong>?
          </p>
          {wasSynced ? (
            <div className="flex items-start gap-2.5 p-3 bg-amber-50 border border-amber-100 rounded-lg">
              <Clock className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-sm text-amber-800">
                <p className="font-semibold mb-0.5">Requires TallyPrime confirmation</p>
                <p>This record exists in TallyPrime. A delete request will be sent — the record will stay visible in FinPilot until TallyPrime confirms the deletion. If Tally rejects it (e.g. linked transactions), the record will remain and you'll see a "Delete Failed" status.</p>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2.5 p-3 bg-blue-50 border border-blue-100 rounded-lg">
              <CheckCircle className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
              <div className="text-sm text-blue-800">
                <p className="font-semibold mb-0.5">Will be removed immediately</p>
                <p>This record is only in FinPilot and has not been synced to TallyPrime.</p>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={loading} className="gap-1.5">
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {wasSynced ? 'Queue Delete' : 'Delete'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Action buttons ───────────────────────────────────────────────────────────

function RowActions({ onEdit, onDelete, deleteDisabled }: {
  onEdit: () => void; onDelete: () => void; deleteDisabled?: boolean;
}) {
  return (
    <div className="flex gap-1">
      <button onClick={onEdit} className="p-1.5 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors" title="Edit">
        <Edit className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={deleteDisabled ? undefined : onDelete}
        disabled={deleteDisabled}
        className={`p-1.5 rounded transition-colors ${deleteDisabled ? 'text-slate-200 cursor-not-allowed' : 'text-slate-400 hover:text-red-600 hover:bg-red-50'}`}
        title={deleteDisabled ? 'Delete pending TallyPrime confirmation' : 'Delete'}
      >
        {deleteDisabled ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color, onClick }: {
  label: string; value: number | string; icon: React.ElementType; color: string; onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "flex items-center gap-4 p-4 bg-white rounded-xl border border-slate-100 shadow-sm",
        onClick && "cursor-pointer hover:border-indigo-200 hover:shadow-md transition-all"
      )}
    >
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
        <p className="text-xs text-slate-500">{label}</p>
      </div>
    </div>
  );
}

// ─── Pagination ───────────────────────────────────────────────────────────────

function Paginator({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (p: number) => void }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2 mt-4">
      <Button variant="outline" size="sm" onClick={() => onPage(page - 1)} disabled={page === 1}>
        <ChevronLeft className="w-4 h-4" />
      </Button>
      <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
      <Button variant="outline" size="sm" onClick={() => onPage(page + 1)} disabled={page === totalPages}>
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, title, desc, action }: {
  icon: React.ElementType; title: string; desc: string; action?: React.ReactNode;
}) {
  return (
    <div className="py-16 text-center">
      <Icon className="w-10 h-10 text-slate-200 mx-auto mb-3" />
      <p className="font-medium text-slate-600">{title}</p>
      <p className="text-sm text-slate-400 mt-1 mb-4">{desc}</p>
      {action}
    </div>
  );
}

// ─── Table header ─────────────────────────────────────────────────────────────

function TH({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th className={cn(
      "py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide",
      right ? "text-right" : "text-left"
    )}>
      {children}
    </th>
  );
}

function TD({ children, className, right }: { children: React.ReactNode; className?: string; right?: boolean }) {
  return <td className={cn("py-3 px-4 text-sm", right && "text-right", className)}>{children}</td>;
}

// ─── Tab definitions ──────────────────────────────────────────────────────────

const MAIN_TABS = ['Overview', 'Masters', 'Transactions'] as const;
type MainTab = typeof MAIN_TABS[number];

const VOUCHER_TYPES = ['ALL', 'SALES', 'PURCHASE', 'EXPENSE'] as const;

const MASTER_TABS = ['Customers', 'Vendors', 'Ledgers', 'Products', 'Stock Groups', 'Units', 'Godowns'] as const;
type MasterTab = typeof MASTER_TABS[number];


// ─── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab({ onNavigate, onGoTally }: { onNavigate: (tab: MainTab, sub?: MasterTab) => void; onGoTally: () => void }) {
  const { data: ov, isLoading } = useQuery({
    queryKey: ['management-overview'],
    queryFn: managementApi.overview,
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
        <Skeleton className="h-40" />
      </div>
    );
  }

  const t = ov?.totals;
  const s = ov?.sync;
  const tally = ov?.tally;

  return (
    <div className="space-y-6">
      {/* ── Tally connection banner ── */}
      <Card className={tally?.online ? 'border-emerald-200 bg-emerald-50' : tally?.connected ? 'border-amber-200 bg-amber-50' : 'border-slate-200'}>
        <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="flex items-center gap-3">
            {tally?.online ? (
              <Wifi className="w-5 h-5 text-emerald-600 shrink-0" />
            ) : tally?.connected ? (
              <Wifi className="w-5 h-5 text-amber-600 shrink-0" />
            ) : (
              <WifiOff className="w-5 h-5 text-slate-400 shrink-0" />
            )}
            <div>
              <p className="font-semibold text-sm text-slate-900">
                {tally?.online
                  ? `TallyPrime Online — ${tally.company || 'Connected'}`
                  : tally?.connected
                  ? 'Connector paired — TallyPrime offline or heartbeat timed out'
                  : 'No TallyPrime connector paired'}
              </p>
              {tally?.last_heartbeat && (
                <p className="text-xs text-slate-500">Last heartbeat: {relTime(tally.last_heartbeat)}</p>
              )}
            </div>
          </div>
          <div className="sm:ml-auto flex items-center gap-2 shrink-0">
            {s && s.pending_jobs > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                <Clock className="w-3 h-3" />
                {s.pending_jobs} pending
              </span>
            )}
            {s && s.failed_jobs > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
                <AlertCircle className="w-3 h-3" />
                {s.failed_jobs} failed
              </span>
            )}
            <Button size="sm" variant="outline" onClick={onGoTally} className="gap-1.5">
              <Activity className="w-3.5 h-3.5" />
              Sync Center
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Stats grid ── */}
      <div>
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Masters</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Customers" value={t?.customers ?? 0} icon={Users} color="bg-blue-100 text-blue-600" onClick={() => onNavigate('Masters', 'Customers')} />
          <StatCard label="Vendors" value={t?.vendors ?? 0} icon={Building2} color="bg-purple-100 text-purple-600" onClick={() => onNavigate('Masters', 'Vendors')} />
          <StatCard label="Products" value={t?.products ?? 0} icon={Package} color="bg-emerald-100 text-emerald-600" onClick={() => onNavigate('Masters', 'Products')} />
          <StatCard label="Ledgers" value={t?.ledgers ?? 0} icon={BookOpen} color="bg-teal-100 text-teal-600" onClick={() => onNavigate('Masters', 'Ledgers')} />
          <StatCard label="Stock Groups" value={t?.stock_groups ?? 0} icon={FolderOpen} color="bg-indigo-100 text-indigo-600" onClick={() => onNavigate('Masters', 'Stock Groups')} />
          <StatCard label="Units" value={t?.units ?? 0} icon={Scale} color="bg-slate-100 text-slate-600" onClick={() => onNavigate('Masters', 'Units')} />
          <StatCard label="Godowns" value={t?.godowns ?? 0} icon={Warehouse} color="bg-amber-100 text-amber-600" onClick={() => onNavigate('Masters', 'Godowns')} />
        </div>
      </div>

      {/* ── Sync stats ── */}
      <div>
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">Tally Sync</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <Clock className="w-5 h-5 text-amber-500 shrink-0" />
              <div>
                <p className="text-xl font-bold text-slate-900">{s?.pending_jobs ?? 0}</p>
                <p className="text-xs text-slate-500">Pending jobs</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
              <div>
                <p className="text-xl font-bold text-slate-900">{s?.failed_jobs ?? 0}</p>
                <p className="text-xs text-slate-500">Failed jobs</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 flex items-center gap-3">
              <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-slate-900">{relTime(s?.last_sync)}</p>
                <p className="text-xs text-slate-500">Last successful sync</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

// ─── Customers sub-tab ────────────────────────────────────────────────────────

function CustomersSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [deleting, setDeleting] = useState<Customer | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['customers', page, debouncedSearch],
    queryFn: () => customersApi.list({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await customersApi.delete(deleting.id);
      toast({ title: 'Customer deleted', variant: 'success' });
      qc.invalidateQueries({ queryKey: ['customers'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search customers…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <TH>Name</TH><TH>Email</TH><TH>GSTIN</TH>
              <TH right>Outstanding</TH><TH>Status</TH><TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={6} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((c: Customer) => (
              <tr key={c.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD>
                  <p className="font-medium text-slate-900">{c.name}</p>
                  {c.phone && <p className="text-xs text-slate-400">{c.phone}</p>}
                </TD>
                <TD className="text-slate-600">{c.email || '—'}</TD>
                <TD className="text-slate-500 font-mono text-xs">{c.gst_number || '—'}</TD>
                <TD right className="font-medium">
                  <span className={c.outstanding_balance > 0 ? 'text-amber-600' : 'text-slate-600'}>
                    {formatCurrency(c.outstanding_balance || 0)}
                  </span>
                </TD>
                <TD>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${c.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {c.is_active ? 'Active' : 'Inactive'}
                  </span>
                </TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(c)} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={6}>
                  <EmptyState icon={Users} title="No customers yet" desc="Add your first customer to get started." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />

      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Customer" wasSynced={false}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={false} />
      )}
    </div>
  );
}

// ─── Vendors sub-tab ─────────────────────────────────────────────────────────

function VendorsSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [deleting, setDeleting] = useState<Vendor | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['vendors', page, debouncedSearch],
    queryFn: () => vendorsApi.list({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await vendorsApi.delete(deleting.id);
      toast({ title: 'Vendor deleted', variant: 'success' });
      qc.invalidateQueries({ queryKey: ['vendors'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search vendors…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <TH>Name</TH><TH>Email</TH><TH>GSTIN</TH>
              <TH right>Outstanding Payable</TH><TH>Status</TH><TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={6} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((v: Vendor) => (
              <tr key={v.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD>
                  <p className="font-medium text-slate-900">{v.name}</p>
                  {v.phone && <p className="text-xs text-slate-400">{v.phone}</p>}
                </TD>
                <TD className="text-slate-600">{v.email || '—'}</TD>
                <TD className="text-slate-500 font-mono text-xs">{v.gst_number || '—'}</TD>
                <TD right className="font-medium">
                  <span className={v.outstanding_payable > 0 ? 'text-amber-600' : 'text-slate-600'}>
                    {formatCurrency(v.outstanding_payable || 0)}
                  </span>
                </TD>
                <TD>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${v.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {v.is_active ? 'Active' : 'Inactive'}
                  </span>
                </TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(v)} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={6}>
                  <EmptyState icon={Building2} title="No vendors yet" desc="Add your first vendor to get started." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Vendor" wasSynced={false}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={false} />
      )}
    </div>
  );
}

// ─── Products sub-tab ─────────────────────────────────────────────────────────

function ProductsSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [deleting, setDeleting] = useState<Product | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['products', page, debouncedSearch],
    queryFn: () => productsApi.list({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await productsApi.delete(deleting.id);
      toast({ title: 'Product deleted', variant: 'success' });
      qc.invalidateQueries({ queryKey: ['products'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search products…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <TH>Name / SKU</TH><TH>Category</TH><TH>Unit</TH>
              <TH right>Stock</TH><TH right>Value</TH><TH>Status</TH><TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={7} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((p: Product) => (
              <tr key={p.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD>
                  <p className="font-medium text-slate-900">{p.name}</p>
                  {p.sku && <p className="text-xs text-slate-400 font-mono">{p.sku}</p>}
                </TD>
                <TD className="text-slate-600">{p.category || '—'}</TD>
                <TD className="text-slate-600">{p.unit || '—'}</TD>
                <TD right>
                  <span className={p.is_low_stock ? 'text-amber-600 font-medium' : 'text-slate-700'}>
                    {p.stock_quantity}
                  </span>
                </TD>
                <TD right className="font-medium text-slate-900">{formatCurrency(p.total_value || 0)}</TD>
                <TD>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${p.status === 'ACTIVE' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {p.status}
                  </span>
                </TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(p)} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={7}>
                  <EmptyState icon={Package} title="No products yet" desc="Add your first product to the inventory." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Product" wasSynced={false}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={false} />
      )}
    </div>
  );
}

// ─── Generic Tally master tab (Ledgers / Stock Groups / Units / Godowns) ──────

type TallyMasterConfig = {
  key: string;
  label: string;
  icon: React.ElementType;
  columns: string[];
  fetchFn: (params: { page: number; page_size: number; search?: string }) => Promise<{ items: unknown[]; total: number; total_pages: number }>;
  createFn: ((data: Record<string, unknown>) => Promise<unknown>) | null;
  renderRow: (item: unknown) => React.ReactNode;
  FormContent: React.FC<{ onClose: () => void }>;
  emptyTitle: string;
  emptyDesc: string;
};

// Ledger form
function LedgerForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [group, setGroup] = useState('Sundry Debtors');
  const [balance, setBalance] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast({ title: 'Name is required', variant: 'destructive' }); return; }
    setLoading(true);
    try {
      await managementApi.createLedger({ name: name.trim(), parent_group: group, opening_balance: parseFloat(balance) || 0 });
      toast({ title: `Ledger "${name}" created`, variant: 'success' });
      qc.invalidateQueries({ queryKey: ['management-ledgers'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Failed', description: err?.response?.data?.detail || 'Could not create ledger', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const COMMON_GROUPS = ['Sundry Debtors', 'Sundry Creditors', 'Bank Accounts', 'Cash-in-Hand', 'Current Assets', 'Current Liabilities', 'Capital Account', 'Loans (Liability)', 'Sales', 'Purchase', 'Direct Expenses', 'Indirect Expenses', 'Direct Incomes', 'Indirect Incomes'];

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Ledger Name *</Label>
        <Input placeholder="e.g. ABC Bank" value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Parent Group *</Label>
        <select
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          value={group} onChange={e => setGroup(e.target.value)}
        >
          {COMMON_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label>Opening Balance</Label>
        <Input type="number" placeholder="0.00" value={balance} onChange={e => setBalance(e.target.value)} />
      </div>
      <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-800">
        This ledger will be created in FinPilot and queued for synchronization to TallyPrime when connected.
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={loading} className="gap-1.5">
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          Create Ledger
        </Button>
      </DialogFooter>
    </div>
  );
}

// Stock Group form
function StockGroupForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [parent, setParent] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast({ title: 'Name is required', variant: 'destructive' }); return; }
    setLoading(true);
    try {
      await managementApi.createStockGroup({ name: name.trim(), parent: parent.trim() || undefined });
      toast({ title: `Stock group "${name}" created`, variant: 'success' });
      qc.invalidateQueries({ queryKey: ['management-stock-groups'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Failed', description: err?.response?.data?.detail || 'Could not create stock group', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Group Name *</Label>
        <Input placeholder="e.g. Electronics" value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Parent Group</Label>
        <Input placeholder="Leave empty for root group" value={parent} onChange={e => setParent(e.target.value)} />
        <p className="text-xs text-slate-400">Leave empty to create a top-level stock group. Do not enter "Primary".</p>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={loading} className="gap-1.5">
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          Create Stock Group
        </Button>
      </DialogFooter>
    </div>
  );
}

// Unit form
function UnitForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');
  const [decimals, setDecimals] = useState('0');
  const [loading, setLoading] = useState(false);
  const [symbolError, setSymbolError] = useState('');

  const validateSymbol = (v: string) => {
    if (v.includes(' ')) return 'Symbol must not contain spaces';
    if (v.length > 8) return 'Symbol must be 8 characters or fewer';
    return '';
  };

  const submit = async () => {
    if (!name.trim()) { toast({ title: 'Name is required', variant: 'destructive' }); return; }
    const sym = symbol.trim() || name.trim();
    const err = validateSymbol(sym);
    if (err) { setSymbolError(err); return; }
    setLoading(true);
    try {
      await managementApi.createUnit({ name: name.trim(), symbol: sym, decimal_places: parseInt(decimals) || 0 });
      toast({ title: `Unit "${name}" created`, variant: 'success' });
      qc.invalidateQueries({ queryKey: ['management-units'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
      onClose();
    } catch (e: unknown) {
      const err2 = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Failed', description: err2?.response?.data?.detail || 'Could not create unit', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Unit Name *</Label>
        <Input placeholder="e.g. Nos, Kg, Litre" value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Symbol</Label>
        <Input
          placeholder="e.g. Nos, Kg, Ltr (max 8 chars, no spaces)"
          value={symbol}
          onChange={e => { setSymbol(e.target.value); setSymbolError(validateSymbol(e.target.value)); }}
        />
        {symbolError && <p className="text-xs text-red-500">{symbolError}</p>}
        <p className="text-xs text-slate-400">Leave empty to use the unit name as symbol.</p>
      </div>
      <div className="space-y-1.5">
        <Label>Decimal Places</Label>
        <Input type="number" min="0" max="4" placeholder="0" value={decimals} onChange={e => setDecimals(e.target.value)} />
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={loading} className="gap-1.5">
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          Create Unit
        </Button>
      </DialogFooter>
    </div>
  );
}

// Godown form
function GodownForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [parent, setParent] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name.trim()) { toast({ title: 'Name is required', variant: 'destructive' }); return; }
    setLoading(true);
    try {
      await managementApi.createGodown({ name: name.trim(), parent: parent.trim() || undefined });
      toast({ title: `Godown "${name}" created`, variant: 'success' });
      qc.invalidateQueries({ queryKey: ['management-godowns'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
      onClose();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Failed', description: err?.response?.data?.detail || 'Could not create godown', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Godown Name *</Label>
        <Input placeholder="e.g. Main Warehouse" value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Parent Location</Label>
        <Input placeholder="Leave empty for root location" value={parent} onChange={e => setParent(e.target.value)} />
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={submit} disabled={loading} className="gap-1.5">
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          Create Godown
        </Button>
      </DialogFooter>
    </div>
  );
}

// ─── Ledgers sub-tab ──────────────────────────────────────────────────────────

function LedgersSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<TallyLedger | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['management-ledgers', page, debouncedSearch],
    queryFn: () => managementApi.ledgers({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      const res = await managementApi.deleteLedger(deleting.id);
      if (res.status === 'pending') {
        toast({ title: 'Delete queued', description: 'Waiting for TallyPrime to confirm. The ledger stays visible until then.', variant: 'default' });
      } else {
        toast({ title: 'Ledger deleted', variant: 'success' });
      }
      qc.invalidateQueries({ queryKey: ['management-ledgers'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleteLoading(false);
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search ledgers…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5 shrink-0">
          <Plus className="w-4 h-4" /> Add Ledger
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <TH>Ledger Name</TH><TH>Parent Group</TH>
              <TH right>Opening Balance</TH><TH right>Closing Balance</TH>
              <TH>Source</TH><TH>Tally Sync</TH><TH>Last Synced</TH><TH>Actions</TH>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={8} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((l: TallyLedger) => (
              <tr key={l.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD><p className="font-medium text-slate-900">{l.name}</p></TD>
                <TD className="text-slate-600">{l.parent_group || '—'}</TD>
                <TD right className="text-slate-700">{formatCurrency(l.opening_balance || 0)}</TD>
                <TD right className="text-slate-700">{formatCurrency(l.closing_balance || 0)}</TD>
                <TD><SyncBadge status={l.tally_sync_status} source={l.source} /></TD>
                <TD><SyncBadge status={l.tally_sync_status} /></TD>
                <TD className="text-slate-400 text-xs">{relTime(l.synced_at)}</TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(l)} deleteDisabled={l.tally_sync_status === 'delete_pending'} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={8}>
                  <EmptyState
                    icon={BookOpen}
                    title="No ledgers yet"
                    desc="Create a ledger to sync it to TallyPrime."
                    action={<Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5"><Plus className="w-4 h-4" /> Add Ledger</Button>}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Ledger" wasSynced={['synced', 'finpilot', 'delete_failed'].includes(deleting.tally_sync_status)}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={deleteLoading} />
      )}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Tally Ledger</DialogTitle></DialogHeader>
          <LedgerForm onClose={() => setShowForm(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Stock Groups sub-tab ─────────────────────────────────────────────────────

function StockGroupsSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<TallyStockGroup | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['management-stock-groups', page, debouncedSearch],
    queryFn: () => managementApi.stockGroups({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      const res = await managementApi.deleteStockGroup(deleting.id);
      if (res.status === 'pending') {
        toast({ title: 'Delete queued', description: 'Waiting for TallyPrime to confirm. The stock group stays visible until then.', variant: 'default' });
      } else {
        toast({ title: 'Stock group deleted', variant: 'success' });
      }
      qc.invalidateQueries({ queryKey: ['management-stock-groups'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleteLoading(false);
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search stock groups…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5 shrink-0">
          <Plus className="w-4 h-4" /> Add Group
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr><TH>Group Name</TH><TH>Parent</TH><TH>Source</TH><TH>Tally Sync</TH><TH>Last Synced</TH><TH>Actions</TH></tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={6} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((sg: TallyStockGroup) => (
              <tr key={sg.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD><p className="font-medium text-slate-900">{sg.name}</p></TD>
                <TD className="text-slate-500">{sg.parent || <span className="text-slate-300 italic">Root</span>}</TD>
                <TD><SyncBadge status={sg.tally_sync_status} source={sg.source} /></TD>
                <TD><SyncBadge status={sg.tally_sync_status} /></TD>
                <TD className="text-slate-400 text-xs">{relTime(sg.synced_at)}</TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(sg)} deleteDisabled={sg.tally_sync_status === 'delete_pending'} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={FolderOpen}
                    title="No stock groups yet"
                    desc="Create a stock group to organize your inventory in TallyPrime."
                    action={<Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5"><Plus className="w-4 h-4" /> Add Stock Group</Button>}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Stock Group" wasSynced={['synced', 'finpilot', 'delete_failed'].includes(deleting.tally_sync_status)}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={deleteLoading} />
      )}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Stock Group</DialogTitle></DialogHeader>
          <StockGroupForm onClose={() => setShowForm(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Units sub-tab ────────────────────────────────────────────────────────────

function UnitsSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<TallyUnit | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['management-units', page, debouncedSearch],
    queryFn: () => managementApi.units({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      const res = await managementApi.deleteUnit(deleting.id);
      if (res.status === 'pending') {
        toast({ title: 'Delete queued', description: 'Waiting for TallyPrime to confirm. The unit stays visible until then.', variant: 'default' });
      } else {
        toast({ title: 'Unit deleted', variant: 'success' });
      }
      qc.invalidateQueries({ queryKey: ['management-units'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleteLoading(false);
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search units…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5 shrink-0">
          <Plus className="w-4 h-4" /> Add Unit
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr><TH>Name</TH><TH>Symbol</TH><TH>Decimals</TH><TH>Type</TH><TH>Source</TH><TH>Tally Sync</TH><TH>Actions</TH></tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={7} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((u: TallyUnit) => (
              <tr key={u.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD><p className="font-medium text-slate-900">{u.name}</p></TD>
                <TD><code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{u.symbol || u.name}</code></TD>
                <TD className="text-slate-600">{u.decimal_places}</TD>
                <TD className="text-slate-500 capitalize">{u.unit_type}</TD>
                <TD><SyncBadge status={u.tally_sync_status} source={u.source} /></TD>
                <TD><SyncBadge status={u.tally_sync_status} /></TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(u)} deleteDisabled={u.tally_sync_status === 'delete_pending'} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon={Scale}
                    title="No units yet"
                    desc="Create units of measure to use in your inventory (Nos, Kg, Ltr…)"
                    action={<Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5"><Plus className="w-4 h-4" /> Add Unit</Button>}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Unit" wasSynced={['synced', 'finpilot', 'delete_failed'].includes(deleting.tally_sync_status)}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={deleteLoading} />
      )}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Unit of Measure</DialogTitle></DialogHeader>
          <UnitForm onClose={() => setShowForm(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Godowns sub-tab ──────────────────────────────────────────────────────────

function GodownsSubTab() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<TallyGodown | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['management-godowns', page, debouncedSearch],
    queryFn: () => managementApi.godowns({ page, page_size: 15, search: debouncedSearch || undefined }),
  });

  const handleDelete = async () => {
    if (!deleting) return;
    setDeleteLoading(true);
    try {
      const res = await managementApi.deleteGodown(deleting.id);
      if (res.status === 'pending') {
        toast({ title: 'Delete queued', description: 'Waiting for TallyPrime to confirm. The godown stays visible until then.', variant: 'default' });
      } else {
        toast({ title: 'Godown deleted', variant: 'success' });
      }
      qc.invalidateQueries({ queryKey: ['management-godowns'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });
    } catch { toast({ title: 'Delete failed', variant: 'destructive' }); }
    setDeleteLoading(false);
    setDeleting(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search godowns…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5 shrink-0">
          <Plus className="w-4 h-4" /> Add Godown
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr><TH>Godown Name</TH><TH>Parent</TH><TH>Source</TH><TH>Tally Sync</TH><TH>Last Synced</TH><TH>Actions</TH></tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i}><td colSpan={6} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((g: TallyGodown) => (
              <tr key={g.id} className="border-b border-slate-50 hover:bg-slate-50">
                <TD><p className="font-medium text-slate-900">{g.name}</p></TD>
                <TD className="text-slate-500">{g.parent || <span className="text-slate-300 italic">Root</span>}</TD>
                <TD><SyncBadge status={g.tally_sync_status} source={g.source} /></TD>
                <TD><SyncBadge status={g.tally_sync_status} /></TD>
                <TD className="text-slate-400 text-xs">{relTime(g.synced_at)}</TD>
                <TD><RowActions onEdit={() => {}} onDelete={() => setDeleting(g)} deleteDisabled={g.tally_sync_status === 'delete_pending'} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={Warehouse}
                    title="No godowns yet"
                    desc="Create a godown or warehouse location to use in TallyPrime."
                    action={<Button size="sm" onClick={() => setShowForm(true)} className="gap-1.5"><Plus className="w-4 h-4" /> Add Godown</Button>}
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
      {deleting && (
        <DeleteDialog name={deleting.name} entityLabel="Godown" wasSynced={['synced', 'finpilot', 'delete_failed'].includes(deleting.tally_sync_status)}
          onConfirm={handleDelete} onClose={() => setDeleting(null)} loading={deleteLoading} />
      )}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Create Godown / Warehouse</DialogTitle></DialogHeader>
          <GodownForm onClose={() => setShowForm(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── Masters Tab ──────────────────────────────────────────────────────────────

const MASTER_ICONS: Record<MasterTab, React.ElementType> = {
  Customers: Users, Vendors: Building2, Ledgers: BookOpen,
  Products: Package, 'Stock Groups': FolderOpen, Units: Scale, Godowns: Warehouse,
};

function MastersTab({ initialSub }: { initialSub?: MasterTab }) {
  const [sub, setSub] = useState<MasterTab>(initialSub || 'Customers');

  useEffect(() => {
    if (initialSub) setSub(initialSub);
  }, [initialSub]);

  const renderSub = () => {
    switch (sub) {
      case 'Customers': return <CustomersSubTab />;
      case 'Vendors': return <VendorsSubTab />;
      case 'Ledgers': return <LedgersSubTab />;
      case 'Products': return <ProductsSubTab />;
      case 'Stock Groups': return <StockGroupsSubTab />;
      case 'Units': return <UnitsSubTab />;
      case 'Godowns': return <GodownsSubTab />;
    }
  };

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-lg overflow-x-auto">
        {MASTER_TABS.map(t => {
          const Icon = MASTER_ICONS[t];
          return (
            <button
              key={t}
              onClick={() => setSub(t)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-all",
                sub === t
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {t}
            </button>
          );
        })}
      </div>

      {renderSub()}
    </div>
  );
}


// ─── Transactions Tab ─────────────────────────────────────────────────────────

const VOUCHER_TYPE_LABELS: Record<string, string> = {
  ALL: 'All', SALES: 'Sales', PURCHASE: 'Purchase', EXPENSE: 'Expenses',
};

const VOUCHER_TYPE_BADGE: Record<string, string> = {
  SALES: 'bg-indigo-100 text-indigo-700',
  PURCHASE: 'bg-orange-100 text-orange-700',
  EXPENSE: 'bg-purple-100 text-purple-700',
  INVOICE: 'bg-indigo-100 text-indigo-700',
};

function TransactionsTab() {
  const [vtype, setVtype] = useState<string>('ALL');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ['management-vouchers', vtype, page, debouncedSearch, dateFrom, dateTo],
    queryFn: () => managementApi.vouchers({
      page, page_size: 20,
      voucher_type: vtype === 'ALL' ? undefined : vtype,
      search: debouncedSearch || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    }),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg shrink-0">
          {VOUCHER_TYPES.map(t => (
            <button
              key={t}
              onClick={() => { setVtype(t); setPage(1); }}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium transition-all whitespace-nowrap",
                vtype === t ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-900"
              )}
            >
              {VOUCHER_TYPE_LABELS[t]}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input placeholder="Search…" className="pl-9" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        </div>
        <Input type="date" className="max-w-[160px]" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} />
        <Input type="date" className="max-w-[160px]" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} />
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-100">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-100">
            <tr>
              <TH>Voucher #</TH><TH>Date</TH><TH>Type</TH>
              <TH>Description</TH><TH right>Amount</TH>
              <TH>Status</TH><TH>Source</TH>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}><td colSpan={7} className="py-2 px-4"><Skeleton className="h-8" /></td></tr>
              ))
            ) : data?.items?.length ? data.items.map((v: VoucherItem) => (
              <tr key={`${v.entity_type}-${v.id}`} className="border-b border-slate-50 hover:bg-slate-50">
                <TD><p className="font-mono text-xs font-medium text-slate-700">{v.voucher_number}</p></TD>
                <TD className="text-slate-500">{v.date ? formatDate(v.date) : '—'}</TD>
                <TD>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${VOUCHER_TYPE_BADGE[v.voucher_type] ?? 'bg-slate-100 text-slate-600'}`}>
                    {v.voucher_type}
                  </span>
                </TD>
                <TD className="text-slate-600">{v.title || v.party || '—'}</TD>
                <TD right className="font-semibold text-slate-900">{formatCurrency(v.amount)}</TD>
                <TD>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    v.status === 'APPROVED' || v.status === 'PAID' ? 'bg-emerald-100 text-emerald-700' :
                    v.status === 'PENDING_APPROVAL' ? 'bg-amber-100 text-amber-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>{v.status}</span>
                </TD>
                <TD><SyncBadge status={v.tally_sync_status} source={v.source} /></TD>
              </tr>
            )) : (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon={FileText}
                    title={vtype === 'ALL' ? 'No transactions yet' : `No ${VOUCHER_TYPE_LABELS[vtype]} transactions`}
                    desc="Transactions created in FinPilot or synced from TallyPrime appear here."
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Paginator page={page} totalPages={data?.total_pages ?? 1} onPage={setPage} />
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ManagementPage() {
  const navigate = useNavigate();
  const [mainTab, setMainTab] = useState<MainTab>('Overview');
  const [masterSub, setMasterSub] = useState<MasterTab | undefined>(undefined);

  const navigateTo = useCallback((tab: MainTab, sub?: MasterTab) => {
    setMainTab(tab);
    if (sub) setMasterSub(sub);
  }, []);

  const MAIN_TAB_ICONS: Record<MainTab, React.ElementType> = {
    Overview: BarChart3, Masters: Database, Transactions: FileText,
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Management</h2>
        <p className="text-sm text-slate-500">Unified view of masters and transactions. For sync and connector details, visit TallyPrime.</p>
      </div>

      {/* Main tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex gap-0 -mb-px">
          {MAIN_TABS.map(tab => {
            const Icon = MAIN_TAB_ICONS[tab];
            return (
              <button
                key={tab}
                onClick={() => setMainTab(tab)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                  mainTab === tab
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
                )}
              >
                <Icon className="w-4 h-4" />
                {tab}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {mainTab === 'Overview' && <OverviewTab onNavigate={navigateTo} onGoTally={() => navigate('/tally')} />}
        {mainTab === 'Masters' && <MastersTab initialSub={masterSub} />}
        {mainTab === 'Transactions' && <TransactionsTab />}
      </div>
    </div>
  );
}
