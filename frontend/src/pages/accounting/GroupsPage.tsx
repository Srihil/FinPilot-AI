import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FolderOpen, Plus, Search, Loader2, AlertCircle, Pencil, Trash2,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { groupsApi } from '../../api/endpoints';
import type { TallyGroup } from '../../types';

const PARENT_GROUPS = [
  'Capital Account', 'Current Assets', 'Current Liabilities', 'Fixed Assets',
  'Investments', 'Loans & Advances (Asset)', 'Loans (Liability)',
  'Direct Expenses', 'Indirect Expenses', 'Direct Incomes', 'Indirect Incomes',
  'Reserves & Surplus', 'Suspense Ac', 'Misc. Expenses (ASSET)', 'Branch / Divisions',
];

const NATURES = ['assets', 'liabilities', 'income', 'expenses'];

export default function GroupsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyGroup | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyGroup | null>(null);

  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [formNature, setFormNature] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['groups', page, search],
    queryFn: () => groupsApi.list({ page, page_size: 20, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => groupsApi.create({ name: formName.trim(), parent: formParent || undefined, nature: formNature || undefined }),
    onSuccess: () => {
      toast({ title: 'Group created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['groups'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const updateMut = useMutation({
    mutationFn: () => groupsApi.update(editItem!.id, { name: formName || undefined, parent: formParent || undefined, nature: formNature || undefined }),
    onSuccess: () => {
      toast({ title: 'Group updated' });
      qc.invalidateQueries({ queryKey: ['groups'] });
      setEditItem(null); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Update failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => groupsApi.delete(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['groups'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' });
    },
  });

  function resetForm() { setFormName(''); setFormParent(''); setFormNature(''); }

  function openEdit(g: TallyGroup) {
    setFormName(g.name);
    setFormParent(g.parent || '');
    setFormNature(g.nature || '');
    setEditItem(g);
  }

  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FolderOpen className="w-6 h-6 text-indigo-600" /> Account Groups
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Accounting groups in TallyPrime (Sundry Debtors, Capital Account, etc.)</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Group
        </Button>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
        <Input placeholder="Search groups…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load groups.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">Parent</th>
                  <th className="px-4 py-3 text-left">Nature</th>
                  <th className="px-4 py-3 text-center">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length === 0 ? (
                  <tr><td colSpan={5} className="text-center py-10 text-slate-400">No groups found. Create one or sync from TallyPrime.</td></tr>
                ) : data?.items.map(g => (
                  <tr key={g.id} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-800">{g.name}</td>
                    <td className="px-4 py-3 text-slate-500">{g.parent || '—'}</td>
                    <td className="px-4 py-3 text-slate-500 capitalize">{g.nature || '—'}</td>
                    <td className="px-4 py-3 text-center"><SyncBadge status={g.tally_sync_status} source={g.source} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openEdit(g)} className="p-1.5 rounded hover:bg-slate-100 text-slate-500">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        {g.source !== 'tally_sync' && (
                          <button onClick={() => setDeleteItem(g)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
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
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Account Group</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name *</Label><Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. My Expenses" /></div>
            <div>
              <Label>Parent Group</Label>
              <select value={formParent} onChange={e => setFormParent(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm">
                <option value="">— None (root group) —</option>
                {PARENT_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Nature</Label>
              <select value={formNature} onChange={e => setFormNature(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm">
                <option value="">— Not specified —</option>
                {NATURES.map(n => <option key={n} value={n} className="capitalize">{n}</option>)}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />} Create Group
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Edit Group</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div><Label>Name</Label><Input value={formName} onChange={e => setFormName(e.target.value)} /></div>
            <div>
              <Label>Parent Group</Label>
              <select value={formParent} onChange={e => setFormParent(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm">
                <option value="">— None —</option>
                {PARENT_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Nature</Label>
              <select value={formNature} onChange={e => setFormNature(e.target.value)} className="w-full border rounded-md px-3 py-2 text-sm">
                <option value="">— Not specified —</option>
                {NATURES.map(n => <option key={n} value={n} className="capitalize">{n}</option>)}
              </select>
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
          <DialogHeader><DialogTitle className="text-red-600">Delete Group</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-700">Delete <strong>{deleteItem?.name}</strong>? This cannot be undone.</p>
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
