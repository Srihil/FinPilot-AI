import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Tag, Plus, Search, Loader2, AlertCircle,
  Pencil, Trash2, ChevronRight, ChevronDown,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import { managementApi } from '../../api/endpoints';
import { cn } from '../../utils/cn';
import type { StockCategory } from '../../types';

// ─── Tree helpers ─────────────────────────────────────────────────────────────

interface TreeNode extends StockCategory {
  children: TreeNode[];
  depth: number;
}

function buildTree(cats: StockCategory[]): TreeNode[] {
  const byName = new Map<string, TreeNode>();
  for (const c of cats) {
    byName.set(c.name.toLowerCase(), { ...c, children: [], depth: 0 });
  }
  const roots: TreeNode[] = [];
  for (const c of cats) {
    const node = byName.get(c.name.toLowerCase())!;
    const parentKey = (c.parent || '').toLowerCase();
    const parentNode = parentKey ? byName.get(parentKey) : null;
    if (parentNode) {
      node.depth = parentNode.depth + 1;
      parentNode.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach(n => sort(n.children));
  };
  sort(roots);
  return roots;
}

function flattenVisible(nodes: TreeNode[], collapsed: Set<string>): TreeNode[] {
  const result: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      result.push(n);
      if (!collapsed.has(n.id) && n.children.length > 0) walk(n.children);
    }
  };
  walk(nodes);
  return result;
}

// ─── Row ─────────────────────────────────────────────────────────────────────

interface RowProps {
  node: TreeNode;
  collapsed: Set<string>;
  onToggle: (id: string) => void;
  onEdit: (c: StockCategory) => void;
  onDelete: (c: StockCategory) => void;
}

function CategoryRow({ node, collapsed, onToggle, onEdit, onDelete }: RowProps) {
  const hasChildren = node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);

  return (
    <tr className="border-b hover:bg-slate-50 group">
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-1" style={{ paddingLeft: node.depth * 20 }}>
          {node.depth > 0 && (
            <span className="text-slate-300 select-none mr-0.5">└</span>
          )}
          {hasChildren ? (
            <button
              onClick={() => onToggle(node.id)}
              className="p-0.5 rounded text-slate-400 hover:text-violet-600 hover:bg-violet-50 transition-colors"
            >
              {isCollapsed
                ? <ChevronRight className="w-3.5 h-3.5" />
                : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          ) : (
            <span className="w-5 inline-block" />
          )}
          <Tag className={cn(
            'w-3.5 h-3.5 shrink-0',
            hasChildren ? 'text-violet-500' : 'text-slate-300',
          )} />
          <span className="ml-1.5 font-medium text-sm text-slate-800">{node.name}</span>
          {hasChildren && (
            <span className="ml-2 text-xs text-slate-400">({node.children.length})</span>
          )}
        </div>
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-500">
        {node.parent || <span className="text-slate-300">root</span>}
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-400 max-w-xs truncate">
        {node.description || <span className="text-slate-300">—</span>}
      </td>
      <td className="px-4 py-2.5 text-center">
        <SyncBadge status={node.tally_sync_status} source={node.source} />
      </td>
      <td className="px-4 py-2.5 text-right">
        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onEdit(node)}
            className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700"
            title="Edit"
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onDelete(node)}
            className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StockCategoriesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<StockCategory | null>(null);
  const [deleteItem, setDeleteItem] = useState<StockCategory | null>(null);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [formDesc, setFormDesc] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-categories-tree'],
    queryFn: () => managementApi.stockCategories({ page_size: 500 }),
  });

  const allCats: StockCategory[] = data?.items ?? [];

  const tree = useMemo(() => buildTree(allCats), [allCats]);

  const filteredTree = useMemo(() => {
    if (!search.trim()) return tree;
    const q = search.toLowerCase();
    const matches = allCats.filter(c =>
      c.name.toLowerCase().includes(q) ||
      (c.parent || '').toLowerCase().includes(q) ||
      (c.description || '').toLowerCase().includes(q)
    );
    return buildTree(matches);
  }, [tree, search, allCats]);

  const visible = useMemo(
    () => flattenVisible(filteredTree, search ? new Set() : collapsed),
    [filteredTree, collapsed, search]
  );

  const toggleCollapse = (id: string) => {
    setCollapsed(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const expandAll = () => setCollapsed(new Set());
  const collapseAll = () => setCollapsed(new Set(
    allCats.filter(c => allCats.some(ch => ch.parent?.toLowerCase() === c.name.toLowerCase())).map(c => c.id)
  ));

  const createMut = useMutation({
    mutationFn: () => managementApi.createStockCategory({
      name: formName.trim(), parent: formParent || undefined, description: formDesc || undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Category created' });
      qc.invalidateQueries({ queryKey: ['stock-categories'] });
      qc.invalidateQueries({ queryKey: ['stock-categories-tree'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateStockCategory(editItem!.id, {
      name: formName || undefined, parent: formParent || undefined, description: formDesc || undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Updated' });
      qc.invalidateQueries({ queryKey: ['stock-categories'] });
      qc.invalidateQueries({ queryKey: ['stock-categories-tree'] });
      setEditItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteStockCategory(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['stock-categories'] });
      qc.invalidateQueries({ queryKey: ['stock-categories-tree'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  function resetForm() { setFormName(''); setFormParent(''); setFormDesc(''); }
  function openEdit(c: StockCategory) {
    setFormName(c.name); setFormParent(c.parent || ''); setFormDesc(c.description || '');
    setEditItem(c);
  }

  const parentOptions = allCats.map(c => c.name);

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Tag className="w-6 h-6 text-violet-600" /> Stock Categories
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {allCats.length} categor{allCats.length !== 1 ? 'ies' : 'y'} — local classification for stock items
          </p>
        </div>
        <Button
          onClick={() => { resetForm(); setShowCreate(true); }}
          className="gap-2 bg-violet-600 hover:bg-violet-700"
        >
          <Plus className="w-4 h-4" /> New Category
        </Button>
      </div>

      {/* Search + tree controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search categories…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        {!search && allCats.length > 0 && (
          <div className="flex gap-2">
            <button onClick={expandAll} className="text-xs text-slate-500 hover:text-violet-600 px-2 py-1 rounded hover:bg-slate-100">
              Expand all
            </button>
            <button onClick={collapseAll} className="text-xs text-slate-500 hover:text-violet-600 px-2 py-1 rounded hover:bg-slate-100">
              Collapse all
            </button>
          </div>
        )}
      </div>

      {/* Tree table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" style={{ marginLeft: (i % 3) * 20 }} />
              ))}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600">
              <AlertCircle className="w-5 h-5" /> Failed to load stock categories.
            </div>
          ) : visible.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              {search
                ? `No categories matching "${search}"`
                : 'No categories yet. Create one to start classifying stock items.'}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">Parent</th>
                  <th className="px-4 py-3 text-left">Description</th>
                  <th className="px-4 py-3 text-center">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(node => (
                  <CategoryRow
                    key={node.id}
                    node={node}
                    collapsed={collapsed}
                    onToggle={toggleCollapse}
                    onEdit={openEdit}
                    onDelete={c => setDeleteItem(c)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader><DialogTitle>New Stock Category</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. Smartphones" className="mt-1" />
            </div>
            <div>
              <Label>Parent Category <span className="text-slate-400 text-xs">(leave empty for root)</span></Label>
              <Combobox
                options={parentOptions}
                value={formParent}
                onChange={setFormParent}
                placeholder="Search categories…"
                clearLabel="— Leave empty (root level)"
                className="mt-1"
              />
              {formParent && (
                <p className="text-xs text-violet-600 mt-1">
                  Will be created under: <strong>{formParent}</strong>
                </p>
              )}
            </div>
            <div>
              <Label>Description</Label>
              <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} placeholder="Optional description" className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={!formName.trim() || createMut.isPending}
              className="bg-violet-600 hover:bg-violet-700"
            >
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader><DialogTitle>Edit Category</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label>Parent Category</Label>
              <Combobox
                options={parentOptions.filter(n => n !== editItem?.name)}
                value={formParent}
                onChange={setFormParent}
                placeholder="Search or leave empty for root…"
                clearLabel="— Leave empty (root level)"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Description</Label>
              <Input value={formDesc} onChange={e => setFormDesc(e.target.value)} className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle className="text-red-600">Delete Category</DialogTitle></DialogHeader>
          <p className="text-sm">
            Delete <strong>{deleteItem?.name}</strong>? This will also remove it from TallyPrime.
            {deleteItem && allCats.some(c => c.parent?.toLowerCase() === deleteItem.name.toLowerCase()) && (
              <span className="block mt-2 text-amber-600 text-xs">
                ⚠ This category has sub-categories. Remove them first.
              </span>
            )}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteItem(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
              {deleteMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
