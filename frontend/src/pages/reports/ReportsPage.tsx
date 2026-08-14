import { useState, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { format, subMonths, startOfMonth, endOfMonth } from 'date-fns';
import {
  FileBarChart, Download, Clock, CheckCircle, XCircle, Loader2,
  TrendingUp, DollarSign, TrendingDown, AlertCircle, CreditCard,
  CalendarDays, Receipt, LucideIcon,
} from 'lucide-react';
import { reportsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Badge } from '../../components/ui/badge';
import { formatDate, formatDateTime } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import type { Report } from '../../types';

const REPORT_TYPES: { value: string; label: string; description: string; icon: LucideIcon; color: string }[] = [
  { value: 'profit_loss', label: 'P&L Statement', description: 'Profit and Loss for a date range', icon: TrendingUp, color: 'text-indigo-600 bg-indigo-50' },
  { value: 'revenue', label: 'Revenue Report', description: 'Revenue breakdown by customer and category', icon: DollarSign, color: 'text-emerald-600 bg-emerald-50' },
  { value: 'expense', label: 'Expense Report', description: 'Expense breakdown by vendor and category', icon: TrendingDown, color: 'text-rose-600 bg-rose-50' },
  { value: 'receivables', label: 'Receivables Aging', description: 'Outstanding receivables by age bucket', icon: AlertCircle, color: 'text-amber-600 bg-amber-50' },
  { value: 'payables', label: 'Payables Aging', description: 'Outstanding payables by age bucket', icon: CreditCard, color: 'text-violet-600 bg-violet-50' },
  { value: 'monthly_summary', label: 'Monthly Summary', description: 'Complete monthly financial summary', icon: CalendarDays, color: 'text-blue-600 bg-blue-50' },
  { value: 'gst_summary', label: 'GST Summary', description: 'GST collected and paid summary', icon: Receipt, color: 'text-slate-600 bg-slate-100' },
];

function DownloadButton({ reportId, title }: { reportId: string; title: string }) {
  const [loading, setLoading] = useState(false);

  const handleDownload = useCallback(async () => {
    setLoading(true);
    try {
      await reportsApi.download(reportId, title);
    } catch {
      toast({ title: 'Download failed', description: 'Could not download the report. Please try again.', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [reportId, title]);

  return (
    <Button
      variant="ghost"
      size="sm"
      className="text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50"
      onClick={handleDownload}
      disabled={loading}
    >
      {loading
        ? <Loader2 className="w-4 h-4 animate-spin mr-1" />
        : <Download className="w-4 h-4 mr-1" />
      }
      PDF
    </Button>
  );
}

export default function ReportsPage() {
  const [selectedType, setSelectedType] = useState('');
  const [dateFrom, setDateFrom] = useState(format(startOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(endOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'));

  const { data: reports, isLoading: reportsLoading, refetch } = useQuery({
    queryKey: ['reports'],
    queryFn: reportsApi.list,
  });

  const generateMutation = useMutation({
    mutationFn: reportsApi.generate,
    onSuccess: () => {
      toast({ title: 'Report generation started', description: 'Your report will be ready shortly', variant: 'success' });
      refetch();
    },
    onError: () => toast({ title: 'Failed to generate report', variant: 'destructive' }),
  });

  const handleGenerate = () => {
    if (!selectedType) {
      toast({ title: 'Please select a report type', variant: 'destructive' });
      return;
    }
    generateMutation.mutate({ type: selectedType, date_from: dateFrom, date_to: dateTo });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Reports</h2>
        <p className="text-sm text-slate-500">Generate and download financial reports</p>
      </div>

      {/* Report type selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Select Report Type</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 mb-6">
            {REPORT_TYPES.map((rt) => (
              <button
                key={rt.value}
                onClick={() => setSelectedType(rt.value)}
                className={cn(
                  "text-left p-4 rounded-xl border-2 transition-all",
                  selectedType === rt.value
                    ? "border-indigo-500 bg-indigo-50"
                    : "border-slate-200 hover:border-indigo-300 hover:bg-slate-50"
                )}
              >
                <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center mb-3", rt.color)}>
                  <rt.icon className="w-5 h-5" />
                </div>
                <p className={cn("font-semibold text-sm", selectedType === rt.value ? "text-indigo-700" : "text-slate-800")}>
                  {rt.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5 leading-snug">{rt.description}</p>
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
            <div className="space-y-1.5">
              <Label>From Date</Label>
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>To Date</Label>
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
            <Button
              onClick={handleGenerate}
              loading={generateMutation.isPending}
              disabled={!selectedType}
              size="lg"
            >
              <FileBarChart className="w-4 h-4 mr-2" />
              Generate Report
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Report history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Report History</CardTitle>
        </CardHeader>
        <CardContent>
          {reportsLoading ? (
            <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Report</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Period</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Generated</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {reports?.length ? reports.map((report: Report) => (
                    <tr key={report.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-medium text-slate-900">{report.title}</td>
                      <td className="py-3 px-4 text-slate-600 text-xs">
                        {report.period_start ? formatDate(report.period_start) : '—'}
                        {report.period_end ? ` – ${formatDate(report.period_end)}` : ''}
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-xs">{formatDateTime(report.created_at)}</td>
                      <td className="py-3 px-4">
                        <Badge variant="success">Ready</Badge>
                      </td>
                      <td className="py-3 px-4">
                        {report.download_url
                          ? <DownloadButton reportId={report.id} title={report.title} />
                          : <span className="text-slate-400 text-sm">-</span>
                        }
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={5} className="py-16 text-center">
                        <FileBarChart className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                        <p className="text-slate-400 text-sm">No reports generated yet</p>
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
