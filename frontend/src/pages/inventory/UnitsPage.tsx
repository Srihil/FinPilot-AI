import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Scale, Plus, Search, Loader2, AlertCircle, Pencil, Trash2, ChevronDown } from 'lucide-react';
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
import type { TallyUnit } from '../../types';

// Full TallyPrime UQC list.
// `tallySymbol` = the NAME TallyPrime stores (what BASEUNITS references in stock items).
// `uqc`        = the UQC code shown in TallyPrime's UQC dropdown.
// `formal`     = human-readable description shown in our UI only.
const STANDARD_UQCS = [
  { uqc: 'BAG', tallySymbol: 'Bag',  formal: 'Bags' },
  { uqc: 'BAL', tallySymbol: 'Bal',  formal: 'Bale' },
  { uqc: 'BDL', tallySymbol: 'Bdl',  formal: 'Bundles' },
  { uqc: 'BKL', tallySymbol: 'Bkl',  formal: 'Buckles' },
  { uqc: 'BOU', tallySymbol: 'Bou',  formal: 'Billion of Units' },
  { uqc: 'BOX', tallySymbol: 'Box',  formal: 'Box' },
  { uqc: 'BTL', tallySymbol: 'Btl',  formal: 'Bottles' },
  { uqc: 'BUN', tallySymbol: 'Bun',  formal: 'Bunches' },
  { uqc: 'CAN', tallySymbol: 'Can',  formal: 'Cans' },
  { uqc: 'CBM', tallySymbol: 'Cbm',  formal: 'Cubic Meters' },
  { uqc: 'CCM', tallySymbol: 'Ccm',  formal: 'Cubic Centimeters' },
  { uqc: 'CMS', tallySymbol: 'Cms',  formal: 'Centimeters' },
  { uqc: 'CTN', tallySymbol: 'Ctn',  formal: 'Cartons' },
  { uqc: 'DOZ', tallySymbol: 'Doz',  formal: 'Dozens' },
  { uqc: 'DRM', tallySymbol: 'Drm',  formal: 'Drums' },
  { uqc: 'GGK', tallySymbol: 'Ggk',  formal: 'Great Gross' },
  { uqc: 'GMS', tallySymbol: 'Gms',  formal: 'Grammes' },
  { uqc: 'GRS', tallySymbol: 'Grs',  formal: 'Gross' },
  { uqc: 'GYD', tallySymbol: 'Gyd',  formal: 'Gross Yards' },
  { uqc: 'KGS', tallySymbol: 'Kgs',  formal: 'Kilograms' },
  { uqc: 'KLR', tallySymbol: 'Klr',  formal: 'Kilolitre' },
  { uqc: 'KME', tallySymbol: 'Kme',  formal: 'Kilometre' },
  { uqc: 'LTR', tallySymbol: 'Ltr',  formal: 'Litres' },
  { uqc: 'MLT', tallySymbol: 'Mlt',  formal: 'Mililitre' },
  { uqc: 'MTR', tallySymbol: 'Mtr',  formal: 'Meters' },
  { uqc: 'MTS', tallySymbol: 'Mts',  formal: 'Metric Ton' },
  { uqc: 'NOS', tallySymbol: 'Nos',  formal: 'Numbers' },
  { uqc: 'OTH', tallySymbol: 'Oth',  formal: 'Others' },
  { uqc: 'PAC', tallySymbol: 'Pac',  formal: 'Packs' },
  { uqc: 'PCS', tallySymbol: 'Pcs',  formal: 'Pieces' },
  { uqc: 'PKT', tallySymbol: 'Pkt',  formal: 'Packets' },
  { uqc: 'PRS', tallySymbol: 'Prs',  formal: 'Pairs' },
  { uqc: 'QNT', tallySymbol: 'Qnt',  formal: 'Quintal' },
  { uqc: 'ROL', tallySymbol: 'Rol',  formal: 'Rolls' },
  { uqc: 'SET', tallySymbol: 'Set',  formal: 'Sets' },
  { uqc: 'SQF', tallySymbol: 'Sqf',  formal: 'Square Feet' },
  { uqc: 'SQM', tallySymbol: 'Sqm',  formal: 'Square Meters' },
  { uqc: 'SQY', tallySymbol: 'Sqy',  formal: 'Square Yards' },
  { uqc: 'TBL', tallySymbol: 'Tbl',  formal: 'Tablets' },
  { uqc: 'TON', tallySymbol: 'Ton',  formal: 'Tonnes' },
  { uqc: 'TUB', tallySymbol: 'Tub',  formal: 'Tubes' },
  { uqc: 'UNT', tallySymbol: 'Unt',  formal: 'Units' },
  { uqc: 'YDS', tallySymbol: 'Yds',  formal: 'Yards' },
];

type CreateMode = 'standard' | 'custom';

export default function UnitsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [createMode, setCreateMode] = useState<CreateMode>('standard');
  const [editItem, setEditItem] = useState<TallyUnit | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyUnit | null>(null);

  // Standard UQC selection
  const [selectedUqc, setSelectedUqc] = useState<typeof STANDARD_UQCS[0] | null>(null);
  const [uqcSearch, setUqcSearch] = useState('');
  const [uqcDecimals, setUqcDecimals] = useState('0');

  // Custom unit fields
  const [formName, setFormName] = useState('');
  const [formSymbol, setFormSymbol] = useState('');
  const [formDecimals, setFormDecimals] = useState('0');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['units', page, search],
    queryFn: () => managementApi.units({ page, page_size: 20, search: search || undefined }),
  });

  const createMut = useMutation({
    mutationFn: () => {
      if (createMode === 'standard' && selectedUqc) {
        // name   = formal/display name (e.g. "Numbers")   → TallyPrime NAME field
        // symbol = short abbreviation (e.g. "Nos")        → TallyPrime ORIGINALNAME field
        return managementApi.createUnit({
          name: selectedUqc.formal,
          symbol: selectedUqc.tallySymbol,
          decimal_places: parseInt(uqcDecimals) || 0,
        });
      }
      return managementApi.createUnit({
        name: formName.trim(),
        symbol: formSymbol || undefined,
        decimal_places: parseInt(formDecimals) || 0,
      });
    },
    onSuccess: () => {
      toast({ title: 'Unit created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['units'] });
      setShowCreate(false); resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateUnit(editItem!.id, {
      name: formName || undefined,
      symbol: formSymbol || undefined,
      decimal_places: formDecimals ? parseInt(formDecimals) : undefined,
    }),
    onSuccess: () => { toast({ title: 'Updated' }); qc.invalidateQueries({ queryKey: ['units'] }); setEditItem(null); },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteUnit(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['units'] }); setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  function resetForm() {
    setSelectedUqc(null); setUqcSearch(''); setUqcDecimals('0');
    setFormName(''); setFormSymbol(''); setFormDecimals('0');
    setCreateMode('standard');
  }

  const filteredUqcs = STANDARD_UQCS.filter(u =>
    u.uqc.toLowerCase().includes(uqcSearch.toLowerCase()) ||
    u.tallySymbol.toLowerCase().includes(uqcSearch.toLowerCase()) ||
    u.formal.toLowerCase().includes(uqcSearch.toLowerCase())
  );

  const canCreate = createMode === 'standard' ? !!selectedUqc : !!formName.trim();
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Scale className="w-6 h-6 text-indigo-600" /> Units of Measure</h1>
          <p className="text-sm text-slate-500 mt-0.5">Units synced with TallyPrime (all 43 standard UQCs + custom)</p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2"><Plus className="w-4 h-4" /> New Unit</Button>
      </div>

      <div className="relative max-w-sm"><Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" /><Input placeholder="Search units…" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" /></div>

      <Card><CardContent className="p-0">
        {isLoading ? <div className="p-6 space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
        : isError ? <div className="flex items-center gap-2 p-6 text-red-600"><AlertCircle className="w-5 h-5" /> Failed to load.</div>
        : <table className="w-full text-sm">
            <thead><tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
              <th className="px-4 py-3 text-left">Name</th><th className="px-4 py-3 text-left">Symbol</th><th className="px-4 py-3 text-center">Decimals</th><th className="px-4 py-3 text-center">Sync</th><th className="px-4 py-3 text-right">Actions</th>
            </tr></thead>
            <tbody>
              {data?.items.length === 0 ? <tr><td colSpan={5} className="text-center py-10 text-slate-400">No units found. Add a standard UQC or create a custom unit.</td></tr>
              : data?.items.map(u => (
                <tr key={u.id} className="border-b hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium">{u.name}</td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{u.symbol || '—'}</td>
                  <td className="px-4 py-3 text-center text-slate-500">{u.decimal_places}</td>
                  <td className="px-4 py-3 text-center"><SyncBadge status={u.tally_sync_status} source={u.source} /></td>
                  <td className="px-4 py-3 text-right"><div className="flex items-center justify-end gap-2">
                    <button onClick={() => { setFormName(u.name); setFormSymbol(u.symbol||''); setFormDecimals(String(u.decimal_places)); setEditItem(u); }} className="p-1.5 rounded hover:bg-slate-100 text-slate-500"><Pencil className="w-3.5 h-3.5" /></button>
                    <button onClick={() => setDeleteItem(u)} className="p-1.5 rounded hover:bg-red-50 text-slate-400 hover:text-red-600"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>}
      </CardContent></Card>

      {totalPages > 1 && <div className="flex justify-between text-sm text-slate-500"><span>Page {page} of {totalPages}</span><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Prev</Button><Button variant="outline" size="sm" disabled={page>=totalPages} onClick={()=>setPage(p=>p+1)}>Next</Button></div></div>}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Add Unit of Measure</DialogTitle></DialogHeader>

          {/* Mode tabs */}
          <div className="flex gap-2 p-1 bg-slate-100 rounded-lg">
            <button
              onClick={() => setCreateMode('standard')}
              className={cn('flex-1 py-1.5 rounded-md text-sm font-medium transition-colors', createMode === 'standard' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700')}
            >
              Standard UQC (TallyPrime)
            </button>
            <button
              onClick={() => setCreateMode('custom')}
              className={cn('flex-1 py-1.5 rounded-md text-sm font-medium transition-colors', createMode === 'custom' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700')}
            >
              Custom Unit
            </button>
          </div>

          {createMode === 'standard' ? (
            <div className="space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                <Input placeholder="Search UQCs…" value={uqcSearch} onChange={e => setUqcSearch(e.target.value)} className="pl-9" />
              </div>
              <div className="border rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                {filteredUqcs.length === 0 ? (
                  <div className="p-4 text-center text-slate-400 text-sm">No match found.</div>
                ) : filteredUqcs.map(u => (
                  <button
                    key={u.uqc}
                    onClick={() => setSelectedUqc(u)}
                    className={cn(
                      'w-full flex items-center gap-3 px-3 py-2 text-left text-sm border-b last:border-0 transition-colors',
                      selectedUqc?.uqc === u.uqc ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-slate-50 text-slate-700',
                    )}
                  >
                    <span className="font-mono text-xs font-bold w-10 shrink-0">{u.uqc}</span>
                    <span className="flex-1">{u.formal}</span>
                    <span className="text-xs text-slate-400 font-mono">{u.tallySymbol}</span>
                  </button>
                ))}
              </div>
              {selectedUqc && (
                <div className="flex items-center gap-3 p-3 bg-indigo-50 rounded-lg">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-indigo-900">{selectedUqc.formal} <span className="font-mono text-indigo-600">({selectedUqc.uqc})</span> <span className="text-xs text-indigo-500">→ Tally: <strong>{selectedUqc.tallySymbol}</strong></span></p>
                  </div>
                  <div className="w-28">
                    <Label className="text-xs">Decimal Places</Label>
                    <Input type="number" min="0" max="5" value={uqcDecimals} onChange={e=>setUqcDecimals(e.target.value)} className="h-8 mt-1"/>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div><Label>Name *</Label><Input value={formName} onChange={e=>setFormName(e.target.value)} placeholder="e.g. Kilogram"/></div>
              <div><Label>Symbol <span className="text-slate-400 text-xs">(max 8 chars, no spaces)</span></Label><Input value={formSymbol} onChange={e=>setFormSymbol(e.target.value)} placeholder="e.g. Kg"/></div>
              <div><Label>Decimal Places</Label><Input type="number" min="0" max="5" value={formDecimals} onChange={e=>setFormDecimals(e.target.value)}/></div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={()=>setShowCreate(false)}>Cancel</Button>
            <Button onClick={()=>createMut.mutate()} disabled={!canCreate||createMut.isPending}>
              {createMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Create Unit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={()=>setEditItem(null)}><DialogContent className="max-w-md"><DialogHeader><DialogTitle>Edit Unit</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Name</Label><Input value={formName} onChange={e=>setFormName(e.target.value)}/></div>
          <div><Label>Symbol</Label><Input value={formSymbol} onChange={e=>setFormSymbol(e.target.value)}/></div>
          <div><Label>Decimal Places</Label><Input type="number" min="0" max="5" value={formDecimals} onChange={e=>setFormDecimals(e.target.value)}/></div>
        </div>
        <DialogFooter><Button variant="outline" onClick={()=>setEditItem(null)}>Cancel</Button><Button onClick={()=>updateMut.mutate()} disabled={updateMut.isPending}>{updateMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Save</Button></DialogFooter>
      </DialogContent></Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={()=>setDeleteItem(null)}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle className="text-red-600">Delete Unit</DialogTitle></DialogHeader>
        <p className="text-sm">Delete <strong>{deleteItem?.name}</strong>? This will also remove it from TallyPrime.</p>
        <DialogFooter><Button variant="outline" onClick={()=>setDeleteItem(null)}>Cancel</Button><Button variant="destructive" onClick={()=>deleteMut.mutate()} disabled={deleteMut.isPending}>{deleteMut.isPending&&<Loader2 className="w-4 h-4 animate-spin mr-2"/>}Delete</Button></DialogFooter>
      </DialogContent></Dialog>
    </div>
  );
}
