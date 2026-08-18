import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen, Plus, Search, Loader2, AlertCircle, Pencil, Trash2, X,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import { formatCurrency } from '../../utils/format';
import type { TallyLedger } from '../../types';

const TALLY_GROUPS = [
  'Sundry Debtors', 'Sundry Creditors', 'Bank Accounts', 'Cash-in-Hand',
  'Capital Account', 'Current Assets', 'Current Liabilities', 'Fixed Assets',
  'Sales Accounts', 'Purchase Accounts', 'Direct Expenses', 'Indirect Expenses',
  'Direct Incomes', 'Indirect Incomes', 'Loans & Advances (Asset)',
  'Loans (Liability)', 'Duties & Taxes', 'Provisions',
];

export default function LedgersPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyLedger | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyLedger | null>(null);

  const [formName, setFormName] = useState('');
  const [formGroup, setFormGroup] = useState('Sundry Debtors');
  const [formBalance, setFormBalance] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ledgers', page, search],
    queryFn: () => managementApi.ledgers({ page, page_size: PAGE_SIZE, search: search || undefined }),
    refetchInterval: 5000,
  });

  const createMut = useMutation({
    mutationFn: () => managementApi.createLedger({
      name: formName.trim(),
      parent_group: formGroup,
      opening_balance: formBalance ? parseFloat(formBalance) : 0,
    }),
    onSuccess: () => {
      toast({ title: 'Ledger created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['ledgers'] });
      setShowCreate(false);
      resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed to create ledger', variant: 'destructive' });
    },
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateLedger(editItem!.id, {
      name: formName.trim() || undefined,
      parent_group: formGroup || undefined,
      opening_balance: formBalance ? parseFloat(formBalance) : undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Ledger updated' });
      qc.invalidateQueries({ queryKey: ['ledgers'] });
      setEditItem(null);
      resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Update failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteLedger(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['ledgers'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' });
    },
  });

  function resetForm() {
    setFormName(''); setFormGroup('Sundry Debtors'); setFormBalance('');
  }

  function openEdit(l: TallyLedger) {
    setFormName(l.name);
    setFormGroup(l.parent_group || 'Sundry Debtors');
    setFormBalance(l.opening_balance ? String(l.opening_balance) : '');
    setEditItem(l);
  }

  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-indigo-600" />
            Ledgers
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Accounting ledgers synced with TallyPrime</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Ledger
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input
          placeholder="Search ledgers…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          className="pl-9"
        />
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600">
              <AlertCircle className="w-5 h-5" /> Failed to load ledgers.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">Parent Group</th>
                  <th className="px-4 py-3 text-right">Opening Balance</th>
                  <th className="px-4 py-3 text-center">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-10 text-slate-400">
                      No ledgers found. Create one or sync from TallyPrime.
                    </td>
                  </tr>
                ) : (
                  data?.items.map(l => (
                    <tr key={l.id} className="border-b hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-800">{l.name}</td>
                      <td className="px-4 py-3 text-slate-500">{l.parent_group || '—'}</td>
                      <td className="px-4 py-3 text-right">{formatCurrency(l.opening_balance)}</td>
                      <td className="px-4 py-3 text-center">
                        <SyncBadge status={l.tally_sync_status} source={l.source} />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openEdit(l)}
                            className="p-1.5 rounded hover:bg-slate-100 text-slate-500 hover:text-slate-800"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => setDeleteItem(l)}
                            className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
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
          <DialogHeader><DialogTitle>New Ledger</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name *</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. HDFC Bank" />
            </div>
            <div>
              <Label>Parent Group *</Label>
              <select
                value={formGroup}
                onChange={e => setFormGroup(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                {TALLY_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Opening Balance</Label>
              <Input type="number" value={formBalance} onChange={e => setFormBalance(e.target.value)} placeholder="0" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Create Ledger
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Ledger</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} />
            </div>
            <div>
              <Label>Parent Group</Label>
              <select
                value={formGroup}
                onChange={e => setFormGroup(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm"
              >
                {TALLY_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Opening Balance</Label>
              <Input type="number" value={formBalance} onChange={e => setFormBalance(e.target.value)} />
            </div>
            {editItem?.tally_sync_status === 'synced' && (
              <p className="text-xs text-amber-600 bg-amber-50 p-2 rounded">
                This ledger is synced to TallyPrime. Changes here won't automatically update Tally — edit there too.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-600">
              <Trash2 className="w-4 h-4" /> Delete Ledger
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-slate-700">
              Are you sure you want to delete <strong>{deleteItem?.name}</strong>?
            </p>
            {deleteItem?.tally_sync_status === 'synced' && (
              <p className="text-xs bg-amber-50 border border-amber-200 p-3 rounded text-amber-700">
                This ledger is synced to TallyPrime. A delete job will be queued and the ledger will be
                removed from FinPilot only after TallyPrime confirms deletion.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteItem(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
