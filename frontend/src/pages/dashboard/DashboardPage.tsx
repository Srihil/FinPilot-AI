import React, { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp, TrendingDown, DollarSign, Wallet, Users,
  Building2, Package, AlertCircle, Clock, Activity, ArrowUpRight,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LabelList,
} from 'recharts';
import { dashboardApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Skeleton } from '../../components/ui/skeleton';
import { formatCurrency, formatCompactCurrency, formatRelativeTime } from '../../utils/format';
import { cn } from '../../utils/cn';

// ─── Types ────────────────────────────────────────────────────────────────────

type GroupItem  = { name: string; amount: number };
type PartyItem  = { name: string; amount: number };

interface TallyKPI {
  income:      { total: number; by_group: GroupItem[] };
  expenses:    { total: number; by_group: GroupItem[] };
  net_profit:  number;
  receivables: { total: number; top: PartyItem[] };
  payables:    { total: number; top: PartyItem[] };
  cash_bank:   { total: number; cash: number; bank: number };
  assets:      number;
  liabilities: number;
  inventory:   { total_value: number; item_count: number };
  ledger_count: number;
  sync: {
    connected: boolean;
    tally_company: string | null;
    last_sync: string | null;
    pending_jobs: number;
    failed_jobs: number;
  };
}

// ─── Count-up Hook ────────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1300, enabled = true): number {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) return;
    setValue(0);
    if (target === 0) return;
    const start = performance.now();
    const abs = Math.abs(target);
    const sign = target < 0 ? -1 : 1;
    const step = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(abs * eased * sign);
      if (progress < 1) rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, enabled]);

  return value;
}

// ─── Slide-in Hook ───────────────────────────────────────────────────────────

function useSlideIn(delay = 0): boolean {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);
  return visible;
}

// ─── Sync Banner ─────────────────────────────────────────────────────────────

function SyncBanner({ kpi, loading }: { kpi?: TallyKPI; loading: boolean }) {
  if (loading) return <Skeleton className="h-14 rounded-xl" />;
  const sync = kpi?.sync;
  return (
    <div className={cn(
      'flex flex-wrap items-center justify-between gap-3 px-5 py-3 rounded-xl',
      sync?.connected
        ? 'bg-gradient-to-r from-indigo-950 via-slate-900 to-slate-900'
        : 'bg-gradient-to-r from-slate-800 to-slate-900',
    )}>
      <div className="flex items-center gap-4">
        {sync?.connected ? (
          <div className="flex items-center gap-2 text-emerald-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider">Live TallyPrime</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-slate-400">
            <AlertCircle className="w-4 h-4" />
            <span className="text-xs font-medium">Not Connected</span>
          </div>
        )}
        {sync?.tally_company && (
          <span className="text-white font-bold text-sm">{sync.tally_company}</span>
        )}
        {kpi?.ledger_count !== undefined && kpi.ledger_count > 0 && (
          <span className="text-slate-500 text-xs">{kpi.ledger_count} ledgers synced</span>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs">
        {sync?.last_sync && (
          <span className="flex items-center gap-1.5 text-slate-400">
            <Clock className="w-3 h-3" />
            {formatRelativeTime(sync.last_sync)}
          </span>
        )}
        {(sync?.pending_jobs ?? 0) > 0 && (
          <span className="flex items-center gap-1 text-amber-400">
            <Activity className="w-3 h-3 animate-spin" />
            {sync!.pending_jobs} syncing
          </span>
        )}
        {(sync?.failed_jobs ?? 0) > 0 && (
          <span className="text-rose-400">{sync!.failed_jobs} failed</span>
        )}
      </div>
    </div>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({
  title, value, icon: Icon, color, loading, delay = 0,
}: {
  title: string; value: number; icon: React.ElementType;
  color: string; // hex
  loading: boolean; delay?: number;
}) {
  const visible = useSlideIn(delay);
  const animated = useCountUp(value, 1300, !loading && visible);

  return (
    <div
      className={cn(
        'relative rounded-2xl p-4 overflow-hidden cursor-default',
        'border border-slate-100 shadow-sm',
        'hover:shadow-lg hover:-translate-y-0.5 transition-all duration-500',
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-3',
      )}
      style={{ background: `linear-gradient(135deg, ${color}12 0%, #ffffff 65%)` }}
    >
      {/* Soft glow blob */}
      <div
        className="absolute -top-8 -right-8 w-28 h-28 rounded-full blur-2xl pointer-events-none"
        style={{ background: `${color}30` }}
      />

      <div className="relative flex items-start justify-between mb-3">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest leading-none">{title}</p>
        <div
          className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: `${color}20` }}
        >
          <Icon className="w-4 h-4" style={{ color }} />
        </div>
      </div>

      <div className="relative">
        {loading ? (
          <Skeleton className="h-7 w-24" />
        ) : (
          <p className="text-xl font-bold text-slate-900 leading-none">
            {formatCompactCurrency(animated)}
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm min-w-[160px]">
      {label && <p className="font-medium text-slate-600 mb-1.5 text-xs">{label}</p>}
      {payload.map((p) => (
        <p key={p.name} className="font-bold" style={{ color: p.color }}>
          {formatCurrency(p.value)}
        </p>
      ))}
    </div>
  );
}

// ─── Party Progress List ──────────────────────────────────────────────────────

function PartyProgressList({
  title, subtitle, items, barColor, loading, emptyText,
}: {
  title: string; subtitle?: string;
  items: PartyItem[]; barColor: string;
  loading: boolean; emptyText: string;
}) {
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 700);
    return () => clearTimeout(t);
  }, []);

  const maxAmt = Math.max(...items.map(i => i.amount), 1);
  const total  = items.reduce((s, i) => s + i.amount, 0);

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold text-slate-800">{title}</CardTitle>
          {!loading && total > 0 && (
            <span className="text-xs font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full">
              {formatCompactCurrency(total)}
            </span>
          )}
        </div>
        {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-9" />)}
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-10">{emptyText}</p>
        ) : (
          <div className="space-y-3.5">
            {items.map((item, idx) => (
              <div key={idx}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium text-slate-700 truncate pr-2 flex-1">
                    {item.name}
                  </span>
                  <span className="text-xs font-bold text-slate-900 shrink-0">
                    {formatCompactCurrency(item.amount)}
                  </span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all duration-700 ease-out', barColor)}
                    style={{
                      width: animated ? `${(item.amount / maxAmt) * 100}%` : '0%',
                      transitionDelay: `${idx * 70}ms`,
                    }}
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

// ─── Dashboard Page ───────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'tally-kpi'],
    queryFn: dashboardApi.tallyKpi,
    staleTime: 60_000,
  });

  const kpi = data as TallyKPI | undefined;
  const netProfit = kpi?.net_profit ?? 0;
  const isLoss    = netProfit < 0;

  const incomeGroups  = (kpi?.income.by_group ?? []).slice(0, 7).map(g => ({ name: g.name, Amount: g.amount }));
  const expenseGroups = (kpi?.expenses.by_group ?? []).slice(0, 7).map(g => ({ name: g.name, Amount: g.amount }));
  const cashBankData  = [
    { name: 'Cash', value: kpi?.cash_bank.cash ?? 0 },
    { name: 'Bank', value: kpi?.cash_bank.bank ?? 0 },
  ].filter(d => d.value > 0);

  const netWorth = (kpi?.assets ?? 0) - (kpi?.liabilities ?? 0);

  return (
    <div className="space-y-4">
      {/* Sync Banner */}
      <SyncBanner kpi={kpi} loading={isLoading} />

      {/* KPI Cards — 6 across */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard title="Total Income"   value={kpi?.income.total ?? 0}    icon={TrendingUp}                              color="#10B981" loading={isLoading} delay={0}   />
        <KpiCard title="Total Expenses" value={kpi?.expenses.total ?? 0}  icon={TrendingDown}                            color="#F43F5E" loading={isLoading} delay={80}  />
        <KpiCard title="Net Profit"     value={netProfit}                  icon={isLoss ? TrendingDown : DollarSign}      color={isLoss ? '#F43F5E' : '#4F46E5'} loading={isLoading} delay={160} />
        <KpiCard title="Receivables"    value={kpi?.receivables.total ?? 0} icon={Users}                                 color="#F59E0B" loading={isLoading} delay={240} />
        <KpiCard title="Payables"       value={kpi?.payables.total ?? 0}  icon={Building2}                               color="#8B5CF6" loading={isLoading} delay={320} />
        <KpiCard title="Cash & Bank"    value={kpi?.cash_bank.total ?? 0} icon={Wallet}                                  color="#06B6D4" loading={isLoading} delay={400} />
      </div>

      {/* By-Group Breakdown Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Income by Group */}
        <Card>
          <CardHeader className="pb-1">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-5 bg-emerald-500 rounded-sm" />
              <CardTitle className="text-sm font-semibold text-slate-800">Income by Group</CardTitle>
              {!isLoading && kpi && (
                <span className="ml-auto text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                  {formatCompactCurrency(kpi.income.total)}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            {isLoading ? (
              <Skeleton className="h-48" />
            ) : incomeGroups.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-slate-400">
                <TrendingUp className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-sm">No income data synced yet</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={incomeGroups.length > 4 ? 210 : 130}>
                <BarChart
                  layout="vertical"
                  data={incomeGroups}
                  margin={{ top: 2, right: 72, left: 4, bottom: 2 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={v => `₹${(v / 100000).toFixed(0)}L`}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    type="category" dataKey="name"
                    tick={{ fontSize: 11, fill: '#475569' }}
                    width={120} axisLine={false} tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f0fdf4' }} />
                  <Bar dataKey="Amount" fill="#10B981" radius={[0, 4, 4, 0]}>
                    <LabelList
                      dataKey="Amount" position="right"
                      style={{ fontSize: 10, fill: '#059669', fontWeight: 600 }}
                      formatter={(v: unknown) => formatCompactCurrency(Number(v))}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Expense by Group */}
        <Card>
          <CardHeader className="pb-1">
            <div className="flex items-center gap-2">
              <div className="w-1.5 h-5 bg-rose-500 rounded-sm" />
              <CardTitle className="text-sm font-semibold text-slate-800">Expenses by Group</CardTitle>
              {!isLoading && kpi && (
                <span className="ml-auto text-xs font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">
                  {formatCompactCurrency(kpi.expenses.total)}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            {isLoading ? (
              <Skeleton className="h-48" />
            ) : expenseGroups.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-slate-400">
                <TrendingDown className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-sm">No expense data synced yet</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={expenseGroups.length > 4 ? 210 : 130}>
                <BarChart
                  layout="vertical"
                  data={expenseGroups}
                  margin={{ top: 2, right: 72, left: 4, bottom: 2 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickFormatter={v => `₹${(v / 100000).toFixed(0)}L`}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    type="category" dataKey="name"
                    tick={{ fontSize: 11, fill: '#475569' }}
                    width={120} axisLine={false} tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: '#fff1f2' }} />
                  <Bar dataKey="Amount" fill="#F43F5E" radius={[0, 4, 4, 0]}>
                    <LabelList
                      dataKey="Amount" position="right"
                      style={{ fontSize: 10, fill: '#e11d48', fontWeight: 600 }}
                      formatter={(v: unknown) => formatCompactCurrency(Number(v))}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top Debtors & Creditors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PartyProgressList
          title="Top Receivables (Debtors)"
          subtitle="Outstanding customer balances — TallyPrime"
          items={kpi?.receivables.top ?? []}
          barColor="bg-amber-400"
          loading={isLoading}
          emptyText="No outstanding receivables found"
        />
        <PartyProgressList
          title="Top Payables (Creditors)"
          subtitle="Outstanding vendor balances — TallyPrime"
          items={kpi?.payables.top ?? []}
          barColor="bg-violet-400"
          loading={isLoading}
          emptyText="No outstanding payables found"
        />
      </div>

      {/* Bottom: Cash/Bank | Assets & Liabilities | Inventory */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Cash & Bank */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800">Cash & Bank Position</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-40" />
            ) : cashBankData.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-10">No cash/bank data</p>
            ) : (
              <div>
                <ResponsiveContainer width="100%" height={100}>
                  <PieChart>
                    <Pie
                      data={cashBankData}
                      cx="50%" cy="50%"
                      innerRadius={28} outerRadius={44}
                      paddingAngle={3} dataKey="value"
                      startAngle={90} endAngle={-270}
                    >
                      <Cell fill="#06B6D4" />
                      <Cell fill="#0369A1" />
                    </Pie>
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex items-center justify-around mt-3">
                  <div className="text-center">
                    <div className="flex items-center gap-1.5 mb-1 justify-center">
                      <div className="w-2 h-2 rounded-full bg-cyan-400" />
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider">Cash</span>
                    </div>
                    <p className="text-sm font-bold text-slate-800">
                      {formatCompactCurrency(kpi?.cash_bank.cash ?? 0)}
                    </p>
                  </div>
                  <div className="w-px h-10 bg-slate-100" />
                  <div className="text-center">
                    <div className="flex items-center gap-1.5 mb-1 justify-center">
                      <div className="w-2 h-2 rounded-full bg-sky-700" />
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider">Bank</span>
                    </div>
                    <p className="text-sm font-bold text-slate-800">
                      {formatCompactCurrency(kpi?.cash_bank.bank ?? 0)}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Assets & Liabilities */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800">Balance Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isLoading ? (
              <div className="space-y-3">{[1, 2, 3].map(i => <Skeleton key={i} className="h-12" />)}</div>
            ) : (
              <>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-50 border border-emerald-100">
                  <ArrowUpRight className="w-4 h-4 text-emerald-600 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">Total Assets</p>
                    <p className="text-sm font-bold text-emerald-700">{formatCompactCurrency(kpi?.assets ?? 0)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-rose-50 border border-rose-100">
                  <TrendingDown className="w-4 h-4 text-rose-600 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">Total Liabilities</p>
                    <p className="text-sm font-bold text-rose-700">{formatCompactCurrency(kpi?.liabilities ?? 0)}</p>
                  </div>
                </div>
                <div className={cn(
                  'flex items-center gap-3 p-3 rounded-lg border',
                  netWorth >= 0 ? 'bg-indigo-50 border-indigo-100' : 'bg-orange-50 border-orange-100',
                )}>
                  <DollarSign className={cn('w-4 h-4 shrink-0', netWorth >= 0 ? 'text-indigo-600' : 'text-orange-600')} />
                  <div className="min-w-0">
                    <p className="text-[10px] text-slate-500 uppercase tracking-wider">Net Worth</p>
                    <p className={cn('text-sm font-bold', netWorth >= 0 ? 'text-indigo-700' : 'text-orange-700')}>
                      {formatCompactCurrency(netWorth)}
                    </p>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Inventory */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800">Inventory Overview</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">{[1, 2].map(i => <Skeleton key={i} className="h-16" />)}</div>
            ) : (
              <div className="space-y-3">
                <div className="flex flex-col items-center justify-center p-5 rounded-xl bg-slate-50 border border-slate-100">
                  <Package className="w-7 h-7 text-slate-300 mb-1.5" />
                  <p className="text-3xl font-bold text-slate-800 leading-none">
                    {(kpi?.inventory.item_count ?? 0).toLocaleString('en-IN')}
                  </p>
                  <p className="text-xs text-slate-400 mt-1">Stock Items</p>
                </div>
                <div className="flex flex-col items-center justify-center p-3.5 rounded-xl bg-indigo-50 border border-indigo-100">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-0.5">
                    Inventory Value
                  </p>
                  <p className="text-lg font-bold text-indigo-700">
                    {formatCompactCurrency(kpi?.inventory.total_value ?? 0)}
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
