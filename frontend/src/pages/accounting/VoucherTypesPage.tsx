import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Receipt, Plus, Search, Loader2, Trash2, RefreshCw,
  ShoppingCart, ArrowDownLeft, ArrowUpRight, CreditCard,
  Banknote, BookOpen, ArrowLeftRight, Package, Truck,
  ClipboardList, Users, RotateCcw, FileText, Wrench,
  AlertCircle,
} from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import type { VoucherTypeItem } from '../../types';
import { cn } from '../../utils/cn';

// ─── All 24 standard TallyPrime voucher types ─────────────────────────────────

interface VoucherTypeDef {
  name: string;
  shortcut?: string;
  description: string;
  category: string;
  icon: React.ElementType;
  color: string;
  badge: string;
}

const TALLY_VOUCHER_TYPES: VoucherTypeDef[] = [
  // ── Sales ──
  {
    name: 'Sales', shortcut: 'F8', category: 'Sales',
    description: 'Record a sale to a customer. Increases receivables.',
    icon: ShoppingCart, color: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-700',
  },
  {
    name: 'Sales Order', category: 'Sales',
    description: 'Customer order confirmation before goods are dispatched.',
    icon: ClipboardList, color: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-700',
  },
  {
    name: 'Credit Note', shortcut: 'Ctrl+F8', category: 'Sales',
    description: 'Sales return — reverse a sale when customer returns goods.',
    icon: ArrowDownLeft, color: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-700',
  },
  {
    name: 'Delivery Note', category: 'Sales',
    description: 'Record goods dispatched to customer before invoicing.',
    icon: Truck, color: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-700',
  },
  // ── Purchase ──
  {
    name: 'Purchase', shortcut: 'F9', category: 'Purchase',
    description: 'Record a purchase from a supplier. Increases payables.',
    icon: ArrowDownLeft, color: 'bg-orange-50 border-orange-200', badge: 'bg-orange-100 text-orange-700',
  },
  {
    name: 'Purchase Order', category: 'Purchase',
    description: 'Order placed with supplier before goods are received.',
    icon: ClipboardList, color: 'bg-orange-50 border-orange-200', badge: 'bg-orange-100 text-orange-700',
  },
  {
    name: 'Debit Note', shortcut: 'Ctrl+F9', category: 'Purchase',
    description: 'Purchase return — reverse a purchase when goods are returned to supplier.',
    icon: ArrowUpRight, color: 'bg-orange-50 border-orange-200', badge: 'bg-orange-100 text-orange-700',
  },
  {
    name: 'Receipt Note', category: 'Purchase',
    description: 'Record goods received from supplier before bill is entered.',
    icon: Package, color: 'bg-orange-50 border-orange-200', badge: 'bg-orange-100 text-orange-700',
  },
  // ── Banking ──
  {
    name: 'Receipt', shortcut: 'F6', category: 'Banking',
    description: 'Money received from customer into bank or cash account.',
    icon: Banknote, color: 'bg-blue-50 border-blue-200', badge: 'bg-blue-100 text-blue-700',
  },
  {
    name: 'Payment', shortcut: 'F5', category: 'Banking',
    description: 'Money paid out — to supplier, employee, or for expenses.',
    icon: CreditCard, color: 'bg-blue-50 border-blue-200', badge: 'bg-blue-100 text-blue-700',
  },
  {
    name: 'Contra', shortcut: 'F4', category: 'Banking',
    description: 'Transfer between your own cash and bank accounts.',
    icon: ArrowLeftRight, color: 'bg-blue-50 border-blue-200', badge: 'bg-blue-100 text-blue-700',
  },
  // ── Journal ──
  {
    name: 'Journal', shortcut: 'F7', category: 'Journal',
    description: 'Internal adjustment between ledgers — no cash movement.',
    icon: BookOpen, color: 'bg-purple-50 border-purple-200', badge: 'bg-purple-100 text-purple-700',
  },
  {
    name: 'Reversing Journal', category: 'Journal',
    description: 'Auto-reverses on a future date — used for provisional entries.',
    icon: RotateCcw, color: 'bg-purple-50 border-purple-200', badge: 'bg-purple-100 text-purple-700',
  },
  {
    name: 'Memorandum', category: 'Journal',
    description: 'Non-accounting entry for reference — does not affect books.',
    icon: FileText, color: 'bg-purple-50 border-purple-200', badge: 'bg-purple-100 text-purple-700',
  },
  // ── Inventory ──
  {
    name: 'Stock Journal', category: 'Inventory',
    description: 'Move stock between godowns or record manufacturing consumption.',
    icon: Package, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  {
    name: 'Physical Stock', category: 'Inventory',
    description: 'Record actual physical stock count to correct book stock.',
    icon: Package, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  {
    name: 'Material In', category: 'Inventory',
    description: 'Record raw material received for job work processing.',
    icon: ArrowDownLeft, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  {
    name: 'Material Out', category: 'Inventory',
    description: 'Record material sent out for job work or processing.',
    icon: ArrowUpRight, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  {
    name: 'Rejections In', category: 'Inventory',
    description: 'Record goods rejected and returned by customer.',
    icon: ArrowDownLeft, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  {
    name: 'Rejections Out', category: 'Inventory',
    description: 'Record goods rejected and returned to supplier.',
    icon: ArrowUpRight, color: 'bg-teal-50 border-teal-200', badge: 'bg-teal-100 text-teal-700',
  },
  // ── Job Work ──
  {
    name: 'Job Work In Order', category: 'Job Work',
    description: 'Order received from principal for job work to be done.',
    icon: Wrench, color: 'bg-yellow-50 border-yellow-200', badge: 'bg-yellow-100 text-yellow-700',
  },
  {
    name: 'Job Work Out Order', category: 'Job Work',
    description: 'Order placed with sub-contractor for job work.',
    icon: Wrench, color: 'bg-yellow-50 border-yellow-200', badge: 'bg-yellow-100 text-yellow-700',
  },
  // ── HR ──
  {
    name: 'Attendance', category: 'HR & Payroll',
    description: 'Record employee attendance and leave for payroll processing.',
    icon: Users, color: 'bg-pink-50 border-pink-200', badge: 'bg-pink-100 text-pink-700',
  },
  {
    name: 'Payroll', category: 'HR & Payroll',
    description: 'Process employee salary and wages payment.',
    icon: Users, color: 'bg-pink-50 border-pink-200', badge: 'bg-pink-100 text-pink-700',
  },
];

const CATEGORIES = ['Sales', 'Purchase', 'Banking', 'Journal', 'Inventory', 'Job Work', 'HR & Payroll'];

const CATEGORY_META: Record<string, { color: string; label: string }> = {
  'Sales':       { color: 'bg-green-100 text-green-800',  label: '💰 Sales' },
  'Purchase':    { color: 'bg-orange-100 text-orange-800', label: '🛒 Purchase' },
  'Banking':     { color: 'bg-blue-100 text-blue-800',    label: '🏦 Banking' },
  'Journal':     { color: 'bg-purple-100 text-purple-800', label: '📒 Journal' },
  'Inventory':   { color: 'bg-teal-100 text-teal-800',    label: '📦 Inventory' },
  'Job Work':    { color: 'bg-yellow-100 text-yellow-800', label: '🔧 Job Work' },
  'HR & Payroll':{ color: 'bg-pink-100 text-pink-800',    label: '👥 HR & Payroll' },
};

const BASE_TYPES = TALLY_VOUCHER_TYPES.map(t => t.name);

export default function VoucherTypesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<{ id: string; name: string } | null>(null);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('Sales');
  const [formNumbering, setFormNumbering] = useState('Automatic');

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['voucher-types'],
    queryFn: () => managementApi.voucherTypes({ page_size: 200 }),
  });

  const createMut = useMutation({
    mutationFn: () => managementApi.createVoucherType({
      name: formName.trim(), parent: formParent, numbering_method: formNumbering,
    }),
    onSuccess: () => {
      toast({ title: 'Voucher type created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['voucher-types'] });
      setShowCreate(false);
      setFormName(''); setFormParent('Sales'); setFormNumbering('Automatic');
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteVoucherType(deleteItem!.id),
    onSuccess: (res: { status: string; message: string }) => {
      if (res.status === 'pending') {
        toast({
          title: 'Delete sent to TallyPrime',
          description: res.message,
        });
      } else {
        toast({ title: 'Deleted', description: res.message });
      }
      qc.invalidateQueries({ queryKey: ['voucher-types'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' });
    },
  });

  // Build a map of synced types from DB
  const syncedMap = new Map<string, VoucherTypeItem>();
  (data?.items || []).forEach(item => syncedMap.set(item.name.toLowerCase(), item));

  // Custom types (created in FinPilot, not standard TallyPrime types)
  const customTypes = (data?.items || []).filter(
    item => !BASE_TYPES.some(b => b.toLowerCase() === item.name.toLowerCase())
  );

  // Filter standard types
  const filtered = TALLY_VOUCHER_TYPES.filter(vt => {
    const matchesSearch = !search || vt.name.toLowerCase().includes(search.toLowerCase()) ||
      vt.description.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !activeCategory || vt.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  const grouped = CATEGORIES.reduce<Record<string, VoucherTypeDef[]>>((acc, cat) => {
    const types = filtered.filter(v => v.category === cat);
    if (types.length > 0) acc[cat] = types;
    return acc;
  }, {});

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Receipt className="w-6 h-6 text-indigo-600" />
            Voucher Types
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            All 24 TallyPrime voucher types — sync to import them into your account
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </Button>
          <Button onClick={() => setShowCreate(true)} className="gap-1.5">
            <Plus className="w-4 h-4" /> New Custom Type
          </Button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-slate-900">24</p>
          <p className="text-xs text-slate-500 mt-0.5">TallyPrime Types</p>
        </div>
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-indigo-600">{syncedMap.size}</p>
          <p className="text-xs text-slate-500 mt-0.5">Synced to FinPilot</p>
        </div>
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-green-600">{customTypes.length}</p>
          <p className="text-xs text-slate-500 mt-0.5">Custom Types</p>
        </div>
        <div className="bg-white rounded-xl border p-4 text-center">
          <p className="text-2xl font-bold text-slate-700">7</p>
          <p className="text-xs text-slate-500 mt-0.5">Categories</p>
        </div>
      </div>

      {/* Search + Category filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search voucher types…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setActiveCategory(null)}
            className={cn(
              'px-3 py-1.5 rounded-full text-xs font-medium transition-all',
              !activeCategory ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            )}
          >
            All
          </button>
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-all',
                activeCategory === cat
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              )}
            >
              {CATEGORY_META[cat]?.label || cat}
            </button>
          ))}
        </div>
      </div>

      {/* Sync notice if none synced */}
      {!isLoading && syncedMap.size === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-800">Not yet synced from TallyPrime</p>
            <p className="text-xs text-amber-600 mt-0.5">
              Go to <strong>TallyPrime → Sync Center → Sync</strong> to import all your voucher types.
              Standard types are shown below for reference.
            </p>
          </div>
        </div>
      )}

      {/* Standard types grouped by category */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-xl" />)}
        </div>
      ) : isError ? (
        <div className="text-center py-10 text-red-500">Failed to load. Please refresh.</div>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([category, types]) => (
            <div key={category}>
              {/* Category header */}
              <div className="flex items-center gap-3 mb-4">
                <span className={cn('px-3 py-1 rounded-full text-xs font-semibold', CATEGORY_META[category]?.color)}>
                  {CATEGORY_META[category]?.label || category}
                </span>
                <div className="flex-1 h-px bg-slate-100" />
                <span className="text-xs text-slate-400">{types.length} type{types.length !== 1 ? 's' : ''}</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {types.map(vt => {
                  const Icon = vt.icon;
                  const synced = syncedMap.get(vt.name.toLowerCase());
                  return (
                    <div
                      key={vt.name}
                      className={cn(
                        'rounded-xl border p-4 space-y-3 transition-all hover:shadow-md hover:-translate-y-0.5',
                        vt.color
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className={cn('p-1.5 rounded-lg', vt.badge.replace('text-', 'bg-').split(' ')[0] + '/20')}>
                            <Icon className={cn('w-4 h-4', vt.badge.split(' ')[1])} />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-900 text-sm leading-tight">{vt.name}</p>
                            {vt.shortcut && (
                              <span className="text-xs font-mono text-slate-400">{vt.shortcut}</span>
                            )}
                          </div>
                        </div>
                        {synced ? (
                          <SyncBadge status={synced.tally_sync_status} source={synced.source} />
                        ) : (
                          <span className="text-xs bg-white/70 text-slate-400 px-1.5 py-0.5 rounded border border-slate-200">
                            Not synced
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-600 leading-relaxed">{vt.description}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {/* Custom types section */}
          {customTypes.length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800">
                  ✨ Custom Types
                </span>
                <div className="flex-1 h-px bg-slate-100" />
                <span className="text-xs text-slate-400">{customTypes.length} custom</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {customTypes.map(vt => (
                  <div
                    key={vt.id}
                    className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 space-y-3 hover:shadow-md transition-all"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-slate-900 text-sm">{vt.name}</p>
                        {vt.parent && (
                          <p className="text-xs text-indigo-500 mt-0.5">Based on {vt.parent}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        <SyncBadge status={vt.tally_sync_status} source={vt.source} />
                        {vt.tally_sync_status === 'delete_pending' ? (
                          <span className="text-xs text-orange-600 bg-orange-50 px-2 py-0.5 rounded">
                            Deleting…
                          </span>
                        ) : (
                          <button
                            onClick={() => setDeleteItem({ id: vt.id, name: vt.name })}
                            className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">
                      Numbering: {vt.numbering_method || 'Automatic'}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus className="w-4 h-4 text-indigo-600" /> New Custom Voucher Type
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name *</Label>
              <Input
                value={formName}
                onChange={e => setFormName(e.target.value)}
                placeholder="e.g. Tax Invoice, GST Bill, Retail Sale"
              />
              <p className="text-xs text-slate-400 mt-1">This name will appear in TallyPrime.</p>
            </div>
            <div>
              <Label>Based on (Parent Type) *</Label>
              <select
                value={formParent}
                onChange={e => setFormParent(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                {TALLY_VOUCHER_TYPES.map(t => (
                  <option key={t.name} value={t.name}>{t.name} — {t.category}</option>
                ))}
              </select>
              <p className="text-xs text-slate-400 mt-1">
                Your custom type inherits the behaviour of this standard type.
              </p>
            </div>
            <div>
              <Label>Voucher Numbering</Label>
              <select
                value={formNumbering}
                onChange={e => setFormNumbering(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                <option value="Automatic">Automatic — Tally numbers them in sequence</option>
                <option value="Manual">Manual — You enter the number each time</option>
                <option value="None">None — No voucher number</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create & Sync to Tally
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="text-red-600">Delete Custom Type</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-700">Delete <strong>{deleteItem?.name}</strong>?</p>
          <p className="text-xs text-slate-600 bg-amber-50 border border-amber-200 p-2 rounded mt-2">
            This will first delete it from <strong>TallyPrime</strong>, then remove it from FinPilot once confirmed.
            You do not need to do anything manually in TallyPrime.
          </p>
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
