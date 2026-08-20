import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LabelList,
} from 'recharts';
import { Search, TrendingUp, TrendingDown, DollarSign, Package, Users, Building2, Wallet } from 'lucide-react';
import { dashboardApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Skeleton } from '../../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import { formatCurrency, formatCompactCurrency } from '../../utils/format';
import { cn } from '../../utils/cn';

// ─── Types ────────────────────────────────────────────────────────────────────

interface LedgerEntry { name: string; group: string; balance: number }
interface PartyEntry  { name: string; group: string; balance: number; gstin: string; state: string }
interface StockGroup  { group: string; items: number; value: number; qty: number }
interface StockItem   { name: string; group: string; category: string; unit: string; rate: number; qty: number; value: number }

interface TallyKPI {
  income:      { total: number; by_group: Array<{ name: string; amount: number }> };
  expenses:    { total: number; by_group: Array<{ name: string; amount: number }> };
  net_profit:  number;
  receivables: { total: number };
  payables:    { total: number };
  cash_bank:   { total: number; cash: number; bank: number };
  assets:      number;
  liabilities: number;
  inventory:   { total_value: number; item_count: number };
}

interface TallyAnalytics {
  income_ledgers:    LedgerEntry[];
  expense_ledgers:   LedgerEntry[];
  debtor_ledgers:    PartyEntry[];
  creditor_ledgers:  PartyEntry[];
  cash_ledgers:      LedgerEntry[];
  bank_ledgers:      LedgerEntry[];
  asset_ledgers:     LedgerEntry[];
  liability_ledgers: LedgerEntry[];
  stock_by_group:    StockGroup[];
  stock_list:        StockItem[];
}

// ─── Colours ──────────────────────────────────────────────────────────────────

const PIE_INCOME  = ['#10B981', '#059669', '#047857', '#34D399', '#6EE7B7', '#A7F3D0'];
const PIE_EXPENSE = ['#F43F5E', '#E11D48', '#FB7185', '#FDA4AF', '#FCA5A5', '#FEE2E2'];

// ─── Shared tooltip ───────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm min-w-[160px]">
      {label && <p className="font-medium text-slate-600 mb-1.5 text-xs">{label}</p>}
      {payload.map(p => (
        <p key={p.name} className="font-bold" style={{ color: p.color }}>
          {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

// ─── KPI Summary Card ────────────────────────────────────────────────────────

function SummaryCard({ title, value, icon: Icon, color, loading }: {
  title: string; value: number; icon: React.ElementType; color: string; loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{title}</p>
            {loading ? (
              <Skeleton className="h-7 w-24 mt-1.5" />
            ) : (
              <p className="text-xl font-bold text-slate-900 mt-1">{formatCompactCurrency(value)}</p>
            )}
          </div>
          <div className={cn('w-9 h-9 rounded-xl flex items-center justify-center shrink-0', color)}>
            <Icon className="w-4 h-4 text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Ledger Table ─────────────────────────────────────────────────────────────

function LedgerTable({ title, rows, total, color, loading, emptyText }: {
  title: string; rows: LedgerEntry[]; total: number;
  color: string; loading: boolean; emptyText: string;
}) {
  const maxBal = Math.max(...rows.map(r => r.balance), 1);
  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold text-slate-800">{title}</CardTitle>
          {!loading && total > 0 && (
            <span className={cn('text-xs font-bold px-2 py-0.5 rounded-full', color)}>
              {formatCompactCurrency(total)}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="p-4 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-8" />)}</div>
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10 px-4">{emptyText}</p>
        ) : (
          <div className="divide-y divide-slate-50">
            {rows.map((row, idx) => (
              <div key={idx} className="px-4 py-2.5 hover:bg-slate-50 transition-colors">
                <div className="flex items-center justify-between mb-1">
                  <div className="min-w-0 flex-1 pr-3">
                    <p className="text-xs font-medium text-slate-800 truncate">{row.name}</p>
                    {row.group && (
                      <p className="text-[10px] text-slate-400 truncate">{row.group}</p>
                    )}
                  </div>
                  <p className="text-xs font-bold text-slate-900 shrink-0">{formatCompactCurrency(row.balance)}</p>
                </div>
                <div className="h-1 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full', color.includes('emerald') ? 'bg-emerald-400' : 'bg-rose-400')}
                    style={{ width: `${(row.balance / maxBal) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Party Table ──────────────────────────────────────────────────────────────

function PartyTable({ rows, total, loading, emptyText }: {
  rows: PartyEntry[]; total: number; loading: boolean; emptyText: string;
}) {
  const [search, setSearch] = useState('');
  const filtered = rows.filter(r =>
    r.name.toLowerCase().includes(search.toLowerCase()) ||
    (r.gstin && r.gstin.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div>
      {/* Search + total */}
      <div className="flex items-center gap-3 mb-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name or GSTIN…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
        </div>
        {!loading && (
          <span className="text-xs font-bold text-slate-600 whitespace-nowrap">
            {filtered.length} / {rows.length} · {formatCompactCurrency(total)}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-10" />)}</div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-slate-400 text-center py-12">{search ? 'No matches found' : emptyText}</p>
      ) : (
        <div className="border border-slate-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">#</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Name</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden sm:table-cell">State</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden md:table-cell">GSTIN</th>
                <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Balance</th>
                <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden sm:table-cell">Share</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((row, idx) => (
                <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-4 py-2.5 text-xs text-slate-400">{idx + 1}</td>
                  <td className="px-4 py-2.5 font-medium text-slate-800 text-xs">{row.name}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-500 hidden sm:table-cell">{row.state || '—'}</td>
                  <td className="px-4 py-2.5 text-xs text-slate-400 font-mono hidden md:table-cell">{row.gstin || '—'}</td>
                  <td className="px-4 py-2.5 text-right font-bold text-xs text-slate-900">{formatCompactCurrency(row.balance)}</td>
                  <td className="px-4 py-2.5 text-right text-xs text-slate-400 hidden sm:table-cell">
                    {total > 0 ? `${((row.balance / total) * 100).toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Analytics Page ───────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [stockSearch, setStockSearch] = useState('');
  const [partyView, setPartyView] = useState<'debtors' | 'creditors'>('debtors');

  const { data: kpiData, isLoading: kpiLoading } = useQuery({
    queryKey: ['dashboard', 'tally-kpi'],
    queryFn: dashboardApi.tallyKpi,
    staleTime: 60_000,
  });

  const { data: analyticsData, isLoading: analyticsLoading } = useQuery({
    queryKey: ['dashboard', 'tally-analytics'],
    queryFn: dashboardApi.tallyAnalytics,
    staleTime: 60_000,
  });

  const kpi       = kpiData       as TallyKPI       | undefined;
  const analytics = analyticsData as TallyAnalytics | undefined;

  // Overview chart data
  const incomeGroupChart  = (kpi?.income.by_group ?? []).slice(0, 6).map(g => ({ name: g.name, value: g.amount }));
  const expenseGroupChart = (kpi?.expenses.by_group ?? []).slice(0, 6).map(g => ({ name: g.name, value: g.amount }));

  // Stock
  const filteredStock = (analytics?.stock_list ?? []).filter(s =>
    s.name.toLowerCase().includes(stockSearch.toLowerCase()) ||
    s.group.toLowerCase().includes(stockSearch.toLowerCase())
  );

  const stockBarData = (analytics?.stock_by_group ?? []).slice(0, 10).map(g => ({
    name: g.group.length > 18 ? g.group.slice(0, 18) + '…' : g.group,
    Value: g.value,
    Items: g.items,
  }));

  // Totals for balance sheet
  const assetTotal    = (analytics?.asset_ledgers    ?? []).reduce((s, l) => s + l.balance, 0);
  const liabTotal     = (analytics?.liability_ledgers ?? []).reduce((s, l) => s + l.balance, 0);
  const cashTotal     = (analytics?.cash_ledgers     ?? []).reduce((s, l) => s + l.balance, 0);
  const bankTotal     = (analytics?.bank_ledgers     ?? []).reduce((s, l) => s + l.balance, 0);

  const loading = kpiLoading || analyticsLoading;

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Analytics</h1>
          <p className="text-xs text-slate-400 mt-0.5">All data sourced exclusively from TallyPrime ledger balances</p>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs font-semibold rounded-full border border-indigo-100">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
          TallyPrime
        </span>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="flex h-auto flex-wrap gap-1 bg-slate-100 p-1 w-full justify-start">
          <TabsTrigger value="overview"   className="text-xs">Overview</TabsTrigger>
          <TabsTrigger value="pl"         className="text-xs">Income & Expenses</TabsTrigger>
          <TabsTrigger value="parties"    className="text-xs">Debtors & Creditors</TabsTrigger>
          <TabsTrigger value="balance"    className="text-xs">Balance Sheet</TabsTrigger>
          <TabsTrigger value="inventory"  className="text-xs">Inventory</TabsTrigger>
        </TabsList>

        {/* ── Overview ───────────────────────────────────────────────────── */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          {/* KPI Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <SummaryCard title="Total Income"    value={kpi?.income.total ?? 0}     icon={TrendingUp}   color="bg-emerald-500" loading={kpiLoading} />
            <SummaryCard title="Total Expenses"  value={kpi?.expenses.total ?? 0}   icon={TrendingDown} color="bg-rose-500"    loading={kpiLoading} />
            <SummaryCard title="Net Profit"      value={kpi?.net_profit ?? 0}       icon={DollarSign}   color="bg-indigo-600"  loading={kpiLoading} />
            <SummaryCard title="Cash & Bank"     value={kpi?.cash_bank.total ?? 0}  icon={Wallet}       color="bg-cyan-500"    loading={kpiLoading} />
          </div>

          {/* Income vs Expense donut charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-5 bg-emerald-500 rounded-sm" />
                  <CardTitle className="text-sm font-semibold text-slate-800">Income Breakdown</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {kpiLoading ? <Skeleton className="h-52" /> : incomeGroupChart.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-16">No income data</p>
                ) : (
                  <div className="flex items-center gap-4">
                    <ResponsiveContainer width="50%" height={180}>
                      <PieChart>
                        <Pie data={incomeGroupChart} cx="50%" cy="50%" innerRadius={40} outerRadius={70}
                          paddingAngle={2} dataKey="value" nameKey="name">
                          {incomeGroupChart.map((_, i) => (
                            <Cell key={i} fill={PIE_INCOME[i % PIE_INCOME.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex-1 space-y-2 min-w-0">
                      {incomeGroupChart.map((item, i) => {
                        const total = incomeGroupChart.reduce((s, g) => s + g.value, 0);
                        return (
                          <div key={i} className="flex items-center gap-2">
                            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIE_INCOME[i % PIE_INCOME.length] }} />
                            <span className="text-xs text-slate-600 truncate flex-1">{item.name}</span>
                            <span className="text-xs font-bold text-slate-700 shrink-0">
                              {total > 0 ? ((item.value / total) * 100).toFixed(1) : 0}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-5 bg-rose-500 rounded-sm" />
                  <CardTitle className="text-sm font-semibold text-slate-800">Expense Breakdown</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                {kpiLoading ? <Skeleton className="h-52" /> : expenseGroupChart.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-16">No expense data</p>
                ) : (
                  <div className="flex items-center gap-4">
                    <ResponsiveContainer width="50%" height={180}>
                      <PieChart>
                        <Pie data={expenseGroupChart} cx="50%" cy="50%" innerRadius={40} outerRadius={70}
                          paddingAngle={2} dataKey="value" nameKey="name">
                          {expenseGroupChart.map((_, i) => (
                            <Cell key={i} fill={PIE_EXPENSE[i % PIE_EXPENSE.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex-1 space-y-2 min-w-0">
                      {expenseGroupChart.map((item, i) => {
                        const total = expenseGroupChart.reduce((s, g) => s + g.value, 0);
                        return (
                          <div key={i} className="flex items-center gap-2">
                            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIE_EXPENSE[i % PIE_EXPENSE.length] }} />
                            <span className="text-xs text-slate-600 truncate flex-1">{item.name}</span>
                            <span className="text-xs font-bold text-slate-700 shrink-0">
                              {total > 0 ? ((item.value / total) * 100).toFixed(1) : 0}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Financial Health Ratios */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-slate-800">Financial Snapshot</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  {
                    label: 'Profit Margin',
                    value: kpi && kpi.income.total > 0
                      ? `${((kpi.net_profit / kpi.income.total) * 100).toFixed(1)}%`
                      : '—',
                    color: (kpi?.net_profit ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600',
                  },
                  {
                    label: 'Receivables / Income',
                    value: kpi && kpi.income.total > 0
                      ? `${((kpi.receivables.total / kpi.income.total) * 100).toFixed(1)}%`
                      : '—',
                    color: 'text-amber-600',
                  },
                  {
                    label: 'Payables / Expenses',
                    value: kpi && kpi.expenses.total > 0
                      ? `${((kpi.payables.total / kpi.expenses.total) * 100).toFixed(1)}%`
                      : '—',
                    color: 'text-violet-600',
                  },
                  {
                    label: 'Debt / Asset Ratio',
                    value: kpi && kpi.assets > 0
                      ? `${((kpi.liabilities / kpi.assets) * 100).toFixed(1)}%`
                      : '—',
                    color: 'text-indigo-600',
                  },
                ].map(item => (
                  <div key={item.label} className="text-center p-3 rounded-lg bg-slate-50 border border-slate-100">
                    <p className="text-xs text-slate-400 mb-1">{item.label}</p>
                    {kpiLoading
                      ? <Skeleton className="h-6 w-16 mx-auto" />
                      : <p className={cn('text-lg font-bold', item.color)}>{item.value}</p>}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Income & Expenses ──────────────────────────────────────────── */}
        <TabsContent value="pl" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <LedgerTable
              title="Income Ledgers"
              rows={analytics?.income_ledgers ?? []}
              total={kpi?.income.total ?? 0}
              color="text-emerald-700 bg-emerald-50"
              loading={loading}
              emptyText="No income ledgers found"
            />
            <LedgerTable
              title="Expense Ledgers"
              rows={analytics?.expense_ledgers ?? []}
              total={kpi?.expenses.total ?? 0}
              color="text-rose-700 bg-rose-50"
              loading={loading}
              emptyText="No expense ledgers found"
            />
          </div>
        </TabsContent>

        {/* ── Debtors & Creditors ────────────────────────────────────────── */}
        <TabsContent value="parties" className="mt-4 space-y-4">
          {/* Toggle */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg w-fit">
            <button
              onClick={() => setPartyView('debtors')}
              className={cn(
                'flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all',
                partyView === 'debtors'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700',
              )}
            >
              <Users className="w-3.5 h-3.5" />
              Debtors
              {!loading && (
                <span className="bg-amber-100 text-amber-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {analytics?.debtor_ledgers.length ?? 0}
                </span>
              )}
            </button>
            <button
              onClick={() => setPartyView('creditors')}
              className={cn(
                'flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all',
                partyView === 'creditors'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700',
              )}
            >
              <Building2 className="w-3.5 h-3.5" />
              Creditors
              {!loading && (
                <span className="bg-violet-100 text-violet-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                  {analytics?.creditor_ledgers.length ?? 0}
                </span>
              )}
            </button>
          </div>

          {partyView === 'debtors' ? (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-slate-800">Sundry Debtors (Receivables)</CardTitle>
                  {!loading && (
                    <span className="text-xs font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                      {formatCompactCurrency(kpi?.receivables.total ?? 0)} total
                    </span>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <PartyTable
                  rows={analytics?.debtor_ledgers ?? []}
                  total={kpi?.receivables.total ?? 0}
                  loading={loading}
                  emptyText="No debtors found"
                />
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-slate-800">Sundry Creditors (Payables)</CardTitle>
                  {!loading && (
                    <span className="text-xs font-bold text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">
                      {formatCompactCurrency(kpi?.payables.total ?? 0)} total
                    </span>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <PartyTable
                  rows={analytics?.creditor_ledgers ?? []}
                  total={kpi?.payables.total ?? 0}
                  loading={loading}
                  emptyText="No creditors found"
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Balance Sheet ──────────────────────────────────────────────── */}
        <TabsContent value="balance" className="mt-4 space-y-4">
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Fixed Assets', value: assetTotal,     color: 'bg-emerald-50 border-emerald-200 text-emerald-700', loading },
              { label: 'Liabilities',  value: liabTotal,      color: 'bg-rose-50 border-rose-200 text-rose-700',         loading },
              { label: 'Cash in Hand', value: cashTotal,      color: 'bg-cyan-50 border-cyan-200 text-cyan-700',          loading },
              { label: 'Bank Balance', value: bankTotal,      color: 'bg-sky-50 border-sky-200 text-sky-700',             loading },
            ].map(item => (
              <div key={item.label} className={cn('p-4 rounded-xl border', item.color)}>
                <p className="text-[10px] font-semibold uppercase tracking-wider opacity-70">{item.label}</p>
                {item.loading
                  ? <Skeleton className="h-6 w-20 mt-1.5" />
                  : <p className="text-lg font-bold mt-1">{formatCompactCurrency(item.value)}</p>}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Assets */}
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-slate-800">Assets</CardTitle>
                  {!loading && (
                    <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      {formatCompactCurrency(assetTotal)}
                    </span>
                  )}
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="p-4 space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-9" />)}</div>
                ) : (analytics?.asset_ledgers ?? []).length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-10 px-4">No asset ledgers found</p>
                ) : (
                  <div className="divide-y divide-slate-50">
                    {(analytics?.asset_ledgers ?? []).map((l, idx) => (
                      <div key={idx} className="flex items-center justify-between px-4 py-2.5 hover:bg-slate-50">
                        <div className="min-w-0 flex-1 pr-3">
                          <p className="text-xs font-medium text-slate-800 truncate">{l.name}</p>
                          {l.group && <p className="text-[10px] text-slate-400">{l.group}</p>}
                        </div>
                        <p className="text-xs font-bold text-emerald-700 shrink-0">{formatCompactCurrency(l.balance)}</p>
                      </div>
                    ))}
                    <div className="flex items-center justify-between px-4 py-2.5 bg-emerald-50">
                      <p className="text-xs font-bold text-slate-700">Total Assets</p>
                      <p className="text-xs font-bold text-emerald-700">{formatCompactCurrency(assetTotal)}</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Liabilities */}
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-slate-800">Liabilities</CardTitle>
                  {!loading && (
                    <span className="text-xs font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">
                      {formatCompactCurrency(liabTotal)}
                    </span>
                  )}
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="p-4 space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-9" />)}</div>
                ) : (analytics?.liability_ledgers ?? []).length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-10 px-4">No liability ledgers found</p>
                ) : (
                  <div className="divide-y divide-slate-50">
                    {(analytics?.liability_ledgers ?? []).map((l, idx) => (
                      <div key={idx} className="flex items-center justify-between px-4 py-2.5 hover:bg-slate-50">
                        <div className="min-w-0 flex-1 pr-3">
                          <p className="text-xs font-medium text-slate-800 truncate">{l.name}</p>
                          {l.group && <p className="text-[10px] text-slate-400">{l.group}</p>}
                        </div>
                        <p className="text-xs font-bold text-rose-700 shrink-0">{formatCompactCurrency(l.balance)}</p>
                      </div>
                    ))}
                    <div className="flex items-center justify-between px-4 py-2.5 bg-rose-50">
                      <p className="text-xs font-bold text-slate-700">Total Liabilities</p>
                      <p className="text-xs font-bold text-rose-700">{formatCompactCurrency(liabTotal)}</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Net worth banner */}
          {!loading && (assetTotal > 0 || liabTotal > 0) && (
            <div className={cn(
              'p-4 rounded-xl border flex items-center justify-between',
              (assetTotal - liabTotal) >= 0
                ? 'bg-indigo-50 border-indigo-200'
                : 'bg-orange-50 border-orange-200',
            )}>
              <p className="text-sm font-semibold text-slate-700">Net Worth (Assets − Liabilities)</p>
              <p className={cn(
                'text-xl font-bold',
                (assetTotal - liabTotal) >= 0 ? 'text-indigo-700' : 'text-orange-700',
              )}>
                {formatCompactCurrency(assetTotal - liabTotal)}
              </p>
            </div>
          )}
        </TabsContent>

        {/* ── Inventory ──────────────────────────────────────────────────── */}
        <TabsContent value="inventory" className="mt-4 space-y-4">
          {/* Summary cards */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="p-4 rounded-xl bg-indigo-50 border border-indigo-100">
              <p className="text-[10px] font-semibold text-indigo-500 uppercase tracking-wider">Total Items</p>
              {analyticsLoading ? <Skeleton className="h-7 w-16 mt-1" /> : (
                <p className="text-2xl font-bold text-indigo-700 mt-1">{analytics?.stock_list.length ?? 0}</p>
              )}
            </div>
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-100">
              <p className="text-[10px] font-semibold text-emerald-500 uppercase tracking-wider">Inventory Value</p>
              {analyticsLoading ? <Skeleton className="h-7 w-24 mt-1" /> : (
                <p className="text-2xl font-bold text-emerald-700 mt-1">{formatCompactCurrency(kpi?.inventory.total_value ?? 0)}</p>
              )}
            </div>
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
              <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Stock Groups</p>
              {analyticsLoading ? <Skeleton className="h-7 w-10 mt-1" /> : (
                <p className="text-2xl font-bold text-slate-700 mt-1">{analytics?.stock_by_group.length ?? 0}</p>
              )}
            </div>
          </div>

          {/* Stock by Group chart */}
          {stockBarData.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-slate-800">Inventory Value by Group</CardTitle>
              </CardHeader>
              <CardContent>
                {analyticsLoading ? <Skeleton className="h-48" /> : (
                  <ResponsiveContainer width="100%" height={stockBarData.length > 5 ? 220 : 160}>
                    <BarChart
                      layout="vertical"
                      data={stockBarData}
                      margin={{ top: 2, right: 80, left: 4, bottom: 2 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }}
                        tickFormatter={v => `₹${(v / 100000).toFixed(0)}L`} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#475569' }}
                        width={120} axisLine={false} tickLine={false} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: '#eef2ff' }} />
                      <Bar dataKey="Value" fill="#6366F1" radius={[0, 4, 4, 0]}>
                        <LabelList
                          dataKey="Value" position="right"
                          style={{ fontSize: 10, fill: '#4F46E5', fontWeight: 600 }}
                          formatter={(v: unknown) => formatCompactCurrency(Number(v))}
                        />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          )}

          {/* Stock Item Table */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <CardTitle className="text-sm font-semibold text-slate-800">Stock Items</CardTitle>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search items or groups…"
                    value={stockSearch}
                    onChange={e => setStockSearch(e.target.value)}
                    className="pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 w-52"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {analyticsLoading ? (
                <div className="p-4 space-y-3">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-9" />)}</div>
              ) : filteredStock.length === 0 ? (
                <p className="text-sm text-slate-400 text-center py-10">
                  {stockSearch ? 'No matching items' : 'No stock items found'}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">#</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Name</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden sm:table-cell">Group</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden md:table-cell">Unit</th>
                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Rate</th>
                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hidden sm:table-cell">Qty</th>
                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredStock.map((item, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
                          <td className="px-4 py-2.5 text-xs text-slate-400">{idx + 1}</td>
                          <td className="px-4 py-2.5 text-xs font-medium text-slate-800">{item.name}</td>
                          <td className="px-4 py-2.5 text-xs text-slate-500 hidden sm:table-cell">{item.group || '—'}</td>
                          <td className="px-4 py-2.5 text-xs text-slate-500 hidden md:table-cell">{item.unit || '—'}</td>
                          <td className="px-4 py-2.5 text-right text-xs text-slate-700">{formatCompactCurrency(item.rate)}</td>
                          <td className="px-4 py-2.5 text-right text-xs text-slate-700 hidden sm:table-cell">
                            {item.qty.toLocaleString('en-IN')}
                          </td>
                          <td className="px-4 py-2.5 text-right text-xs font-bold text-indigo-700">
                            {formatCompactCurrency(item.value)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
