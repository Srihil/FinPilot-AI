/**
 * Reusable chart wrapper components built on Recharts
 * Used across Dashboard and Analytics pages
 */
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { formatCurrency } from '../utils/format';

export const CHART_COLORS = {
  primary: '#4F46E5',
  secondary: '#7C3AED',
  success: '#10B981',
  danger: '#F43F5E',
  warning: '#F59E0B',
  info: '#3B82F6',
  pie: ['#4F46E5', '#7C3AED', '#EC4899', '#F59E0B', '#10B981', '#3B82F6'],
};

interface MonthlyData {
  month: string;
  amount: number;
}

interface CategoryData {
  category: string;
  amount: number;
  percentage: number;
}

const DefaultTooltip = ({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) => {
  if (active && payload?.length) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-lg p-3 text-sm">
        <p className="font-medium text-slate-500 mb-1">{label}</p>
        {payload.map((p) => (
          <p key={p.name} style={{ color: p.color }} className="font-semibold">
            {p.name}: {formatCurrency(p.value)}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

// Revenue Line Chart
export function RevenueLineChart({ data }: { data: MonthlyData[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} />
        <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
        <Tooltip content={<DefaultTooltip />} />
        <Line type="monotone" dataKey="amount" name="Revenue" stroke={CHART_COLORS.primary} strokeWidth={2.5} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// Revenue vs Expenses Bar Chart
export function RevenueExpenseBarChart({ data }: { data: Array<{ month: string; Revenue: number; Expenses: number }> }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="month" tick={{ fontSize: 11, fill: '#94a3b8' }} />
        <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
        <Tooltip content={<DefaultTooltip />} />
        <Legend iconSize={10} wrapperStyle={{ fontSize: '12px' }} />
        <Bar dataKey="Revenue" fill={CHART_COLORS.primary} radius={[3, 3, 0, 0]} />
        <Bar dataKey="Expenses" fill={CHART_COLORS.danger} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// Expense Category Pie Chart
export function ExpensePieChart({ data }: { data: CategoryData[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={80}
          paddingAngle={2}
          dataKey="amount"
          nameKey="category"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS.pie[i % CHART_COLORS.pie.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v) => formatCurrency(Number(v))} />
      </PieChart>
    </ResponsiveContainer>
  );
}
