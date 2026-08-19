import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FolderOpen, FolderClosed, Folder, Plus, Search, Loader2, AlertCircle,
  Pencil, Trash2, ChevronRight, ChevronDown, Square, CheckSquare,
} from 'lucide-react';
import { BulkDeleteBar } from '../../components/ui/BulkDeleteBar';
import { bulkDeleteApi } from '../../api/endpoints';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { groupsApi } from '../../api/endpoints';
import { cn } from '../../utils/cn';
import type { TallyGroup } from '../../types';

// ─── Tree types ───────────────────────────────────────────────────────────────

interface GroupNode extends TallyGroup {
  children: GroupNode[];
  depth: number;
}

type Row = { kind: 'group'; node: GroupNode; continues: boolean[] };

// ─── Tree connector prefix ────────────────────────────────────────────────────

function TreePrefix({ continues }: { continues: boolean[] }) {
  if (continues.length === 0) return null;
  const ancestors = continues.slice(0, -1);
  const isLast = !continues[continues.length - 1];
  return (
    <span className="font-mono text-slate-300 select-none whitespace-pre text-sm leading-none">
      {ancestors.map((c, i) => <span key={i}>{c ? '│  ' : '   '}</span>)}
      <span>{isLast ? '└─ ' : '├─ '}</span>
    </span>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const normalise = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');

function countDescendants(node: GroupNode): number {
  let n = node.children.length;
  for (const c of node.children) n += countDescendants(c);
  return n;
}

function buildTree(groups: TallyGroup[]): { roots: GroupNode[]; allIds: string[] } {
  const byName = new Map<string, GroupNode>();
  for (const g of groups) {
    const key = normalise(g.name);
    if (!byName.has(key))
      byName.set(key, { ...g, children: [], depth: 0 });
  }
  const roots: GroupNode[] = [];
  for (const node of byName.values()) {
    const pk = node.parent ? normalise(node.parent) : '';
    const parent = pk ? byName.get(pk) : null;
    if (parent) { node.depth = parent.depth + 1; parent.children.push(node); }
    else roots.push(node);
  }
  const sort = (ns: GroupNode[]) => {
    ns.sort((a, b) => a.name.localeCompare(b.name));
    ns.forEach(n => sort(n.children));
  };
  sort(roots);
  const allIds = [...byName.values()].map(n => n.id);
  return { roots, allIds };
}

function flattenToRows(roots: GroupNode[], collapsed: Set<string>, search: string): Row[] {
  const rows: Row[] = [];
  const expand = search.trim().length > 0;

  const walk = (node: GroupNode, parentContinues: boolean[]) => {
    rows.push({ kind: 'group', node, continues: parentContinues });
    if (!expand && collapsed.has(node.id)) return;
    const total = node.children.length;
    node.children.forEach((child, idx) => {
      walk(child, [...parentContinues, idx < total - 1]);
    });
  };

  roots.forEach(root => walk(root, []));
  return rows;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const PARENT_GROUPS = [
  'Capital Account', 'Current Assets', 'Current Liabilities', 'Fixed Assets',
  'Investments', 'Loans & Advances (Asset)', 'Loans (Liability)',
  'Direct Expenses', 'Indirect Expenses', 'Direct Incomes', 'Indirect Incomes',
  'Reserves & Surplus', 'Suspense Ac', 'Misc. Expenses (ASSET)', 'Branch / Divisions',
];

const NATURES = ['assets', 'liabilities', 'income', 'expenses'];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function GroupsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyGroup | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyGroup | null>(null);

  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [formNature, setFormNature] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const toggleSelect = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSelection = () => setSelectedIds(new Set());

  const { data, isLoading, isError } = useQuery({
    queryKey: ['groups-tree'],
    queryFn: () => groupsApi.list({ page_size: 200 }),
    refetchInterval: 5000,
  });

  const allGroups: TallyGroup[] = data?.items ?? [];

  const nodeIds = allGroups.map(g => g.id);
  const allNodesSelected = nodeIds.length > 0 && nodeIds.every(id => selectedIds.has(id));
  const toggleSelectAll = () => allNodesSelected
    ? setSelectedIds(prev => { const n = new Set(prev); nodeIds.forEach(id => n.delete(id)); return n; })
    : setSelectedIds(prev => new Set([...prev, ...nodeIds]));

  const filteredGroups = useMemo(() => {
    if (!search.trim()) return allGroups;
    const q = search.toLowerCase();
    return allGroups.filter(g =>
      g.name.toLowerCase().includes(q) ||
      (g.parent || '').toLowerCase().includes(q)
    );
  }, [allGroups, search]);

  const { roots, allIds } = useMemo(() => buildTree(filteredGroups), [filteredGroups]);

  // Collapse only root groups initially (children visible on expand)
  const { roots: allRoots, allIds: allAllIds } = useMemo(() => buildTree(allGroups), [allGroups]);

  useEffect(() => {
    if (!initialized && allRoots.length > 0) {
      // Collapse everything except roots
      const toCollapse = new Set<string>();
      const walkCollapse = (nodes: GroupNode[]) => {
        for (const n of nodes) {
          toCollapse.add(n.id);
          walkCollapse(n.children);
        }
      };
      walkCollapse(allRoots);
      setCollapsed(toCollapse);
      setInitialized(true);
    }
  }, [allRoots, initialized]);

  const rows = useMemo(() => flattenToRows(roots, collapsed, search), [roots, collapsed, search]);

  const toggle = (id: string) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const expandAll = () => setCollapsed(new Set());
  const collapseAll = () => {
    const ids = new Set<string>();
    const walk = (ns: GroupNode[]) => { for (const n of ns) { ids.add(n.id); walk(n.children); } };
    walk(allRoots);
    setCollapsed(ids);
  };

  // ── Mutations ─────────────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: () => groupsApi.create({ name: formName.trim(), parent: formParent || undefined, nature: formNature || undefined }),
    onSuccess: () => {
      toast({ title: 'Group created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['groups-tree'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: () => groupsApi.update(editItem!.id, { name: formName || undefined, parent: formParent || undefined, nature: formNature || undefined }),
    onSuccess: () => {
      toast({ title: 'Group updated' });
      qc.invalidateQueries({ queryKey: ['groups-tree'] });
      setEditItem(null); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Update failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => groupsApi.delete(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['groups-tree'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' }),
  });

  function resetForm() { setFormName(''); setFormParent(''); setFormNature(''); }
  function openEdit(g: TallyGroup) {
    setFormName(g.name); setFormParent(g.parent || ''); setFormNature(g.nature || '');
    setEditItem(g);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FolderOpen className="w-6 h-6 text-indigo-600" /> Account Groups
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {allGroups.length} group{allGroups.length !== 1 ? 's' : ''} · Group → Sub-group hierarchy
          </p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Group
        </Button>
      </div>

      {/* Search + controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search groups…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        {!search && (
          <div className="flex gap-2">
            <button onClick={expandAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Expand all</button>
            <button onClick={collapseAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Collapse all</button>
          </div>
        )}
        <button
          onClick={toggleSelectAll}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-700 px-2 py-1 rounded hover:bg-indigo-50 transition-colors"
        >
          {allNodesSelected ? <CheckSquare className="w-3.5 h-3.5 text-indigo-600" /> : <Square className="w-3.5 h-3.5" />}
          {allNodesSelected ? 'Deselect all' : `Select all (${nodeIds.length})`}
        </button>
      </div>

      {/* Tree */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-9 w-full" style={{ marginLeft: (i % 3) * 20 }} />)}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600">
              <AlertCircle className="w-5 h-5" /> Failed to load groups.
            </div>
          ) : rows.length === 0 ? (
            <div className="text-center py-14 text-slate-400">
              {search ? `No groups matching "${search}"` : 'No groups yet. Create one or sync from TallyPrime.'}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Hierarchy</th>
                  <th className="px-4 py-3 text-left w-28">Nature</th>
                  <th className="px-4 py-3 text-center w-24">Sync</th>
                  <th className="px-4 py-3 text-right w-20">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  const n = row.node;
                  const cId = n.id;
                  const isCol = collapsed.has(cId);
                  const hasChildren = n.children.length > 0;
                  const isRoot = row.continues.length === 0;
                  const desc = countDescendants(n);

                  return (
                    <tr
                      key={`${cId}-${i}`}
                      className={cn('border-b group', isRoot ? 'bg-indigo-50/40 hover:bg-indigo-50/60' : 'hover:bg-slate-50/80', hasChildren && 'cursor-pointer select-none')}
                      onClick={() => hasChildren && toggle(cId)}
                    >
                      <td className="px-3 py-2">
                        <div className="flex items-center">
                          <button onClick={e => { e.stopPropagation(); toggleSelect(cId); }} className="p-1 rounded shrink-0 text-slate-300 hover:text-indigo-600 transition-colors">
                            {selectedIds.has(cId) ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
                          </button>
                          <TreePrefix continues={row.continues} />
                          {hasChildren ? (
                            <button
                              className="p-0.5 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-100 shrink-0 pointer-events-none"
                            >
                              {isCol ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                            </button>
                          ) : <span className="w-5 shrink-0" />}
                          {hasChildren
                            ? (isCol
                              ? <FolderClosed className="w-4 h-4 text-indigo-500 shrink-0 ml-0.5" />
                              : <FolderOpen className="w-4 h-4 text-indigo-400 shrink-0 ml-0.5" />)
                            : <Folder className="w-4 h-4 text-slate-300 shrink-0 ml-0.5" />}
                          <span className={cn('ml-1.5 text-slate-800', isRoot ? 'font-bold' : 'font-medium text-sm')}>
                            {n.name}
                          </span>
                          {desc > 0 && (
                            <span className="ml-2 text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full font-semibold shrink-0">
                              {desc}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-500 capitalize">
                        {n.nature || <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <SyncBadge status={n.tally_sync_status} source={n.source} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className={cn('flex items-center justify-end gap-0.5', 'opacity-0 group-hover:opacity-100 transition-opacity')}>
                          <button onClick={() => openEdit(n)} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          {n.source !== 'tally_sync' && (
                            <button onClick={() => setDeleteItem(n)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
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

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Account Group</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name *</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. My Expenses" className="mt-1" />
            </div>
            <div>
              <Label>Parent Group</Label>
              <select value={formParent} onChange={e => setFormParent(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                <option value="">— None (root group) —</option>
                {PARENT_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Nature</Label>
              <select value={formNature} onChange={e => setFormNature(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
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
            <div>
              <Label>Name</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label>Parent Group</Label>
              <select value={formParent} onChange={e => setFormParent(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                <option value="">— None —</option>
                {PARENT_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Nature</Label>
              <select value={formNature} onChange={e => setFormNature(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
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

      <BulkDeleteBar
        selectedIds={selectedIds}
        entityLabel="group"
        queryKeys={[['groups-tree']]}
        onClear={clearSelection}
        onDelete={ids => bulkDeleteApi.masters('group', ids)}
      />
    </div>
  );
}
