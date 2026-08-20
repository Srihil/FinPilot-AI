import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Package, Plus, Search, Loader2, AlertCircle, Pencil, Trash2,
  FolderOpen, FolderClosed, Folder,
  ChevronRight, ChevronDown, SlidersHorizontal, Square, CheckSquare, Download,
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
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import { managementApi } from '../../api/endpoints';
import apiClient from '../../api/client';

const stockTxnApi = {
  create: (d: object) => apiClient.post('/api/inventory/stock-transactions', d).then(r => r.data),
};
import { formatCurrency } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { TallyStockItem, TallyUnit, TallyStockGroup } from '../../types';

// ─── Tree types ───────────────────────────────────────────────────────────────

interface GroupNode extends TallyStockGroup {
  children: GroupNode[];
  depth: number;
  items: TallyStockItem[];
}

// `continues[i]` = true when ancestor at nesting level i still has more siblings
// after the current subtree → draw │ at that column; false → draw space.
// The last element is whether THIS node itself has more siblings → ├─ vs └─.
type Row =
  | { kind: 'group'; node: GroupNode; continues: boolean[] }
  | { kind: 'item';  item: TallyStockItem; continues: boolean[] };

// ─── Tree connector prefix ────────────────────────────────────────────────────

function TreePrefix({ continues }: { continues: boolean[] }) {
  if (continues.length === 0) return null;
  const ancestors = continues.slice(0, -1);
  const isLast    = !continues[continues.length - 1];
  return (
    <span className="font-mono text-slate-300 select-none whitespace-pre text-sm leading-none">
      {ancestors.map((c, i) => <span key={i}>{c ? '│  ' : '   '}</span>)}
      <span>{isLast ? '└─ ' : '├─ '}</span>
    </span>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function countItems(node: GroupNode): number {
  let n = node.items.length;
  for (const c of node.children) n += countItems(c);
  return n;
}

function collectItemIds(node: GroupNode): string[] {
  const ids: string[] = node.items.map(i => i.id);
  for (const c of node.children) ids.push(...collectItemIds(c));
  return ids;
}

function buildHierarchy(groups: TallyStockGroup[], items: TallyStockItem[]) {
  // Build map: normalised name → node
  const byName = new Map<string, GroupNode>();
  const normalise = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');
  for (const g of groups) {
    const key = normalise(g.name);
    if (!byName.has(key))
      byName.set(key, { ...g, children: [], depth: 0, items: [] });
  }

  const roots: GroupNode[] = [];
  for (const node of byName.values()) {
    const pk = node.parent ? normalise(node.parent) : '';
    const parent = pk ? byName.get(pk) : null;
    if (parent) { node.depth = parent.depth + 1; parent.children.push(node); }
    else roots.push(node);
  }

  // Match items to groups; unmatched items go to rootItems (shown at root, not "Ungrouped")
  const rootItems: TallyStockItem[] = [];
  for (const item of items) {
    const key = item.stock_group ? normalise(item.stock_group) : '';
    const gNode = key ? byName.get(key) : null;
    if (gNode) gNode.items.push(item);
    else rootItems.push(item);
  }

  const sort = (ns: GroupNode[]) => {
    ns.sort((a, b) => a.name.localeCompare(b.name));
    ns.forEach(n => { sort(n.children); n.items.sort((a, b) => a.name.localeCompare(b.name)); });
  };
  sort(roots);
  rootItems.sort((a, b) => a.name.localeCompare(b.name));

  return { roots, rootItems };
}

function flattenToRows(
  roots: GroupNode[],
  rootItems: TallyStockItem[],
  collapsed: Set<string>,
): Row[] {
  const rows: Row[] = [];

  const walkGroup = (node: GroupNode, parentContinues: boolean[]) => {
    const cId = `g:${node.id}`;
    rows.push({ kind: 'group', node, continues: parentContinues });
    if (collapsed.has(cId)) return;

    // Interleave sub-groups and items, groups first then items
    const subGroups = node.children;
    const nodeItems = node.items;
    const total = subGroups.length + nodeItems.length;
    let idx = 0;
    for (const child of subGroups) {
      const isLast = idx === total - 1;
      walkGroup(child, [...parentContinues, !isLast]);
      idx++;
    }
    for (const item of nodeItems) {
      const isLast = idx === total - 1;
      rows.push({ kind: 'item', item, continues: [...parentContinues, !isLast] });
      idx++;
    }
  };

  // Root-level: all root groups + unmatched items shown together
  const rootEntries: Array<{ type: 'group'; node: GroupNode } | { type: 'item'; item: TallyStockItem }> = [
    ...roots.map(n => ({ type: 'group' as const, node: n })),
    ...rootItems.map(i => ({ type: 'item' as const, item: i })),
  ];
  // Root items have no tree prefix (continues = [])
  for (const entry of rootEntries) {
    if (entry.type === 'group') walkGroup(entry.node, []);
    else rows.push({ kind: 'item', item: entry.item, continues: [] });
  }

  return rows;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function StockItemsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyStockItem | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyStockItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showExport, setShowExport] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const toggleSelect = (id: string) => setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSelection = () => setSelectedIds(new Set());

  const [formName, setFormName] = useState('');

  const [formGroup, setFormGroup] = useState('');
  const [formUnit, setFormUnit] = useState('');
  const [formRate, setFormRate] = useState('');
  const [formQty, setFormQty] = useState('');

  // Adjust Qty state
  const [adjustItem, setAdjustItem] = useState<TallyStockItem | null>(null);
  const [formAdjGodown, setFormAdjGodown] = useState('');
  const [formAdjQty, setFormAdjQty] = useState('');
  const [formAdjRate, setFormAdjRate] = useState('');
  const [formAdjDate, setFormAdjDate] = useState('');

  const { data: itemsData, isLoading, isError } = useQuery({
    queryKey: ['stock-items-tree'],
    queryFn: () => managementApi.stockItems({ page_size: 500 }),
    refetchInterval: 5000,
  });

  const { data: unitsData } = useQuery({
    queryKey: ['units-all'],
    queryFn: () => managementApi.units({ page_size: 100 }),
    staleTime: 60_000,
  });

  const { data: groupsData } = useQuery({
    queryKey: ['stock-groups-all'],
    queryFn: () => managementApi.stockGroups({ page_size: 500 }),
    staleTime: 60_000,
  });

  const { data: godownsData } = useQuery({
    queryKey: ['godowns-all'],
    queryFn: () => managementApi.godowns({ page_size: 100 }),
    staleTime: 60_000,
  });
  const godownNames = (godownsData?.items ?? []).map(g => g.name);

  const allItems: TallyStockItem[] = itemsData?.items ?? [];
  const allGroups: TallyStockGroup[] = groupsData?.items ?? [];

  const leafIds = allItems.map(i => i.id);
  const allLeafSelected = leafIds.length > 0 && leafIds.every(id => selectedIds.has(id));
  const toggleSelectAll = () => allLeafSelected
    ? setSelectedIds(prev => { const n = new Set(prev); leafIds.forEach(id => n.delete(id)); return n; })
    : setSelectedIds(prev => new Set([...prev, ...leafIds]));

  const filteredItems = useMemo(() => {
    if (!search.trim()) return allItems;
    const q = search.toLowerCase();
    return allItems.filter(i =>
      i.name.toLowerCase().includes(q) ||
      (i.stock_group || '').toLowerCase().includes(q)
    );
  }, [allItems, search]);

  const { roots, rootItems } = useMemo(
    () => buildHierarchy(allGroups, filteredItems),
    [allGroups, filteredItems]
  );

  const rows = useMemo(
    () => flattenToRows(roots, rootItems, search ? new Set() : collapsed),
    [roots, rootItems, collapsed, search]
  );

  const toggle = (id: string) => setCollapsed(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next;
  });

  const collapseAll = () => {
    const ids = new Set<string>();
    const walk = (ns: GroupNode[]) => { for (const n of ns) { ids.add(`g:${n.id}`); walk(n.children); } };
    walk(roots);
    setCollapsed(ids);
  };

  const createMut = useMutation({
    mutationFn: () => managementApi.createStockItem({
      name: formName.trim(), stock_group: formGroup || undefined,
      unit: formUnit || undefined, rate: formRate ? parseFloat(formRate) : 0,
      opening_qty: formQty ? parseFloat(formQty) : 0,
    }),
    onSuccess: () => {
      toast({ title: 'Stock item created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['stock-items-tree'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateStockItem(editItem!.id, {
      name: formName || undefined, stock_group: formGroup || undefined,
      unit: formUnit || undefined, rate: formRate.trim() !== '' ? parseFloat(formRate) : undefined,
    }),
    onSuccess: () => {
      toast({ title: 'Updated' });
      qc.invalidateQueries({ queryKey: ['stock-items-tree'] });
      setEditItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteStockItem(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['stock-items-tree'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  const adjustMut = useMutation({
    mutationFn: () => stockTxnApi.create({
      transaction_type: 'PHYSICAL_STOCK',
      transaction_date: formAdjDate || undefined,
      from_godown: formAdjGodown || undefined,
      narration: `Physical stock adjustment — ${adjustItem!.name}`,
      entries: [{
        stock_item_name: adjustItem!.name,
        quantity: parseFloat(formAdjQty) || 0,
        unit: adjustItem!.unit || '',
        rate: parseFloat(formAdjRate) || adjustItem!.rate || 0,
      }],
    }),
    onSuccess: () => {
      toast({ title: 'Physical Stock created', description: 'Queued for TallyPrime sync. Qty will update after sync.' });
      qc.invalidateQueries({ queryKey: ['stock-transactions'] });
      setAdjustItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' }),
  });

  function openAdjust(item: TallyStockItem) {
    setFormAdjGodown('');
    setFormAdjQty(item.opening_qty ? String(item.opening_qty) : '');
    setFormAdjRate(item.rate ? String(item.rate) : '');
    setFormAdjDate('');
    setAdjustItem(item);
  }

  function resetForm() { setFormName(''); setFormGroup(''); setFormUnit(''); setFormRate(''); setFormQty(''); }
  function openEdit(item: TallyStockItem) {
    setFormName(item.name); setFormGroup(item.stock_group || '');
    setFormUnit(item.unit || '');
    // Use explicit null/undefined check so rate=0 is preserved as '0', not ''
    setFormRate(item.rate != null ? String(item.rate) : '');
    setEditItem(item);
  }

  const groupOpts = allGroups.map(g => g.name);
  const unitItems = unitsData?.items ?? [];

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Package className="w-6 h-6 text-indigo-600" /> Stock Items
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {allItems.length} item{allItems.length !== 1 ? 's' : ''} · Group → Item hierarchy
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowExport(true)} className="gap-2">
            <Download className="w-4 h-4" /> Export
          </Button>
          <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
            <Plus className="w-4 h-4" /> New Stock Item
          </Button>
        </div>
      </div>

      {/* Search + controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search items or groups…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex gap-2">
          {!search && (
            <>
              <button onClick={() => setCollapsed(new Set())} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Expand all</button>
              <button onClick={collapseAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Collapse all</button>
            </>
          )}
          <button
            onClick={toggleSelectAll}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-indigo-700 px-2 py-1 rounded hover:bg-indigo-50 transition-colors"
          >
            {allLeafSelected ? <CheckSquare className="w-3.5 h-3.5 text-indigo-600" /> : <Square className="w-3.5 h-3.5" />}
            {allLeafSelected ? 'Deselect all' : `Select all (${leafIds.length})`}
          </button>
        </div>
      </div>

      {/* Tree */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-9 w-full" style={{ marginLeft: (i % 3) * 20 }} />)}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load stock items.</div>
          ) : rows.length === 0 ? (
            <div className="text-center py-14 text-slate-400">
              {search ? `No items matching "${search}"` : 'No stock items yet. Create one to get started.'}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Hierarchy</th>
                  <th className="px-4 py-3 text-left w-28">Unit</th>
                  <th className="px-4 py-3 text-right w-28">Rate</th>
                  <th className="px-4 py-3 text-right w-28">Qty</th>
                  <th className="px-4 py-3 text-center w-24">Sync</th>
                  <th className="px-4 py-3 text-right w-20">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  // ── Group row ──────────────────────────────────────────────
                  if (row.kind === 'group') {
                    const n = row.node;
                    const cId = `g:${n.id}`;
                    const isCol = collapsed.has(cId);
                    const hasChildren = n.children.length + n.items.length > 0;
                    const ic = countItems(n);
                    const isRoot = row.continues.length === 0;
                    const gItemIds = ic > 0 ? collectItemIds(n) : [];
                    const allGroupSelected = gItemIds.length > 0 && gItemIds.every(id => selectedIds.has(id));
                    const toggleGroupSelect = (e: React.MouseEvent) => {
                      e.stopPropagation();
                      if (allGroupSelected) {
                        setSelectedIds(prev => { const s = new Set(prev); gItemIds.forEach(id => s.delete(id)); return s; });
                      } else {
                        setSelectedIds(prev => new Set([...prev, ...gItemIds]));
                      }
                    };
                    return (
                      <tr key={`${cId}-${i}`} className={cn('border-b', isRoot ? 'bg-amber-50/60' : 'hover:bg-amber-50/40', hasChildren && 'cursor-pointer select-none')} onClick={() => hasChildren && toggle(cId)}>
                        <td className="px-3 py-2">
                          <div className="flex items-center">
                            {gItemIds.length > 0 ? (
                              <button onClick={toggleGroupSelect} className="p-1 rounded shrink-0 text-slate-300 hover:text-indigo-600 transition-colors">
                                {allGroupSelected ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
                              </button>
                            ) : <span className="w-6 shrink-0" />}
                            <TreePrefix continues={row.continues} />
                            {hasChildren ? (
                              <button
                                className="p-0.5 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-100 shrink-0 pointer-events-none"
                              >
                                {isCol ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                              </button>
                            ) : <span className="w-5 shrink-0" />}
                            {hasChildren
                              ? (isCol
                                ? <FolderClosed className="w-4 h-4 text-amber-500 shrink-0 ml-0.5" />
                                : <FolderOpen className="w-4 h-4 text-amber-400 shrink-0 ml-0.5" />)
                              : <Folder className="w-4 h-4 text-slate-300 shrink-0 ml-0.5" />}
                            <span className={cn('ml-1.5 text-slate-800', isRoot ? 'font-bold' : 'font-semibold text-sm')}>{n.name}</span>
                            {ic > 0 && (
                              <span className="ml-2 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-semibold shrink-0">
                                {ic}
                              </span>
                            )}
                          </div>
                        </td>
                        <td /><td /><td />
                        <td className="px-4 py-2 text-center">
                          <SyncBadge status={n.tally_sync_status} source={n.source} />
                        </td>
                        <td />
                      </tr>
                    );
                  }

                  // ── Item row ───────────────────────────────────────────────
                  if (row.kind === 'item') {
                    const item = row.item;
                    const isRoot = row.continues.length === 0;
                    return (
                      <tr key={`item-${item.id}-${i}`} className="border-b hover:bg-slate-50/80 group">
                        <td className="px-3 py-2">
                          <div className="flex items-center">
                            <button onClick={e => { e.stopPropagation(); toggleSelect(item.id); }} className="p-1 rounded shrink-0 text-slate-300 hover:text-indigo-600 transition-colors">
                              {selectedIds.has(item.id) ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
                            </button>
                            <TreePrefix continues={row.continues} />
                            <Package className={cn('w-3.5 h-3.5 shrink-0', isRoot ? 'text-slate-400' : 'text-indigo-400')} />
                            <span className="ml-1.5 font-medium text-slate-800 text-sm">{item.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-xs">
                          {item.unit
                            ? <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">{item.unit}</span>
                            : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2 text-xs text-right text-slate-600">
                          {item.rate ? formatCurrency(item.rate) : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2 text-xs text-right font-medium text-indigo-700">
                          {item.opening_qty ? `${item.opening_qty} ${item.unit || ''}`.trim() : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2 text-center">
                          <SyncBadge status={item.tally_sync_status} source={item.source} />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className={cn('flex items-center justify-end gap-0.5', 'opacity-0 group-hover:opacity-100 transition-opacity')}>
                            <button onClick={() => openAdjust(item)} title="Adjust Qty" className="p-1.5 rounded hover:bg-indigo-50 text-slate-400 hover:text-indigo-600"><SlidersHorizontal className="w-3.5 h-3.5" /></button>
                            <button onClick={() => openEdit(item)} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700"><Pencil className="w-3.5 h-3.5" /></button>
                            <button onClick={() => setDeleteItem(item)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  }

                  return null;
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}><DialogHeader><DialogTitle>New Stock Item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name *</Label><Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. Laptop" className="mt-1" /></div>
            <div>
              <Label>Stock Group</Label>
              <Combobox options={groupOpts} value={formGroup} onChange={setFormGroup} placeholder="Search groups…" clearLabel="— No group" className="mt-1" />
            </div>
            <div>
              <Label>Unit</Label>
              <select value={formUnit} onChange={e => setFormUnit(e.target.value)} className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                <option value="">— No unit —</option>
                {unitItems.map((u: TallyUnit) => <option key={u.id} value={u.name}>{u.name}{u.symbol ? ` (${u.symbol})` : ''}</option>)}
              </select>
              {!unitItems.length && <p className="text-xs text-amber-600 mt-1">No units yet — create units first.</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Opening Qty</Label><Input type="number" min="0" value={formQty} onChange={e => setFormQty(e.target.value)} placeholder="0" className="mt-1" /></div>
              <div><Label>Rate (₹)</Label><Input type="number" min="0" value={formRate} onChange={e => setFormRate(e.target.value)} placeholder="0" className="mt-1" /></div>
            </div>
            <p className="text-xs text-slate-400">Opening Qty × Rate = Opening Balance in TallyPrime</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}><DialogHeader><DialogTitle>Edit Stock Item</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name</Label><Input value={formName} onChange={e => setFormName(e.target.value)} className="mt-1" /></div>
            <div>
              <Label>Stock Group</Label>
              <Combobox options={groupOpts} value={formGroup} onChange={setFormGroup} placeholder="Search groups…" clearLabel="— No group" className="mt-1" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Unit</Label>
                <select value={formUnit} onChange={e => setFormUnit(e.target.value)} className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring">
                  <option value="">— No unit —</option>
                  {unitItems.map((u: TallyUnit) => <option key={u.id} value={u.name}>{u.name}{u.symbol ? ` (${u.symbol})` : ''}</option>)}
                </select>
              </div>
              <div><Label>Rate (₹)</Label><Input type="number" value={formRate} onChange={e => setFormRate(e.target.value)} className="mt-1" /></div>
            </div>
            <div>
              <Label>Current Quantity</Label>
              <div className="mt-1 flex items-center gap-2 px-3 py-2 rounded-md border border-slate-200 bg-slate-50">
                <span className="text-sm font-semibold text-indigo-700">
                  {editItem?.opening_qty ? `${editItem.opening_qty} ${editItem.unit || ''}`.trim() : '—'}
                </span>
                <span className="text-xs text-slate-400 ml-auto">Use Physical Stock voucher to adjust</span>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Adjust Qty dialog */}
      <Dialog open={!!adjustItem} onOpenChange={() => setAdjustItem(null)}>
        <DialogContent className="max-w-md" onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-indigo-600" />
              Adjust Quantity — {adjustItem?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-indigo-50 border border-indigo-100">
              <Package className="w-4 h-4 text-indigo-500 shrink-0" />
              <div className="text-sm">
                <span className="font-semibold text-indigo-800">{adjustItem?.name}</span>
                <span className="text-indigo-500 ml-2 text-xs">
                  Current: {adjustItem?.opening_qty ?? 0} {adjustItem?.unit || ''}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>New Quantity *</Label>
                <Input
                  type="number"
                  min="0"
                  value={formAdjQty}
                  onChange={e => setFormAdjQty(e.target.value)}
                  placeholder="0"
                  className="mt-1"
                />
                <p className="text-xs text-slate-400 mt-1">Target quantity after adjustment</p>
              </div>
              <div>
                <Label>Rate (₹)</Label>
                <Input
                  type="number"
                  min="0"
                  value={formAdjRate}
                  onChange={e => setFormAdjRate(e.target.value)}
                  placeholder="0"
                  className="mt-1"
                />
              </div>
            </div>
            <div>
              <Label>Godown</Label>
              <Combobox
                options={godownNames}
                value={formAdjGodown}
                onChange={setFormAdjGodown}
                placeholder="Select godown…"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Date</Label>
              <Input
                type="date"
                value={formAdjDate}
                onChange={e => setFormAdjDate(e.target.value)}
                className="mt-1"
              />
              <p className="text-xs text-amber-600 mt-1 font-medium">
                Use TallyPrime's <strong>Current Date</strong> (shown in Gateway of Tally) — not your PC's date. If the company was split, use the split date or later.
              </p>
            </div>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              This creates a <strong>Physical Stock</strong> voucher in TallyPrime which sets the stock count to the quantity you enter above. The Qty column here updates automatically after the next sync.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustItem(null)}>Cancel</Button>
            <Button
              onClick={() => adjustMut.mutate()}
              disabled={adjustMut.isPending || !formAdjQty}
            >
              {adjustMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Adjust &amp; Sync to Tally
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm"><DialogHeader><DialogTitle className="text-red-600">Delete Stock Item</DialogTitle></DialogHeader>
          <p className="text-sm">Delete <strong>{deleteItem?.name}</strong>? This will also remove it from TallyPrime.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteItem(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteMut.mutate()} disabled={deleteMut.isPending}>
              {deleteMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <BulkDeleteBar
        selectedIds={selectedIds}
        entityLabel="stock item"
        queryKeys={[['stock-items-tree']]}
        onClear={clearSelection}
        onDelete={ids => bulkDeleteApi.masters('stock_item', ids)}
      />

      <ExportDialog
        open={showExport}
        onClose={() => setShowExport(false)}
        isExporting={isExporting}
        contextLabel={search ? `Stock Items — Search: "${search}"` : 'All Stock Items'}
        onExport={async (fmt: ExportFormat) => {
          setIsExporting(true);
          try {
            const ts = new Date().toISOString().slice(0, 10);
            await downloadExport(
              '/api/management/stock-items/export',
              { format: fmt, search: search || undefined },
              `stock_items_${ts}.${fmt}`,
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
