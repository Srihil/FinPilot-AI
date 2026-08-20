import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FolderOpen, FolderClosed, Plus, Search, Loader2, AlertCircle,
  Pencil, Trash2, ChevronRight, ChevronDown, Folder, Square, CheckSquare, Download,
} from 'lucide-react';
import { ExportDialog } from '../../components/ui/ExportDialog';
import { downloadExport } from '../../api/endpoints';
import type { ExportFormat } from '../../api/endpoints';
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
import { managementApi } from '../../api/endpoints';
import { cn } from '../../utils/cn';
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import type { TallyStockGroup } from '../../types';

// ─── Tree helpers ─────────────────────────────────────────────────────────────

interface TreeNode extends TallyStockGroup {
  children: TreeNode[];
  depth: number;
}

function buildTree(groups: TallyStockGroup[]): TreeNode[] {
  const byName = new Map<string, TreeNode>();
  // First pass — create all nodes
  for (const g of groups) {
    byName.set(g.name.toLowerCase(), { ...g, children: [], depth: 0 });
  }
  const roots: TreeNode[] = [];
  // Second pass — attach children
  for (const g of groups) {
    const node = byName.get(g.name.toLowerCase())!;
    const parentKey = (g.parent || '').toLowerCase();
    const parentNode = parentKey ? byName.get(parentKey) : null;
    if (parentNode) {
      node.depth = parentNode.depth + 1;
      parentNode.children.push(node);
    } else {
      roots.push(node);
    }
  }
  // Sort children alphabetically at every level
  const sortNodes = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach(n => sortNodes(n.children));
  };
  sortNodes(roots);
  return roots;
}

function flattenVisible(nodes: TreeNode[], collapsed: Set<string>): TreeNode[] {
  const result: TreeNode[] = [];
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      result.push(n);
      if (!collapsed.has(n.id) && n.children.length > 0) {
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return result;
}

// ─── Row component ────────────────────────────────────────────────────────────

interface RowProps {
  node: TreeNode;
  collapsed: Set<string>;
  onToggle: (id: string) => void;
  onEdit: (g: TallyStockGroup) => void;
  onDelete: (g: TallyStockGroup) => void;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
}

function GroupRow({ node, collapsed, onToggle, onEdit, onDelete, selectedIds, onToggleSelect }: RowProps) {
  const hasChildren = node.children.length > 0;
  const isCollapsed = collapsed.has(node.id);

  return (
    <tr className={cn('border-b hover:bg-slate-50 group', hasChildren && 'cursor-pointer select-none')} onClick={() => hasChildren && onToggle(node.id)}>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-1" style={{ paddingLeft: node.depth * 20 }}>
          <button onClick={e => { e.stopPropagation(); onToggleSelect(node.id); }} className="p-1 rounded shrink-0 text-slate-300 hover:text-indigo-600 transition-colors">
            {selectedIds.has(node.id) ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
          </button>
          {/* Tree line indicator */}
          {node.depth > 0 && (
            <span className="text-slate-300 select-none mr-0.5">
              {'└'}
            </span>
          )}
          {/* Expand / collapse toggle */}
          {hasChildren ? (
            <button
              className="p-0.5 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors pointer-events-none"
            >
              {isCollapsed
                ? <ChevronRight className="w-3.5 h-3.5" />
                : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          ) : (
            <span className="w-5 inline-block" />
          )}
          {/* Folder icon */}
          {hasChildren
            ? (isCollapsed
              ? <FolderClosed className="w-4 h-4 text-amber-500 shrink-0" />
              : <FolderOpen className="w-4 h-4 text-amber-400 shrink-0" />)
            : <Folder className="w-4 h-4 text-slate-300 shrink-0" />}
          <span className="ml-1.5 font-medium text-sm text-slate-800">{node.name}</span>
          {hasChildren && (
            <span className="ml-2 text-xs text-slate-400">({node.children.length})</span>
          )}
        </div>
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-500">{node.parent || <span className="text-slate-300">root</span>}</td>
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

export default function StockGroupsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyStockGroup | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyStockGroup | null>(null);
  const [formName, setFormName] = useState('');
  const [formParent, setFormParent] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showExport, setShowExport] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const toggleSelect = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSelection = () => setSelectedIds(new Set());

  // Load all groups — no pagination for tree view
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-groups-tree'],
    queryFn: () => managementApi.stockGroups({ page_size: 500 }),
    refetchInterval: 5000,
  });

  const allGroups: TallyStockGroup[] = data?.items ?? [];

  const nodeIds = allGroups.map(g => g.id);
  const allNodesSelected = nodeIds.length > 0 && nodeIds.every(id => selectedIds.has(id));
  const toggleSelectAll = () => allNodesSelected
    ? setSelectedIds(prev => { const n = new Set(prev); nodeIds.forEach(id => n.delete(id)); return n; })
    : setSelectedIds(prev => new Set([...prev, ...nodeIds]));

  // Build tree and filter
  const tree = useMemo(() => buildTree(allGroups), [allGroups]);

  const filteredTree = useMemo(() => {
    if (!search.trim()) return tree;
    const q = search.toLowerCase();
    // When searching, flatten and show only matches (no tree collapse)
    const matches = allGroups.filter(g =>
      g.name.toLowerCase().includes(q) || (g.parent || '').toLowerCase().includes(q)
    );
    return buildTree(matches);
  }, [tree, search, allGroups]);

  const visible = useMemo(() =>
    flattenVisible(filteredTree, search ? new Set() : collapsed),
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
  const collapseAll = () => setCollapsed(new Set(allGroups.filter(g =>
    allGroups.some(c => c.parent?.toLowerCase() === g.name.toLowerCase())
  ).map(g => g.id)));

  const createMut = useMutation({
    mutationFn: () => managementApi.createStockGroup({ name: formName.trim(), parent: formParent || undefined }),
    onSuccess: () => {
      toast({ title: 'Created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['stock-groups-tree'] });
      qc.invalidateQueries({ queryKey: ['stock-groups-all'] });
      setShowCreate(false); setFormName(''); setFormParent('');
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateStockGroup(editItem!.id, { name: formName || undefined, parent: formParent || undefined }),
    onSuccess: () => {
      toast({ title: 'Updated' });
      qc.invalidateQueries({ queryKey: ['stock-groups-tree'] });
      qc.invalidateQueries({ queryKey: ['stock-groups-all'] });
      setEditItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteStockGroup(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['stock-groups-tree'] });
      qc.invalidateQueries({ queryKey: ['stock-groups-all'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FolderOpen className="w-6 h-6 text-indigo-600" /> Stock Groups
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {allGroups.length} group{allGroups.length !== 1 ? 's' : ''} — synced with TallyPrime
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowExport(true)} className="gap-2">
            <Download className="w-4 h-4" /> Export
          </Button>
          <Button onClick={() => { setFormName(''); setFormParent(''); setShowCreate(true); }} className="gap-2">
            <Plus className="w-4 h-4" /> New Stock Group
          </Button>
        </div>
      </div>

      {/* Search + tree controls */}
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
            <button onClick={expandAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">
              Expand all
            </button>
            <button onClick={collapseAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">
              Collapse all
            </button>
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

      {/* Tree table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" style={{ marginLeft: (i % 3) * 20 }} />
              ))}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600">
              <AlertCircle className="w-5 h-5" /> Failed to load stock groups.
            </div>
          ) : visible.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              {search ? `No groups matching "${search}"` : 'No stock groups yet. Create one to get started.'}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Name</th>
                  <th className="px-4 py-3 text-left">Parent</th>
                  <th className="px-4 py-3 text-center">Sync</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map(node => (
                  <GroupRow
                    key={node.id}
                    node={node}
                    collapsed={collapsed}
                    onToggle={toggleCollapse}
                    onEdit={g => { setFormName(g.name); setFormParent(g.parent || ''); setEditItem(g); }}
                    onDelete={g => setDeleteItem(g)}
                    selectedIds={selectedIds}
                    onToggleSelect={toggleSelect}
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
          <DialogHeader><DialogTitle>New Stock Group</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. Mobile Phones" />
            </div>
            <div>
              <Label>Parent Group <span className="text-slate-400 text-xs">(leave empty for root)</span></Label>
              <Combobox
                options={allGroups.map(g => g.name)}
                value={formParent}
                onChange={setFormParent}
                placeholder="Search existing groups…"
                clearLabel="— Leave empty (root level)"
                className="mt-1"
              />
              {formParent && (
                <p className="text-xs text-indigo-600 mt-1">
                  Will be created under: <strong>{formParent}</strong>
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader><DialogTitle>Edit Stock Group</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} />
            </div>
            <div>
              <Label>Parent Group</Label>
              <Combobox
                options={allGroups.map(g => g.name)}
                value={formParent}
                onChange={setFormParent}
                placeholder="Search or leave empty for root…"
                clearLabel="— Leave empty (root level)"
                className="mt-1"
              />
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
          <DialogHeader><DialogTitle className="text-red-600">Delete Stock Group</DialogTitle></DialogHeader>
          <p className="text-sm">
            Delete <strong>{deleteItem?.name}</strong>?
            {deleteItem && allGroups.some(g => g.parent?.toLowerCase() === deleteItem.name.toLowerCase()) && (
              <span className="block mt-2 text-amber-600 text-xs">
                ⚠ This group has child groups. Delete them first in TallyPrime.
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

      <BulkDeleteBar
        selectedIds={selectedIds}
        entityLabel="stock group"
        queryKeys={[['stock-groups-tree'], ['stock-groups-all']]}
        onClear={clearSelection}
        onDelete={ids => bulkDeleteApi.masters('stock_group', ids)}
      />

      <ExportDialog
        open={showExport}
        onClose={() => setShowExport(false)}
        isExporting={isExporting}
        contextLabel={search ? `Stock Groups — Search: "${search}"` : 'All Stock Groups'}
        onExport={async (fmt: ExportFormat) => {
          setIsExporting(true);
          try {
            const ts = new Date().toISOString().slice(0, 10);
            await downloadExport(
              '/api/management/stock-groups/export',
              { format: fmt, search: search || undefined },
              `stock_groups_${ts}.${fmt}`,
              fmt,
            );
            setShowExport(false);
          } catch {
            toast({ title: 'Export failed', variant: 'destructive' });
          } finally {
            setIsExporting(false);
          }
        }}
      />
    </div>
  );
}
