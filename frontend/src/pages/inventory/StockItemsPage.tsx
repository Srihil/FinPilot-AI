import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Package, Plus, Search, Loader2, AlertCircle, Pencil, Trash2,
  FolderOpen, FolderClosed, Folder, Layers,
  ChevronRight, ChevronDown, SlidersHorizontal,
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

type Row =
  | { kind: 'group';   node: GroupNode }
  | { kind: 'item';    item: TallyStockItem; depth: number }
  | { kind: 'ug-hdr'; colId: string; count: number }
  | { kind: 'ug-item'; item: TallyStockItem; depth: number };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function countItems(node: GroupNode): number {
  let n = node.items.length;
  for (const c of node.children) n += countItems(c);
  return n;
}

function buildHierarchy(groups: TallyStockGroup[], items: TallyStockItem[]) {
  const byName = new Map<string, GroupNode>();
  for (const g of groups) {
    // First occurrence wins — subsequent duplicates with same name are ignored
    if (!byName.has(g.name.toLowerCase())) {
      byName.set(g.name.toLowerCase(), { ...g, children: [], depth: 0, items: [] });
    }
  }
  const roots: GroupNode[] = [];
  // Iterate the deduplicated map values, not the original groups array
  for (const node of byName.values()) {
    const pk = (node.parent || '').toLowerCase();
    const parent = pk ? byName.get(pk) : null;
    if (parent) { node.depth = parent.depth + 1; parent.children.push(node); }
    else roots.push(node);
  }

  const ugItems: TallyStockItem[] = [];
  for (const item of items) {
    const gNode = item.stock_group ? byName.get(item.stock_group.toLowerCase()) : null;
    if (gNode) gNode.items.push(item);
    else ugItems.push(item);
  }

  const sort = (ns: GroupNode[]) => {
    ns.sort((a, b) => a.name.localeCompare(b.name));
    ns.forEach(n => { sort(n.children); n.items.sort((a, b) => a.name.localeCompare(b.name)); });
  };
  sort(roots);
  ugItems.sort((a, b) => a.name.localeCompare(b.name));

  return { roots, ugItems };
}

function flattenToRows(roots: GroupNode[], ugItems: TallyStockItem[], collapsed: Set<string>): Row[] {
  const rows: Row[] = [];

  const walkGroup = (node: GroupNode) => {
    const cId = `g:${node.id}`;
    rows.push({ kind: 'group', node });
    if (collapsed.has(cId)) return;
    for (const child of node.children) walkGroup(child);
    for (const item of node.items) rows.push({ kind: 'item', item, depth: node.depth + 1 });
  };

  for (const root of roots) walkGroup(root);

  if (ugItems.length > 0) {
    const ugId = '__ug__';
    rows.push({ kind: 'ug-hdr', colId: ugId, count: ugItems.length });
    if (!collapsed.has(ugId))
      for (const item of ugItems) rows.push({ kind: 'ug-item', item, depth: 1 });
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

  const filteredItems = useMemo(() => {
    if (!search.trim()) return allItems;
    const q = search.toLowerCase();
    return allItems.filter(i =>
      i.name.toLowerCase().includes(q) ||
      (i.stock_group || '').toLowerCase().includes(q)
    );
  }, [allItems, search]);

  const { roots, ugItems } = useMemo(
    () => buildHierarchy(allGroups, filteredItems),
    [allGroups, filteredItems]
  );

  const rows = useMemo(
    () => flattenToRows(roots, ugItems, search ? new Set() : collapsed),
    [roots, ugItems, collapsed, search]
  );

  const toggle = (id: string) => setCollapsed(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next;
  });

  const collapseAll = () => {
    const ids = new Set<string>();
    const walk = (ns: GroupNode[]) => { for (const n of ns) { ids.add(`g:${n.id}`); walk(n.children); } };
    walk(roots);
    if (ugItems.length > 0) ids.add('__ug__');
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
      unit: formUnit || undefined, rate: formRate ? parseFloat(formRate) : undefined,
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
    setFormUnit(item.unit || ''); setFormRate(item.rate ? String(item.rate) : '');
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
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Stock Item
        </Button>
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
        {!search && (
          <div className="flex gap-2">
            <button onClick={() => setCollapsed(new Set())} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Expand all</button>
            <button onClick={collapseAll} className="text-xs text-slate-500 hover:text-indigo-600 px-2 py-1 rounded hover:bg-slate-100">Collapse all</button>
          </div>
        )}
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
                  // ── Stock group row
                  if (row.kind === 'group') {
                    const n = row.node;
                    const cId = `g:${n.id}`;
                    const isCol = collapsed.has(cId);
                    const hasChildren = n.children.length + n.items.length > 0;
                    const ic = countItems(n);
                    return (
                      <tr key={cId} className="border-b bg-amber-50/50 hover:bg-amber-50">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5" style={{ paddingLeft: n.depth * 20 }}>
                            {n.depth > 0 && <span className="text-slate-300 select-none text-sm">└</span>}
                            {hasChildren ? (
                              <button onClick={() => toggle(cId)} className="p-0.5 rounded text-slate-400 hover:text-amber-600 hover:bg-amber-100">
                                {isCol ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                              </button>
                            ) : <span className="w-5" />}
                            {hasChildren
                              ? (isCol ? <FolderClosed className="w-4 h-4 text-amber-500 shrink-0" /> : <FolderOpen className="w-4 h-4 text-amber-400 shrink-0" />)
                              : <Folder className="w-4 h-4 text-slate-300 shrink-0" />}
                            <span className="font-semibold text-slate-800 ml-0.5">{n.name}</span>
                            {n.parent && <span className="text-slate-400 text-xs ml-1">· {n.parent}</span>}
                            {ic > 0 && <span className="ml-2 text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">{ic}</span>}
                          </div>
                        </td>
                        <td /><td /><td />
                        <td className="px-4 py-2.5 text-center"><SyncBadge status={n.tally_sync_status} source={n.source} /></td>
                        <td />
                      </tr>
                    );
                  }

                  // ── Stock item under a group
                  if (row.kind === 'item') {
                    const item = row.item;
                    return (
                      <tr key={`item-${item.id}`} className="border-b hover:bg-slate-50 group">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2" style={{ paddingLeft: row.depth * 20 }}>
                            <span className="text-slate-300 select-none text-sm">└</span>
                            <Package className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                            <span className="font-medium text-slate-800">{item.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs">
                          {item.unit
                            ? <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">{item.unit}</span>
                            : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-right text-slate-600">
                          {item.rate ? formatCurrency(item.rate) : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-right font-medium text-indigo-700">
                          {item.opening_qty ? `${item.opening_qty} ${item.unit || ''}`.trim() : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-center"><SyncBadge status={item.tally_sync_status} source={item.source} /></td>
                        <td className="px-4 py-2.5 text-right">
                          <div className={cn('flex items-center justify-end gap-1', 'opacity-0 group-hover:opacity-100 transition-opacity')}>
                            <button onClick={() => openAdjust(item)} title="Adjust Qty" className="p-1.5 rounded hover:bg-indigo-50 text-slate-400 hover:text-indigo-600"><SlidersHorizontal className="w-3.5 h-3.5" /></button>
                            <button onClick={() => openEdit(item)} className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700"><Pencil className="w-3.5 h-3.5" /></button>
                            <button onClick={() => setDeleteItem(item)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  }

                  // ── Ungrouped header
                  if (row.kind === 'ug-hdr') {
                    const isCol = collapsed.has(row.colId);
                    return (
                      <tr key="ug-hdr" className="border-b bg-slate-100/70">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-1.5">
                            <button onClick={() => toggle(row.colId)} className="p-0.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-200">
                              {isCol ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                            </button>
                            <Layers className="w-4 h-4 text-slate-400 shrink-0" />
                            <span className="font-medium text-slate-500 italic">Ungrouped</span>
                            <span className="ml-1 text-xs bg-slate-200 text-slate-500 px-1.5 py-0.5 rounded-full">{row.count}</span>
                          </div>
                        </td>
                        <td /><td /><td /><td />
                      </tr>
                    );
                  }

                  // ── Ungrouped item
                  if (row.kind === 'ug-item') {
                    const item = row.item;
                    return (
                      <tr key={`ugitem-${item.id}`} className="border-b hover:bg-slate-50 group">
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2" style={{ paddingLeft: row.depth * 20 }}>
                            <span className="text-slate-300 select-none text-sm">└</span>
                            <Package className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                            <span className="font-medium text-slate-800">{item.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-xs">
                          {item.unit
                            ? <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">{item.unit}</span>
                            : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-right text-slate-600">
                          {item.rate ? formatCurrency(item.rate) : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-xs text-right font-medium text-indigo-700">
                          {item.opening_qty ? `${item.opening_qty} ${item.unit || ''}`.trim() : <span className="text-slate-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5 text-center"><SyncBadge status={item.tally_sync_status} source={item.source} /></td>
                        <td className="px-4 py-2.5 text-right">
                          <div className={cn('flex items-center justify-end gap-1', 'opacity-0 group-hover:opacity-100 transition-opacity')}>
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
    </div>
  );
}
