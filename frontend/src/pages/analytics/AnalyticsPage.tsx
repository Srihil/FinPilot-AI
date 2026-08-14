import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays, subMonths, startOfYear } from 'date-fns';
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { analyticsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { formatCurrency, formatCompactCurrency, formatPercent, getChangeColor } from '../../utils/format';
import { TrendingUp, TrendingDown, DollarSign, BarChart3 } from 'lucide-react';

type DateRange = '30d' | '90d' | 'ytd' | 'custom';

const PIE_COLORS = ['#4F46E5', '#7C3AED', '#EC4899', '#F59E0B', '#10B981'];

const DATE_OPTIONS: { label: string; value: DateRange }[] = [
  { label: 'Last 30 Days', value: '30d' },
  { label: 'Last 90 Days', value: '90d' },
  { label: 'This Year', value: 'ytd' },
];

function getDateRange(range: DateRange): { date_from: string; date_to: string } {
  const today = new Date();
  const fmt = (d: Date) => format(d, 'yyyy-MM-dd');
  switch (range) {
    case '30d': return { date_from: fmt(subDays(today, 30)), date_to: fmt(today) };
    case '90d': return { date_from: fmt(subDays(today, 90)), date_to: fmt(today) };
    case 'ytd': return { date_from: fmt(startOfYear(today)), date_to: fmt(today) };
    default: return { date_from: fmt(subDays(today, 30)), date_to: fmt(today) };
  }
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

export default function AnalyticsPage() {
  const [dateRange, setDateRange] = useState<DateRange>('30d');
  const params = getDateRange(dateRange);

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['analytics', 'overview', params],
    queryFn: () => analyticsApi.overview(params),
  });

  const { data: charts, isLoading: chartsLoading } = useQuery({
    queryKey: ['analytics', 'charts', params],
    queryFn: () => analyticsApi.charts(params),
  });

  const profitTrend = (charts?.monthly || []).map((r: { month: string; revenue: number; expenses: number; profit: number }) => ({
    month: r.month,
    Revenue: r.revenue,
    Expenses: r.expenses,
    Profit: r.profit,
  }));

  return (
    <div className="space-y-6">
      {/* Date Range Filter */}
      <div className="flex items-center gap-2">
        {DATE_OPTIONS.map(opt => (
          <Button
            key={opt.value}
            variant={dateRange === opt.value ? 'default' : 'outline'}
            size="sm"
            onClick={() => setDateRange(opt.value)}
          >
            {opt.label}
          </Button>
        ))}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { title: 'Total Revenue', value: (overview as { revenue?: number } | undefined)?.revenue, change: undefined, icon: DollarSign, color: 'bg-indigo-600' },
          { title: 'Total Expenses', value: (overview as { expenses?: number } | undefined)?.expenses, change: undefined, icon: TrendingDown, color: 'bg-rose-500' },
          { title: 'Net Profit', value: (overview as { net_profit?: number } | undefined)?.net_profit, icon: TrendingUp, color: 'bg-emerald-600' },
          { title: 'Profit Margin', value: null, percent: (overview as { profit_margin?: number } | undefined)?.profit_margin, icon: BarChart3, color: 'bg-violet-600' },
        ].map((kpi) => (
          <Card key={kpi.title} className="hover:shadow-md transition-shadow">
            <CardContent className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-500">{kpi.title}</p>
                  {overviewLoading ? (
                    <Skeleton className="h-7 w-24 mt-1" />
                  ) : (
                    <p className="text-xl font-bold text-slate-900 mt-1">
                      {kpi.percent !== undefined
                        ? `${(kpi.percent || 0).toFixed(1)}%`
                        : formatCompactCurrency(kpi.value || 0)
                      }
                    </p>
                  )}
                  {kpi.change !== undefined && !overviewLoading && (
                    <p className={`text-xs mt-1 ${getChangeColor(kpi.change || 0)}`}>
                      {formatPercent(kpi.change || 0)}
                    </p>
                  )}
                </div>
                <div className={`w-9 h-9 rounded-lg ${kpi.color} flex items-center justify-center`}>
                  <kpi.icon className="w-4 h-4 text-white" />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Revenue & Expense Trend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Revenue, Expenses & Profit Trend</CardTitle>
        </CardHeader>
        <CardContent>
          {chartsLoading ? <Skeleton className="h-64" /> : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={profitTrend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                <Tooltip content={<CustomTooltip />} />
                <Legend iconSize={10} wrapperStyle={{ fontSize: '12px' }} />
                <Line type="monotone" dataKey="Revenue" stroke="#4F46E5" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Expenses" stroke="#F43F5E" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Profit" stroke="#10B981" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Bottom charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Customer revenue */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Top Customers by Revenue</CardTitle>
          </CardHeader>
          <CardContent>
            {chartsLoading ? <Skeleton className="h-52" /> : (
              <ResponsiveContainer width="100%" height={210}>
                <BarChart data={charts?.customer_revenue || []} layout="vertical" margin={{ top: 4, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} width={120} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Bar dataKey="revenue" fill="#4F46E5" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Expense categories */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Expense Categories</CardTitle>
          </CardHeader>
          <CardContent>
            {chartsLoading ? <Skeleton className="h-52" /> : (
              <div>
                <ResponsiveContainer width="100%" height={140}>
                  <PieChart>
                    <Pie data={charts?.expense_categories || []} cx="50%" cy="50%" innerRadius={40} outerRadius={60}
                      paddingAngle={2} dataKey="value" nameKey="name">
                      {charts?.expense_categories?.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2 mt-2">
                  {charts?.expense_categories?.slice(0, 5).map((cat, i) => (
                    <div key={cat.name} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full" style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                        <span className="text-slate-600">{cat.name}</span>
                      </div>
                      <span className="font-medium text-slate-700">{formatCompactCurrency(cat.value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
