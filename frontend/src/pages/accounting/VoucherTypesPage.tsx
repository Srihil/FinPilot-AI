import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Receipt, Plus, Search, Loader2, AlertCircle, Trash2, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
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

const BASE_TYPES = [
  'Sales', 'Purchase', 'Receipt', 'Payment',
  'Journal', 'Contra', 'Credit Note', 'Debit Note',
];

const BASE_TYPE_COLORS: Record<string, string> = {
  'Sales':       'bg-green-100 text-green-700',
  'Purchase':    'bg-orange-100 text-orange-700',
  'Receipt':     'bg-blue-100 text-blue-700',
  'Payment':     'bg-red-100 text-red-700',
  'Journal':     'bg-purple-100 text-purple-700',
  'Contra':      'bg-slate-100 text-slate-700',
  'Credit Note': 'bg-cyan-100 text-cyan-700',
  'Debit Note':  'bg-yellow-100 text-yellow-700',
};

export default function VoucherTypesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [deleteItem, setDeleteItem] = useState<{ id: string; name: string } | null>(null);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('Sales');
  const [formNumbering, setFormNumbering] = useState('Automatic');

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['voucher-types', search],
    queryFn: () => managementApi.voucherTypes({ page_size: 200, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => managementApi.createVoucherType({
      name: formName.trim(),
      parent: formParent,
      numbering_method: formNumbering,
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
    onSuccess: () => {
      toast({ title: 'Deleted' });
      qc.invalidateQueries({ queryKey: ['voucher-types'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' });
    },
  });

  // Group by parent type
  const grouped: Record<string, VoucherTypeItem[]> = {};
  (data?.items || []).forEach(vt => {
    const key = vt.parent || vt.name;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(vt);
  });

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Receipt className="w-6 h-6 text-indigo-600" />
            Voucher Types
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            All voucher types from TallyPrime — standard and custom
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </Button>
          <Button onClick={() => setShowCreate(true)} className="gap-2">
            <Plus className="w-4 h-4" /> New Custom Type
          </Button>
        </div>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input
          placeholder="Search voucher types…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : isError ? (
        <div className="flex items-center gap-2 p-6 text-red-600 bg-red-50 rounded-lg">
          <AlertCircle className="w-5 h-5" />
          <div>
            <p className="font-medium">Failed to load voucher types</p>
            <p className="text-sm text-red-500 mt-0.5">Run a full sync from TallyPrime → Sync Center to import voucher types.</p>
          </div>
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-16 text-slate-400 space-y-2">
          <Receipt className="w-10 h-10 mx-auto opacity-30" />
          <p className="font-medium">No voucher types found</p>
          <p className="text-sm">Go to <strong>TallyPrime → Sync Center → Sync</strong> to import all voucher types from TallyPrime.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b)).map(([parentName, types]) => (
            <div key={parentName}>
              <div className="flex items-center gap-2 mb-3">
                <span className={cn('px-2.5 py-1 rounded-full text-xs font-semibold', BASE_TYPE_COLORS[parentName] || 'bg-slate-100 text-slate-600')}>
                  {parentName}
                </span>
                <span className="text-xs text-slate-400">{types.length} type{types.length !== 1 ? 's' : ''}</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {types.map(vt => (
                  <Card key={vt.id} className="border hover:shadow-sm transition-shadow">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-slate-900 truncate">{vt.name}</p>
                          <p className="text-xs text-slate-400 mt-0.5">Numbering: {vt.numbering_method || 'Automatic'}</p>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <SyncBadge status={vt.tally_sync_status} source={vt.source} />
                          {vt.source === 'finpilot' && (
                            <button
                              onClick={() => setDeleteItem({ id: vt.id, name: vt.name })}
                              className="p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Custom Voucher Type</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name *</Label>
              <Input
                value={formName}
                onChange={e => setFormName(e.target.value)}
                placeholder="e.g. Tax Invoice, GST Sales, Retail Bill"
              />
              <p className="text-xs text-slate-400 mt-1">This name will appear in TallyPrime as a new voucher type.</p>
            </div>
            <div>
              <Label>Based on (Parent Type) *</Label>
              <select
                value={formParent}
                onChange={e => setFormParent(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                {BASE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <p className="text-xs text-slate-400 mt-1">The standard TallyPrime type this custom type is based on.</p>
            </div>
            <div>
              <Label>Voucher Numbering</Label>
              <select
                value={formNumbering}
                onChange={e => setFormNumbering(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                <option value="Automatic">Automatic</option>
                <option value="Manual">Manual</option>
                <option value="None">None</option>
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
          <DialogHeader><DialogTitle className="text-red-600">Delete Voucher Type</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-700">Delete <strong>{deleteItem?.name}</strong> from FinPilot?</p>
          <p className="text-xs text-slate-500 bg-slate-50 p-2 rounded">Note: This only removes it from FinPilot. Delete it in TallyPrime manually if needed.</p>
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
