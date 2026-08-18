import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen, Plus, Search, Loader2, AlertCircle, Pencil, Trash2,
  ChevronRight, ChevronDown, Layers,
} from 'lucide-react';
import { Card, CardContent } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { SyncBadge } from '../../components/ui/SyncBadge';
import { toast } from '../../components/ui/use-toast';
import { managementApi } from '../../api/endpoints';
import { formatCurrency } from '../../utils/format';
import { cn } from '../../utils/cn';
import { Combobox, preventDropdownDismissal } from '../../components/ui/Combobox';
import type { TallyLedger } from '../../types';

// ─── Tree types ───────────────────────────────────────────────────────────────

type Row =
  | { kind: 'group'; name: string; count: number }
  | { kind: 'ledger'; ledger: TallyLedger; isLast: boolean };

// ─── Tree connector ───────────────────────────────────────────────────────────

function TreePrefix({ isLast }: { isLast: boolean }) {
  return (
    <span className="font-mono text-slate-300 select-none whitespace-pre text-sm leading-none">
      {isLast ? '└─ ' : '├─ '}
    </span>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const normalise = (s: string) => s.trim().toLowerCase().replace(/\s+/g, ' ');

function buildRows(
  ledgers: TallyLedger[],
  collapsed: Set<string>,
  search: string,
): Row[] {
  const byGroup = new Map<string, { displayName: string; ledgers: TallyLedger[] }>();

  for (const l of ledgers) {
    const gName = l.parent_group?.trim() || 'Other';
    const key = normalise(gName);
    if (!byGroup.has(key)) byGroup.set(key, { displayName: gName, ledgers: [] });
    byGroup.get(key)!.ledgers.push(l);
  }

  const sortedGroups = [...byGroup.values()].sort((a, b) =>
    a.displayName.localeCompare(b.displayName)
  );
  for (const g of sortedGroups) {
    g.ledgers.sort((a, b) => a.name.localeCompare(b.name));
  }

  const expand = search.trim().length > 0;
  const rows: Row[] = [];

  for (const g of sortedGroups) {
    const key = normalise(g.displayName);
    rows.push({ kind: 'group', name: g.displayName, count: g.ledgers.length });
    if (expand || !collapsed.has(key)) {
      g.ledgers.forEach((l, i) =>
        rows.push({ kind: 'ledger', ledger: l, isLast: i === g.ledgers.length - 1 })
      );
    }
  }

  return rows;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const PARTY_GROUPS = ['Sundry Debtors', 'Sundry Creditors'];

// TallyPrime country list (all countries available in TallyPrime)
const TALLY_COUNTRIES = [
  'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola', 'Argentina',
  'Armenia', 'Australia', 'Austria', 'Azerbaijan', 'Bahrain', 'Bangladesh',
  'Belarus', 'Belgium', 'Bhutan', 'Bolivia', 'Bosnia Herzegovina', 'Brazil',
  'Bulgaria', 'Cambodia', 'Cameroon', 'Canada', 'Chile', 'China', 'Colombia',
  'Croatia', 'Cuba', 'Cyprus', 'Czech Republic', 'Denmark', 'Ecuador', 'Egypt',
  'Eritrea', 'Estonia', 'Ethiopia', 'Finland', 'France', 'Germany', 'Ghana',
  'Greece', 'Guatemala', 'Hungary', 'India', 'Indonesia', 'Iran', 'Iraq',
  'Ireland', 'Israel', 'Italy', 'Japan', 'Jordan', 'Kazakhstan', 'Kenya',
  'Kuwait', 'Kyrgyzstan', 'Latvia', 'Lebanon', 'Libya', 'Lithuania',
  'Luxembourg', 'Malaysia', 'Maldives', 'Malta', 'Mexico', 'Moldova',
  'Mongolia', 'Morocco', 'Myanmar', 'Nepal', 'Netherlands', 'New Zealand',
  'Nigeria', 'Norway', 'Oman', 'Pakistan', 'Palestine', 'Panama', 'Peru',
  'Philippines', 'Poland', 'Portugal', 'Qatar', 'Romania', 'Russia',
  'Saudi Arabia', 'Serbia', 'Singapore', 'Slovakia', 'Slovenia',
  'South Africa', 'South Korea', 'Spain', 'Sri Lanka', 'Sweden', 'Switzerland',
  'Syria', 'Taiwan', 'Tajikistan', 'Tanzania', 'Thailand', 'Tunisia', 'Turkey',
  'Turkmenistan', 'Uganda', 'Ukraine', 'United Arab Emirates', 'United Kingdom',
  'United States', 'Uruguay', 'Uzbekistan', 'Venezuela', 'Vietnam', 'Yemen',
  'Zimbabwe',
];

// States/provinces per country (TallyPrime predefined lists)
const COUNTRY_STATES: Record<string, string[]> = {
  'India': [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka',
    'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram',
    'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu',
    'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
    'Andaman and Nicobar Islands', 'Chandigarh',
    'Dadra & Nagar Haveli and Daman & Diu', 'Delhi',
    'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
  ],
  'United States': [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
    'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
    'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey',
    'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
    'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina',
    'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia',
    'Washington', 'West Virginia', 'Wisconsin', 'Wyoming', 'District of Columbia',
  ],
  'Australia': [
    'Australian Capital Territory', 'New South Wales', 'Northern Territory',
    'Queensland', 'South Australia', 'Tasmania', 'Victoria', 'Western Australia',
  ],
  'Canada': [
    'Alberta', 'British Columbia', 'Manitoba', 'New Brunswick',
    'Newfoundland and Labrador', 'Northwest Territories', 'Nova Scotia',
    'Nunavut', 'Ontario', 'Prince Edward Island', 'Quebec', 'Saskatchewan',
    'Yukon',
  ],
  'United Arab Emirates': [
    'Abu Dhabi', 'Ajman', 'Dubai', 'Fujairah',
    'Ras Al Khaimah', 'Sharjah', 'Umm Al Quwain',
  ],
  'United Kingdom': ['England', 'Northern Ireland', 'Scotland', 'Wales'],
};

const TALLY_GROUPS = [
  'Sundry Debtors', 'Sundry Creditors', 'Bank Accounts', 'Cash-in-Hand',
  'Capital Account', 'Current Assets', 'Current Liabilities', 'Fixed Assets',
  'Sales Accounts', 'Purchase Accounts', 'Direct Expenses', 'Indirect Expenses',
  'Direct Incomes', 'Indirect Incomes', 'Loans & Advances (Asset)',
  'Loans (Liability)', 'Duties & Taxes', 'Provisions',
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LedgersPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [initialized, setInitialized] = useState(false);

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<TallyLedger | null>(null);
  const [deleteItem, setDeleteItem] = useState<TallyLedger | null>(null);

  const [formName, setFormName] = useState('');
  const [formGroup, setFormGroup] = useState('Sundry Debtors');
  const [formBalance, setFormBalance] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formPhone, setFormPhone] = useState('');
  const [formAddress, setFormAddress] = useState('');
  const [formCountry, setFormCountry] = useState('');
  const [formState, setFormState] = useState('');
  const [formGstin, setFormGstin] = useState('');

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ledgers-tree'],
    queryFn: () => managementApi.ledgers({ page_size: 500 }),
    refetchInterval: 5000,
  });

  const allLedgers: TallyLedger[] = data?.items ?? [];

  const filteredLedgers = useMemo(() => {
    if (!search.trim()) return allLedgers;
    const q = search.toLowerCase();
    return allLedgers.filter(l =>
      l.name.toLowerCase().includes(q) ||
      (l.parent_group || '').toLowerCase().includes(q)
    );
  }, [allLedgers, search]);

  const allGroupKeys = useMemo(
    () => [...new Set(allLedgers.map(l => normalise(l.parent_group?.trim() || 'Other')))],
    [allLedgers]
  );

  // Collapse all groups on first data load
  useEffect(() => {
    if (!initialized && allGroupKeys.length > 0) {
      setCollapsed(new Set(allGroupKeys));
      setInitialized(true);
    }
  }, [allGroupKeys, initialized]);

  const rows = useMemo(
    () => buildRows(filteredLedgers, collapsed, search),
    [filteredLedgers, collapsed, search]
  );

  const toggle = (groupName: string) => {
    const key = normalise(groupName);
    setCollapsed(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const expandAll = () => setCollapsed(new Set());
  const collapseAll = () => setCollapsed(new Set(allGroupKeys));

  // ── Mutations ─────────────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: () => managementApi.createLedger({
      name: formName.trim(),
      parent_group: formGroup,
      opening_balance: formBalance ? parseFloat(formBalance) : 0,
    }),
    onSuccess: () => {
      toast({ title: 'Ledger created', description: 'Queued for TallyPrime sync.' });
      qc.invalidateQueries({ queryKey: ['ledgers-tree'] });
      setShowCreate(false);
      resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed to create ledger', variant: 'destructive' }),
  });

  const isPartyGroup = PARTY_GROUPS.includes(formGroup);

  const updateMut = useMutation({
    mutationFn: () => managementApi.updateLedger(editItem!.id, {
      name: formName.trim() || undefined,
      parent_group: formGroup || undefined,
      opening_balance: formBalance ? parseFloat(formBalance) : undefined,
      ...(isPartyGroup ? {
        email: formEmail || undefined,
        phone: formPhone || undefined,
        address: formAddress || undefined,
        country: formCountry || undefined,
        state: formState || undefined,
        gstin: formGstin || undefined,
      } : {}),
    }),
    onSuccess: () => {
      toast({ title: 'Ledger updated' });
      qc.invalidateQueries({ queryKey: ['ledgers-tree'] });
      setEditItem(null);
      resetForm();
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Update failed', variant: 'destructive' }),
  });

  const deleteMut = useMutation({
    mutationFn: () => managementApi.deleteLedger(deleteItem!.id),
    onSuccess: (res: { status?: string; message?: string }) => {
      toast({ title: res.status === 'pending' ? 'Delete queued' : 'Deleted', description: res.message });
      qc.invalidateQueries({ queryKey: ['ledgers-tree'] });
      setDeleteItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast({ title: 'Error', description: e.response?.data?.detail || 'Delete failed', variant: 'destructive' }),
  });

  function resetForm() {
    setFormName(''); setFormGroup('Sundry Debtors'); setFormBalance('');
    setFormEmail(''); setFormPhone(''); setFormAddress('');
    setFormCountry(''); setFormState(''); setFormGstin('');
  }

  function openEdit(l: TallyLedger) {
    setFormName(l.name);
    setFormGroup(l.parent_group || 'Sundry Debtors');
    setFormBalance(l.opening_balance != null ? String(l.opening_balance) : '');
    setFormEmail(l.email || '');
    setFormPhone(l.phone || '');
    setFormAddress(l.address || '');
    setFormCountry(l.country || '');
    setFormState(l.state || '');
    setFormGstin(l.gstin || '');
    setEditItem(l);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <BookOpen className="w-6 h-6 text-indigo-600" /> Ledgers
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {allLedgers.length} ledger{allLedgers.length !== 1 ? 's' : ''} · Grouped by account type
          </p>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="gap-2">
          <Plus className="w-4 h-4" /> New Ledger
        </Button>
      </div>

      {/* Search + controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <Input
            placeholder="Search ledgers or groups…"
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
      </div>

      {/* Tree table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-9 w-full" style={{ marginLeft: (i % 2) * 20 }} />)}
            </div>
          ) : isError ? (
            <div className="flex items-center gap-2 p-6 text-red-600">
              <AlertCircle className="w-5 h-5" /> Failed to load ledgers.
            </div>
          ) : rows.length === 0 ? (
            <div className="text-center py-14 text-slate-400">
              {search ? `No ledgers matching "${search}"` : 'No ledgers yet. Create one or sync from TallyPrime.'}
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Hierarchy</th>
                  <th className="px-4 py-3 text-right w-36">Opening Balance</th>
                  <th className="px-4 py-3 text-center w-24">Sync</th>
                  <th className="px-4 py-3 text-right w-20">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => {
                  // ── Group header row ───────────────────────────────────────
                  if (row.kind === 'group') {
                    const key = normalise(row.name);
                    const isCol = collapsed.has(key);
                    return (
                      <tr key={`g-${row.name}-${i}`} className="border-b bg-indigo-50/40 hover:bg-indigo-50/60 cursor-pointer select-none" onClick={() => toggle(row.name)}>
                        <td className="px-3 py-2" colSpan={4}>
                          <div className="flex items-center gap-1">
                            <button
                              className="p-0.5 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-100 shrink-0 pointer-events-none"
                            >
                              {isCol
                                ? <ChevronRight className="w-3.5 h-3.5" />
                                : <ChevronDown className="w-3.5 h-3.5" />}
                            </button>
                            <Layers className="w-4 h-4 text-indigo-400 shrink-0 ml-0.5" />
                            <span className="font-bold text-slate-800 ml-1.5">{row.name}</span>
                            <span className="ml-2 text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full font-semibold shrink-0">
                              {row.count}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  }

                  // ── Ledger row ─────────────────────────────────────────────
                  if (row.kind === 'ledger') {
                    const l = row.ledger;
                    return (
                      <tr key={`l-${l.id}`} className="border-b hover:bg-slate-50/80 group">
                        <td className="px-3 py-2">
                          <div className="flex items-center">
                            <TreePrefix isLast={row.isLast} />
                            <BookOpen className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                            <span className="ml-1.5 font-medium text-slate-800 text-sm">{l.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-xs text-right text-slate-600">
                          {formatCurrency(l.opening_balance)}
                        </td>
                        <td className="px-4 py-2 text-center">
                          <SyncBadge status={l.tally_sync_status} source={l.source} />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className={cn('flex items-center justify-end gap-0.5', 'opacity-0 group-hover:opacity-100 transition-opacity')}>
                            <button
                              onClick={() => openEdit(l)}
                              className="p-1.5 rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700"
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
                    );
                  }

                  return null;
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Ledger</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Name *</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} placeholder="e.g. HDFC Bank" className="mt-1" />
            </div>
            <div>
              <Label>Parent Group *</Label>
              <select
                value={formGroup}
                onChange={e => setFormGroup(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {TALLY_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Opening Balance</Label>
              <Input type="number" value={formBalance} onChange={e => setFormBalance(e.target.value)} placeholder="0" className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={() => createMut.mutate()} disabled={!formName.trim() || createMut.isPending}>
              {createMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Create Ledger
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editItem} onOpenChange={() => setEditItem(null)}>
        <DialogContent className={isPartyGroup ? 'max-w-lg' : 'max-w-md'} onPointerDownOutside={preventDropdownDismissal}>
          <DialogHeader><DialogTitle>Edit Ledger</DialogTitle></DialogHeader>
          <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            <div>
              <Label>Name</Label>
              <Input value={formName} onChange={e => setFormName(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label>Parent Group</Label>
              <select
                value={formGroup}
                onChange={e => setFormGroup(e.target.value)}
                className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {TALLY_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>
            <div>
              <Label>Opening Balance</Label>
              <Input type="number" value={formBalance} onChange={e => setFormBalance(e.target.value)} className="mt-1" />
            </div>

            {/* Party fields — only for Sundry Debtors / Creditors */}
            {isPartyGroup && (
              <>
                <div className="border-t pt-3 mt-1 space-y-3">
                  <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
                    Party / Contact Details
                  </p>

                  {/* Email + Phone */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Email</Label>
                      <Input
                        type="email"
                        value={formEmail}
                        onChange={e => setFormEmail(e.target.value)}
                        placeholder="customer@example.com"
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label>Phone</Label>
                      <Input
                        value={formPhone}
                        onChange={e => setFormPhone(e.target.value)}
                        placeholder="+91 98765 43210"
                        className="mt-1"
                      />
                    </div>
                  </div>

                  {/* Address */}
                  <div>
                    <Label>Address</Label>
                    <Input
                      value={formAddress}
                      onChange={e => setFormAddress(e.target.value)}
                      placeholder="Street address"
                      className="mt-1"
                    />
                  </div>

                  {/* Country */}
                  <div>
                    <Label>Country</Label>
                    <Combobox
                      options={TALLY_COUNTRIES}
                      value={formCountry}
                      onChange={v => { setFormCountry(v); setFormState(''); setFormGstin(''); }}
                      placeholder="Search country…"
                      clearLabel="— No country —"
                      className="mt-1"
                    />
                  </div>

                  {/* State — depends on selected country */}
                  <div>
                    <Label>State</Label>
                    {!formCountry ? (
                      <p className="mt-1 text-xs text-slate-400 italic px-3 py-2 border border-dashed border-slate-200 rounded-md">
                        Please select a country first
                      </p>
                    ) : (
                      <Combobox
                        options={COUNTRY_STATES[formCountry] ?? []}
                        value={formState}
                        onChange={setFormState}
                        placeholder={
                          COUNTRY_STATES[formCountry]
                            ? 'Search state…'
                            : 'No predefined states for this country'
                        }
                        clearLabel="— No state —"
                        className="mt-1"
                      />
                    )}
                  </div>

                  {/* GSTIN */}
                  <div>
                    <Label>GSTIN</Label>
                    <Input
                      value={formGstin}
                      onChange={e => setFormGstin(e.target.value.toUpperCase())}
                      placeholder="22AAAAA0000A1Z5"
                      maxLength={15}
                      className="mt-1 font-mono tracking-wider"
                    />
                    <p className="text-xs text-slate-400 mt-1">15-character GST Identification Number</p>
                  </div>
                </div>
              </>
            )}

            {editItem?.tally_sync_status === 'synced' && (
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-100 p-2 rounded">
                This ledger is synced to TallyPrime. Changes will be queued for sync.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>Cancel</Button>
            <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={!!deleteItem} onOpenChange={() => setDeleteItem(null)}>
        <DialogContent className="max-w-sm">
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
