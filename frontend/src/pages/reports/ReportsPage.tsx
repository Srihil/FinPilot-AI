import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, subMonths, startOfMonth, endOfMonth } from 'date-fns';
import {
  FileBarChart, Download, Loader2,
  TrendingUp, DollarSign, TrendingDown, AlertCircle, CreditCard,
  CalendarDays, Receipt, LucideIcon, Scale, Users, Sparkles,
  ChevronDown, ChevronUp, BarChart2, ChevronLeft, ChevronRight as ChevronRightIcon,
  Trash2, Square, CheckSquare, X,
} from 'lucide-react';
import { reportsApi, reportsExtApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Badge } from '../../components/ui/badge';
import { Switch } from '../../components/ui/switch';
import { formatDate, formatDateTime } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import { cn } from '../../utils/cn';
import type { Report } from '../../types';

// ─── Report type registry ─────────────────────────────────────────────────────

const REPORT_TYPES: {
  value: string;
  label: string;
  description: string;
  icon: LucideIcon;
  color: string;
  needsParty?: 'customer' | 'vendor';
  supportsAI?: boolean;
}[] = [
  {
    value: 'profit_loss',
    label: 'P&L Statement',
    description: 'Profit and Loss for a date range',
    icon: TrendingUp, color: 'text-indigo-600 bg-indigo-50',
    supportsAI: true,
  },
  {
    value: 'revenue',
    label: 'Revenue Report',
    description: 'Revenue breakdown by customer and category',
    icon: DollarSign, color: 'text-emerald-600 bg-emerald-50',
    supportsAI: true,
  },
  {
    value: 'expense',
    label: 'Expense Report',
    description: 'Expense breakdown by vendor and category',
    icon: TrendingDown, color: 'text-rose-600 bg-rose-50',
    supportsAI: true,
  },
  {
    value: 'monthly_summary',
    label: 'Monthly Summary',
    description: 'Complete monthly financial summary',
    icon: CalendarDays, color: 'text-blue-600 bg-blue-50',
    supportsAI: true,
  },
  {
    value: 'gst_summary',
    label: 'GST Summary',
    description: 'GST collected and paid by month',
    icon: Receipt, color: 'text-slate-600 bg-slate-100',
  },
  {
    value: 'trial_balance',
    label: 'Trial Balance',
    description: 'All ledger closing balances (Dr / Cr)',
    icon: Scale, color: 'text-cyan-600 bg-cyan-50',
    supportsAI: true,
  },
  {
    value: 'aged_receivables',
    label: 'Aged Receivables',
    description: 'Outstanding receivables bucketed by age',
    icon: AlertCircle, color: 'text-amber-600 bg-amber-50',
    supportsAI: true,
  },
  {
    value: 'aged_payables',
    label: 'Aged Payables',
    description: 'Outstanding payables bucketed by age',
    icon: CreditCard, color: 'text-violet-600 bg-violet-50',
    supportsAI: true,
  },
  {
    value: 'customer_statement',
    label: 'Customer Statement',
    description: 'Full transaction history for one customer',
    icon: Users, color: 'text-teal-600 bg-teal-50',
    needsParty: 'customer',
  },
  {
    value: 'vendor_statement',
    label: 'Vendor Statement',
    description: 'Full transaction history for one vendor',
    icon: BarChart2, color: 'text-pink-600 bg-pink-50',
    needsParty: 'vendor',
  },
];

const COMPARISON_OPTIONS = [
  { value: 'prev_month',   label: 'vs Previous Month' },
  { value: 'prev_year',    label: 'vs Same Period Last Year' },
  { value: 'prev_quarter', label: 'vs Previous Quarter' },
  { value: 'custom',       label: 'Custom Date Range' },
];

// ─── Download button ──────────────────────────────────────────────────────────

function DownloadButton({ reportId, title }: { reportId: string; title: string }) {
  const [loading, setLoading] = useState(false);

  const handleDownload = useCallback(async () => {
    setLoading(true);
    try {
      await reportsApi.download(reportId, title);
    } catch {
      toast({ title: 'Download failed', description: 'Could not download the report.', variant: 'destructive' });
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
      {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Download className="w-4 h-4 mr-1" />}
      PDF
    </Button>
  );
}

// ─── Party search combobox ────────────────────────────────────────────────────

function PartySelect({
  partyType,
  value,
  onChange,
}: {
  partyType: 'customer' | 'vendor';
  value: string;
  onChange: (id: string, name: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [selectedName, setSelectedName] = useState('');

  const { data: parties, isFetching } = useQuery({
    queryKey: ['party-search', partyType, query],
    queryFn: () => reportsExtApi.searchParties(query, partyType),
    enabled: open,
  });

  const handleSelect = (id: string, name: string) => {
    onChange(id, name);
    setSelectedName(name);
    setOpen(false);
  };

  return (
    <div className="relative">
      <div
        className="w-full flex items-center border border-slate-300 rounded-lg px-3 py-2 bg-white cursor-pointer text-sm"
        onClick={() => setOpen(!open)}
      >
        <span className={selectedName ? 'text-slate-900' : 'text-slate-400'}>
          {selectedName || `Search ${partyType}...`}
        </span>
        {open ? <ChevronUp className="w-4 h-4 ml-auto text-slate-400" /> : <ChevronDown className="w-4 h-4 ml-auto text-slate-400" />}
      </div>
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden">
          <div className="p-2 border-b border-slate-100">
            <Input
              autoFocus
              placeholder={`Search ${partyType}s...`}
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {isFetching ? (
              <div className="p-3 text-center text-sm text-slate-400">Searching…</div>
            ) : parties?.length ? (
              parties.map(p => (
                <button
                  key={p.id}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-indigo-50 hover:text-indigo-700"
                  onClick={() => handleSelect(p.id, p.name)}
                >
                  <span className="font-medium">{p.name}</span>
                  {p.gstin && <span className="ml-2 text-xs text-slate-400">{p.gstin}</span>}
                </button>
              ))
            ) : (
              <div className="p-3 text-center text-sm text-slate-400">No {partyType}s found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const [selectedType, setSelectedType] = useState('');
  const [dateFrom, setDateFrom] = useState(format(startOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'));
  const [dateTo, setDateTo] = useState(format(endOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'));

  // Party selection (Customer/Vendor statement)
  const [partyId, setPartyId] = useState('');

  // Report history pagination + selection
  const [historyPage, setHistoryPage] = useState(1);
  const PAGE_SIZE = 10;
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const toggleSelect = (id: string) =>
    setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearSelection = () => setSelectedIds(new Set());

  // AI controls
  const [enableAiSummary, setEnableAiSummary] = useState(false);
  const [enableAiComparison, setEnableAiComparison] = useState(false);
  const [comparisonBasis, setComparisonBasis] = useState('prev_month');
  const [cmpDateFrom, setCmpDateFrom] = useState('');
  const [cmpDateTo, setCmpDateTo] = useState('');

  const selectedMeta = REPORT_TYPES.find(r => r.value === selectedType);

  const qc = useQueryClient();
  const { data: reportsData, isLoading: reportsLoading, refetch } = useQuery({
    queryKey: ['reports', historyPage],
    queryFn: () => reportsApi.list(historyPage, PAGE_SIZE),
  });
  const reports = reportsData?.items ?? [];
  const totalPages = reportsData?.total_pages ?? 1;
  const totalReports = reportsData?.total ?? 0;

  const pageIds = reports.map(r => r.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every(id => selectedIds.has(id));

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => reportsApi.bulkDelete(ids),
    onSuccess: (res) => {
      toast({ title: `${res.deleted} report${res.deleted !== 1 ? 's' : ''} deleted`, variant: 'success' });
      clearSelection();
      setHistoryPage(1);
      qc.invalidateQueries({ queryKey: ['reports'] });
    },
    onError: () => toast({ title: 'Delete failed', variant: 'destructive' }),
  });

  const generateMutation = useMutation({
    mutationFn: reportsApi.generate,
    onSuccess: () => {
      toast({ title: 'Report generated', description: 'Your report is ready to download.', variant: 'success' });
      setHistoryPage(1);
      refetch();
    },
    onError: () => toast({ title: 'Failed to generate report', variant: 'destructive' }),
  });

  const handleGenerate = () => {
    if (!selectedType) {
      toast({ title: 'Please select a report type', variant: 'destructive' });
      return;
    }
    if (selectedMeta?.needsParty && !partyId) {
      toast({ title: `Please select a ${selectedMeta.needsParty}`, variant: 'destructive' });
      return;
    }
    generateMutation.mutate({
      type: selectedType,
      date_from: dateFrom,
      date_to: dateTo,
      party_id: partyId || undefined,
      enable_ai_summary: enableAiSummary,
      enable_ai_comparison: enableAiComparison && !!selectedMeta?.supportsAI,
      comparison_basis: comparisonBasis,
      comparison_period_start: comparisonBasis === 'custom' ? cmpDateFrom : undefined,
      comparison_period_end: comparisonBasis === 'custom' ? cmpDateTo : undefined,
    });
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
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {REPORT_TYPES.map((rt) => (
              <button
                key={rt.value}
                type="button"
                onClick={() => { setSelectedType(rt.value); setPartyId(''); }}
                className={cn(
                  'text-left p-4 rounded-xl border-2 transition-all',
                  selectedType === rt.value
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50',
                )}
              >
                <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center mb-3', rt.color)}>
                  <rt.icon className="w-5 h-5" />
                </div>
                <p className={cn('font-semibold text-sm', selectedType === rt.value ? 'text-indigo-700' : 'text-slate-800')}>
                  {rt.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5 leading-snug">{rt.description}</p>
              </button>
            ))}
          </div>

          {/* Date range + party selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
            <div className="space-y-1.5">
              <Label>From Date</Label>
              <Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>To Date</Label>
              <Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
            {selectedMeta?.needsParty && (
              <div className="space-y-1.5 lg:col-span-2">
                <Label className="capitalize">{selectedMeta.needsParty}</Label>
                <PartySelect
                  partyType={selectedMeta.needsParty}
                  value={partyId}
                  onChange={(id) => setPartyId(id)}
                />
              </div>
            )}
          </div>

          {/* AI controls — only for supported report types */}
          {selectedMeta?.supportsAI && (
            <div className="border border-indigo-100 bg-indigo-50/40 rounded-xl p-4 space-y-4">
              <div className="flex items-center gap-2 text-indigo-700 font-semibold text-sm">
                <Sparkles className="w-4 h-4" />
                AI Insights (optional)
              </div>

              {/* AI Summary toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-800">AI Summary</p>
                  <p className="text-xs text-slate-500">Generate a 3-5 sentence executive summary of this report</p>
                </div>
                <Switch
                  checked={enableAiSummary}
                  onCheckedChange={setEnableAiSummary}
                />
              </div>

              {/* AI Comparison toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-800">Comparative Analysis</p>
                  <p className="text-xs text-slate-500">Compare to a previous period and explain what changed</p>
                </div>
                <Switch
                  checked={enableAiComparison}
                  onCheckedChange={setEnableAiComparison}
                />
              </div>

              {/* Comparison options — shown when toggle is on */}
              {enableAiComparison && (
                <div className="space-y-3 pl-1">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {COMPARISON_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setComparisonBasis(opt.value)}
                        className={cn(
                          'text-xs px-3 py-2 rounded-lg border font-medium transition-all',
                          comparisonBasis === opt.value
                            ? 'border-indigo-500 bg-indigo-100 text-indigo-700'
                            : 'border-slate-200 text-slate-600 hover:border-indigo-300',
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  {comparisonBasis === 'custom' && (
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <Label className="text-xs">Comparison From</Label>
                        <Input type="date" value={cmpDateFrom} onChange={e => setCmpDateFrom(e.target.value)} className="h-8 text-sm" />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Comparison To</Label>
                        <Input type="date" value={cmpDateTo} onChange={e => setCmpDateTo(e.target.value)} className="h-8 text-sm" />
                      </div>
                    </div>
                  )}
                  <p className="text-xs text-slate-400">
                    AI will compare key metrics and generate a written explanation in the PDF.
                    If the AI call fails, the report still generates without the insight section.
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end">
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
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Report History
            {totalReports > 0 && <span className="ml-2 text-sm font-normal text-slate-400">({totalReports} total)</span>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {reportsLoading ? (
            <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="py-3 px-4 w-8">
                      <button
                        type="button"
                        onClick={() => allPageSelected
                          ? setSelectedIds(prev => { const n = new Set(prev); pageIds.forEach(id => n.delete(id)); return n; })
                          : setSelectedIds(prev => new Set([...prev, ...pageIds]))
                        }
                        className="text-slate-400 hover:text-indigo-600"
                      >
                        {allPageSelected ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
                      </button>
                    </th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Report</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Period</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Generated</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">AI</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.length ? reports.map((report: Report & { ai_insights?: string }) => (
                    <tr key={report.id} className={cn(
                      "border-b border-slate-50 hover:bg-slate-50 transition-colors",
                      selectedIds.has(report.id) && "bg-indigo-50/60",
                    )}>
                      <td className="py-3 px-4">
                        <button type="button" onClick={() => toggleSelect(report.id)} className="text-slate-400 hover:text-indigo-600">
                          {selectedIds.has(report.id)
                            ? <CheckSquare className="w-4 h-4 text-indigo-600" />
                            : <Square className="w-4 h-4" />
                          }
                        </button>
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-900">{report.title}</td>
                      <td className="py-3 px-4 text-slate-600 text-xs">
                        {report.period_start ? formatDate(report.period_start) : '—'}
                        {report.period_end ? ` – ${formatDate(report.period_end)}` : ''}
                      </td>
                      <td className="py-3 px-4 text-slate-500 text-xs">{formatDateTime(report.created_at)}</td>
                      <td className="py-3 px-4">
                        {report.ai_insights
                          ? <Badge variant="secondary" className="text-xs gap-1">
                              <Sparkles className="w-3 h-3" /> AI
                            </Badge>
                          : <span className="text-slate-300 text-xs">—</span>
                        }
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
                      <td colSpan={6} className="py-16 text-center">
                        <FileBarChart className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                        <p className="text-slate-400 text-sm">No reports generated yet</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
                  <p className="text-xs text-slate-500">
                    Page {historyPage} of {totalPages} · {totalReports} report{totalReports !== 1 ? 's' : ''}
                  </p>
                  <div className="flex gap-1">
                    <button
                      onClick={() => setHistoryPage(p => Math.max(1, p - 1))}
                      disabled={historyPage === 1}
                      className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50 transition-colors"
                    >
                      <ChevronLeft className="w-4 h-4 text-slate-600" />
                    </button>
                    {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                      const pg = totalPages <= 7 ? i + 1
                        : historyPage <= 4 ? i + 1
                        : historyPage >= totalPages - 3 ? totalPages - 6 + i
                        : historyPage - 3 + i;
                      return (
                        <button
                          key={pg}
                          onClick={() => setHistoryPage(pg)}
                          className={cn(
                            'w-8 h-8 text-xs rounded-lg border transition-colors font-medium',
                            historyPage === pg
                              ? 'bg-indigo-600 text-white border-indigo-600'
                              : 'border-slate-200 text-slate-600 hover:bg-slate-50',
                          )}
                        >
                          {pg}
                        </button>
                      );
                    })}
                    <button
                      onClick={() => setHistoryPage(p => Math.min(totalPages, p + 1))}
                      disabled={historyPage === totalPages}
                      className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50 transition-colors"
                    >
                      <ChevronRightIcon className="w-4 h-4 text-slate-600" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-slate-900 text-white px-5 py-3 rounded-2xl shadow-2xl border border-slate-700">
          <button type="button" onClick={clearSelection} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium">
            {selectedIds.size} report{selectedIds.size !== 1 ? 's' : ''} selected
          </span>
          <div className="w-px h-4 bg-slate-600" />
          <button
            type="button"
            onClick={() => bulkDeleteMutation.mutate([...selectedIds])}
            disabled={bulkDeleteMutation.isPending}
            className="flex items-center gap-2 text-rose-400 hover:text-rose-300 text-sm font-medium transition-colors disabled:opacity-50"
          >
            {bulkDeleteMutation.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Trash2 className="w-4 h-4" />
            }
            Delete Selected
          </button>
        </div>
      )}
    </div>
  );
}
