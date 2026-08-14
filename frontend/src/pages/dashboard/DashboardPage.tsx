import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TrendingUp, TrendingDown, DollarSign, CreditCard, Clock, AlertTriangle, ArrowUpRight
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { dashboardApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Skeleton } from '../../components/ui/skeleton';
import { StatusBadge } from '../../components/ui/badge';
import { formatCurrency, formatCompactCurrency, formatDate, formatPercent, getChangeColor } from '../../utils/format';

const PIE_COLORS = ['#4F46E5', '#7C3AED', '#EC4899', '#F59E0B', '#10B981', '#3B82F6'];

function KPICard({
  title, value, change, icon: Icon, color, loading
}: {
  title: string; value: number; change?: number; icon: React.ComponentType<{ className?: string }>;
  color: string; loading: boolean;
}) {
  if (loading) return <Skeleton className="h-32 rounded-lg" />;
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{title}</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{formatCompactCurrency(value)}</p>
            {change !== undefined && (
              <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${getChangeColor(change)}`}>
                {change >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                {formatPercent(change)} vs last period
              </div>
            )}
          </div>
          <div className={`w-10 h-10 rounded-lg ${color} flex items-center justify-center`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) => {
  if (active && payload?.length) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3">
        <p className="text-xs font-medium text-slate-500 mb-2">{label}</p>
        {payload.map((p) => (
          <p key={p.name} className="text-sm font-semibold" style={{ color: p.color }}>
            {p.name}: {formatCurrency(p.value)}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function DashboardPage() {
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardApi.overview,
  });

  const { data: charts, isLoading: chartsLoading } = useQuery({
    queryKey: ['dashboard', 'charts'],
    queryFn: dashboardApi.charts,
  });

  // Use monthly_data from the API (has month, revenue, expenses, profit)
  const combinedChartData = (charts?.monthly_data || []).map((d: { month: string; revenue: number; expenses: number; profit: number }) => ({
    month: d.month,
    Revenue: d.revenue,
    Expenses: d.expenses,
  }));

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard
          title="Total Revenue"
          value={overview?.total_revenue || 0}
          change={overview?.revenue_growth}
          icon={DollarSign}
          color="bg-indigo-600"
          loading={overviewLoading}
        />
        <KPICard
          title="Total Expenses"
          value={overview?.total_expenses || 0}
          change={overview?.expense_growth}
          icon={CreditCard}
          color="bg-rose-500"
          loading={overviewLoading}
        />
        <KPICard
          title="Net Profit"
          value={overview?.net_profit || 0}
          icon={TrendingUp}
          color="bg-emerald-600"
          loading={overviewLoading}
        />
        <KPICard
          title="Receivables"
          value={overview?.outstanding_receivables || 0}
          icon={Clock}
          color="bg-amber-500"
          loading={overviewLoading}
        />
        <KPICard
          title="Payables"
          value={overview?.outstanding_payables || 0}
          icon={AlertTriangle}
          color="bg-violet-600"
          loading={overviewLoading}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue vs Expenses */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Revenue vs Expenses</CardTitle>
          </CardHeader>
          <CardContent>
            {chartsLoading ? (
              <Skeleton className="h-56" />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={combinedChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize: '12px' }} />
                  <Bar dataKey="Revenue" fill="#4F46E5" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Expenses" fill="#F43F5E" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Expense Categories Pie */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Expense Categories</CardTitle>
          </CardHeader>
          <CardContent>
            {chartsLoading ? (
              <Skeleton className="h-56" />
            ) : (
              <div>
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie
                      data={charts?.expense_categories || []}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={70}
                      paddingAngle={2}
                      dataKey="value"
                      nameKey="name"
                    >
                      {charts?.expense_categories?.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1.5 mt-2">
                  {(() => {
                    const cats = charts?.expense_categories || [];
                    const total = cats.reduce((s, c) => s + c.value, 0);
                    return cats.slice(0, 4).map((cat, i) => (
                      <div key={cat.name} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                          <span className="text-xs text-slate-600">{cat.name}</span>
                        </div>
                        <span className="text-xs font-medium text-slate-700">{total > 0 ? (cat.value / total * 100).toFixed(1) : 0}%</span>
                      </div>
                    ));
                  })()}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Revenue trend line chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Revenue Trend</CardTitle>
          </CardHeader>
          <CardContent>
            {chartsLoading ? (
              <Skeleton className="h-44" />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={combinedChartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Line type="monotone" dataKey="Revenue" stroke="#4F46E5" strokeWidth={2.5} dot={{ r: 3, fill: '#4F46E5' }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Pending Approvals */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Pending Approvals</CardTitle>
            <a href="/approvals" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
              View all <ArrowUpRight className="w-3 h-3" />
            </a>
          </CardHeader>
          <CardContent>
            {overviewLoading ? (
              <Skeleton className="h-40" />
            ) : (
              <div className="text-center py-6">
                <div className="text-5xl font-bold text-indigo-600">{overview?.pending_approvals_count || 0}</div>
                <p className="text-slate-500 text-sm mt-2">items awaiting approval</p>
                {(overview?.pending_approvals_count || 0) > 0 && (
                  <a
                    href="/approvals"
                    className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-50 text-indigo-700 text-sm font-medium hover:bg-indigo-100 transition-colors"
                  >
                    Review now <ArrowUpRight className="w-4 h-4" />
                  </a>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Transactions */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Recent Transactions</CardTitle>
          <a href="/transactions" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
            View all <ArrowUpRight className="w-3 h-3" />
          </a>
        </CardHeader>
        <CardContent>
          {overviewLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12" />)}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Date</th>
                    <th className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Reference</th>
                    <th className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Party</th>
                    <th className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Type</th>
                    <th className="text-right py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Amount</th>
                    <th className="text-left py-2 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {overview?.recent_transactions?.length ? overview.recent_transactions.map((tx) => (
                    <tr key={tx.id} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                      <td className="py-2.5 px-3 text-slate-600">{formatDate(tx.date)}</td>
                      <td className="py-2.5 px-3 text-slate-900 font-medium">{tx.ref_number}</td>
                      <td className="py-2.5 px-3 text-slate-600">{tx.customer_name || tx.vendor_name || '-'}</td>
                      <td className="py-2.5 px-3">
                        <StatusBadge status={tx.type} />
                      </td>
                      <td className="py-2.5 px-3 text-right font-semibold text-slate-900">{formatCurrency(tx.total_amount)}</td>
                      <td className="py-2.5 px-3">
                        <StatusBadge status={tx.status} />
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-slate-400 text-sm">
                        No recent transactions
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
