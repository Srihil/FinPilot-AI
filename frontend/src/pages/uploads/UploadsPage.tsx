import { useState, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Upload, FileText, CheckCircle, AlertTriangle, Download,
  Clock, RefreshCw, ChevronDown, ChevronUp, History, Zap,
} from 'lucide-react';
import apiClient from '../../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Label } from '../../components/ui/label';
import { Progress } from '../../components/ui/progress';
import { Skeleton } from '../../components/ui/skeleton';
import { toast } from '../../components/ui/use-toast';
import { formatFileSize } from '../../utils/format';
import { cn } from '../../utils/cn';

// ─── Types ────────────────────────────────────────────────────────────────────

interface UploadResult {
  upload_id: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  imported_rows: number;
  tally_queued: number;
  status: string;
  errors: Array<{ row: number; field: string; message: string }>;
  duplicate_rows: number;
}

interface UploadHistory {
  id: string;
  original_filename: string;
  upload_type: string | null;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  imported_rows: number;
  created_at: string;
  completed_at: string | null;
  errors: Array<{ row: number; field: string; message: string }>;
}

// ─── Entity type definitions ──────────────────────────────────────────────────

const DATA_TYPES = [
  { group: 'Master Data', items: [
    { value: 'customers',    label: 'Customers',     desc: 'Name, email, phone, GST, address' },
    { value: 'vendors',      label: 'Vendors',        desc: 'Name, email, phone, GST, address' },
    { value: 'products',     label: 'Products',       desc: 'SKU, name, category, price, stock' },
    { value: 'expenses',     label: 'Expenses',       desc: 'Title, category, date, amount' },
  ]},
  { group: 'Tally Masters', items: [
    { value: 'ledgers',      label: 'Ledgers',        desc: 'Name, parent group, opening balance' },
    { value: 'stock_groups', label: 'Stock Groups',   desc: 'Name, parent group' },
    { value: 'units',        label: 'Units',          desc: 'Name, symbol, decimal places' },
    { value: 'godowns',      label: 'Godowns',        desc: 'Name, parent location' },
  ]},
];

const TALLY_TYPES = new Set(['ledgers', 'stock_groups', 'units', 'godowns']);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return d.toLocaleDateString();
}

const STATUS_CFG: Record<string, { cls: string; label: string }> = {
  COMPLETED: { cls: 'bg-emerald-100 text-emerald-700', label: 'Completed' },
  PARTIAL:   { cls: 'bg-amber-100 text-amber-700',   label: 'Partial' },
  FAILED:    { cls: 'bg-red-100 text-red-700',       label: 'Failed' },
  PROCESSING:{ cls: 'bg-blue-100 text-blue-700',     label: 'Processing' },
  PENDING:   { cls: 'bg-slate-100 text-slate-600',   label: 'Pending' },
};

// ─── Download template ────────────────────────────────────────────────────────

async function downloadTemplate(type: string) {
  try {
    const res = await apiClient.get(`/api/uploads/template/${type}`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `${type}_template.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    toast({ title: 'Template download failed', variant: 'destructive' });
  }
}

// ─── History row ──────────────────────────────────────────────────────────────

function HistoryRow({ u }: { u: UploadHistory }) {
  const [expanded, setExpanded] = useState(false);
  const s = STATUS_CFG[u.status] ?? STATUS_CFG.PENDING;

  return (
    <div className="border-b border-slate-100 last:border-0">
      <div
        className="flex items-center gap-3 py-3 px-4 hover:bg-slate-50 cursor-pointer transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <FileText className="w-4 h-4 text-slate-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-900 truncate">{u.original_filename}</p>
          <p className="text-xs text-slate-400">{u.upload_type?.replace('_', ' ') || '—'} · {relTime(u.created_at)}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-slate-500 hidden sm:block">
            {u.imported_rows}/{u.total_rows || 0} imported
          </span>
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${s.cls}`}>{s.label}</span>
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Total', value: u.total_rows, color: 'text-slate-700' },
              { label: 'Imported', value: u.imported_rows, color: 'text-emerald-600' },
              { label: 'Invalid', value: u.invalid_rows, color: 'text-red-600' },
            ].map(s => (
              <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
                <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-slate-500">{s.label}</p>
              </div>
            ))}
          </div>
          {u.errors?.length > 0 && (
            <div className="rounded-lg border border-red-100 overflow-hidden">
              <div className="bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">Sample errors</div>
              {u.errors.slice(0, 5).map((e, i) => (
                <div key={i} className="flex gap-3 px-3 py-1.5 text-xs border-t border-red-50">
                  <span className="text-slate-500 w-12 shrink-0">Row {e.row}</span>
                  <span className="text-red-600">{e.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function UploadsPage() {
  const [tab, setTab] = useState<'upload' | 'history'>('upload');
  const [uploadMode, setUploadMode] = useState<'csv' | 'pdf'>('csv');
  const [dataType, setDataType] = useState('');
  const [syncTally, setSyncTally] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data: history, isLoading: historyLoading } = useQuery<UploadHistory[]>({
    queryKey: ['upload-history'],
    queryFn: () => apiClient.get('/api/uploads').then(r => r.data),
    refetchInterval: tab === 'history' ? 15_000 : false,
  });

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback(() => setIsDragging(false), []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setSelectedFile(f);
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;
    if (uploadMode === 'csv' && !dataType) {
      toast({ title: 'Select a data type first', variant: 'destructive' });
      return;
    }

    setUploading(true);
    setProgress(10);
    setResult(null);

    const tick = setInterval(() => setProgress(p => Math.min(p + 12, 85)), 400);

    try {
      const form = new FormData();
      form.append('file', selectedFile);

      let res;
      if (uploadMode === 'pdf') {
        form.append('data_type', 'invoice_pdf');
        res = await apiClient.post('/api/uploads/pdf-invoice', form, { headers: { 'Content-Type': 'multipart/form-data' } });
        toast({ title: 'PDF processed', description: 'Invoice data extracted successfully.', variant: 'success' });
      } else {
        form.append('upload_type', dataType);
        form.append('sync_to_tally', syncTally ? 'true' : 'false');
        const r = await apiClient.post('/api/uploads/csv', form, { headers: { 'Content-Type': 'multipart/form-data' } });
        res = r;
        setResult(r.data);
      }

      setProgress(100);
      qc.invalidateQueries({ queryKey: ['upload-history'] });
      qc.invalidateQueries({ queryKey: ['management-overview'] });

      if (uploadMode === 'csv') {
        const d = res.data as UploadResult;
        const synced = d.tally_queued ? ` · ${d.tally_queued} Tally job${d.tally_queued !== 1 ? 's' : ''} queued` : '';
        toast({
          title: 'Upload complete',
          description: `${d.imported_rows} records imported${synced}`,
          variant: d.invalid_rows > 0 ? 'default' : 'success',
        });
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Upload failed', description: err?.response?.data?.detail || 'Processing error', variant: 'destructive' });
      setProgress(0);
    } finally {
      clearInterval(tick);
      setUploading(false);
    }
  };

  const downloadErrors = () => {
    if (!result?.errors?.length) return;
    const csv = ['Row,Field,Error', ...result.errors.map(e => `${e.row},${e.field},"${e.message}"`)].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'upload_errors.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  const isTallyType = TALLY_TYPES.has(dataType);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Bulk Uploads</h2>
          <p className="text-sm text-slate-500">Import data via CSV or extract from PDF invoices</p>
        </div>
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
          {(['upload', 'history'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all capitalize",
                tab === t ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-900"
              )}
            >
              {t === 'upload' ? <Upload className="w-3.5 h-3.5" /> : <History className="w-3.5 h-3.5" />}
              {t === 'upload' ? 'Upload' : `History${history?.length ? ` (${history.length})` : ''}`}
            </button>
          ))}
        </div>
      </div>

      {tab === 'upload' && (
        <div className="space-y-6 max-w-2xl">
          {/* Mode selector */}
          <div className="flex gap-2">
            {(['csv', 'pdf'] as const).map(m => (
              <button
                key={m}
                onClick={() => { setUploadMode(m); setSelectedFile(null); setResult(null); setProgress(0); }}
                className={cn(
                  "px-4 py-2 rounded-lg text-sm font-medium border transition-all",
                  uploadMode === m
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-200 text-slate-600 hover:border-slate-300"
                )}
              >
                {m === 'csv' ? 'CSV / XLSX Import' : 'PDF Invoice'}
              </button>
            ))}
          </div>

          <Card>
            <CardContent className="pt-6 space-y-5">
              {/* Data type select */}
              {uploadMode === 'csv' && (
                <div className="space-y-1.5">
                  <Label>Entity Type *</Label>
                  <Select value={dataType} onValueChange={v => { setDataType(v); setResult(null); }}>
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Select entity type" />
                    </SelectTrigger>
                    <SelectContent>
                      {DATA_TYPES.map(group => (
                        <div key={group.group}>
                          <div className="px-2 py-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wide">{group.group}</div>
                          {group.items.map(item => (
                            <SelectItem key={item.value} value={item.value}>
                              <div>
                                <p className="font-medium">{item.label}</p>
                                <p className="text-xs text-slate-400">{item.desc}</p>
                              </div>
                            </SelectItem>
                          ))}
                        </div>
                      ))}
                    </SelectContent>
                  </Select>
                  {dataType && (
                    <button
                      onClick={() => downloadTemplate(dataType)}
                      className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:underline mt-1"
                    >
                      <Download className="w-3 h-3" />
                      Download {dataType.replace('_', ' ')} template
                    </button>
                  )}
                </div>
              )}

              {/* Drop zone */}
              <div
                className={cn(
                  "border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer",
                  isDragging ? "border-indigo-400 bg-indigo-50" : "border-slate-200 hover:border-indigo-300 hover:bg-slate-50"
                )}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={uploadMode === 'csv' ? '.csv,.xlsx,.xls' : '.pdf'}
                  className="hidden"
                  onChange={e => e.target.files?.[0] && setSelectedFile(e.target.files[0])}
                />
                {selectedFile ? (
                  <div className="space-y-2">
                    <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center mx-auto">
                      <FileText className="w-6 h-6 text-indigo-600" />
                    </div>
                    <p className="font-medium text-slate-900">{selectedFile.name}</p>
                    <p className="text-sm text-slate-500">{formatFileSize(selectedFile.size)}</p>
                    <p className="text-xs text-indigo-600">Click to change file</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto">
                      <Upload className="w-6 h-6 text-slate-400" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-700">Drop file here or click to browse</p>
                      <p className="text-sm text-slate-400 mt-1">
                        {uploadMode === 'csv' ? 'CSV or XLSX, max 10MB' : 'PDF only, max 10MB'}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Tally sync option (for all types when connector might be active) */}
              {uploadMode === 'csv' && dataType && (
                <label className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg cursor-pointer hover:bg-slate-100 transition-colors">
                  <input
                    type="checkbox"
                    checked={syncTally}
                    onChange={e => setSyncTally(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 rounded"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Zap className="w-3.5 h-3.5 text-indigo-500" />
                      <span className="text-sm font-medium text-slate-900">
                        {isTallyType ? 'Sync imported records to TallyPrime' : 'Sync to TallyPrime after import'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5">
                      {isTallyType
                        ? 'Queues a Tally job for each record if connector is active'
                        : 'Queues a full sync job with TallyPrime after import completes'}
                    </p>
                  </div>
                </label>
              )}

              {/* Progress */}
              {uploading && (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm text-slate-600">
                    <span>Uploading and processing…</span>
                    <span>{progress}%</span>
                  </div>
                  <Progress value={progress} />
                </div>
              )}

              <Button
                onClick={handleUpload}
                disabled={!selectedFile || uploading || (uploadMode === 'csv' && !dataType)}
                size="lg"
                className="w-full gap-2"
              >
                {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {uploading ? 'Processing…' : 'Upload & Import'}
              </Button>
            </CardContent>
          </Card>

          {/* Results */}
          {result && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Import Results</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Total Rows', value: result.total_rows, color: 'text-slate-700' },
                    { label: 'Imported', value: result.imported_rows, color: 'text-emerald-600' },
                    { label: 'Invalid', value: result.invalid_rows, color: 'text-red-600' },
                    { label: 'Tally Jobs', value: result.tally_queued ?? 0, color: 'text-indigo-600' },
                  ].map(s => (
                    <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
                      <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                      <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                    </div>
                  ))}
                </div>

                {result.imported_rows > 0 && result.invalid_rows === 0 && (
                  <div className="flex items-center gap-2 p-3 bg-emerald-50 rounded-lg">
                    <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                    <p className="text-sm text-emerald-800 font-medium">
                      All {result.imported_rows} records imported successfully
                      {result.tally_queued ? ` · ${result.tally_queued} Tally job${result.tally_queued !== 1 ? 's' : ''} queued` : ''}
                    </p>
                  </div>
                )}

                {result.errors?.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-amber-700">
                        <AlertTriangle className="w-4 h-4" />
                        <span className="text-sm font-medium">{result.errors.length} validation errors</span>
                      </div>
                      <Button variant="outline" size="sm" onClick={downloadErrors} className="gap-1.5">
                        <Download className="w-3.5 h-3.5" /> Download Errors
                      </Button>
                    </div>
                    <div className="rounded-lg border border-red-100 overflow-hidden max-h-48 overflow-y-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-red-50 sticky top-0">
                          <tr>
                            <th className="text-left py-2 px-3 font-semibold text-red-700">Row</th>
                            <th className="text-left py-2 px-3 font-semibold text-red-700">Field</th>
                            <th className="text-left py-2 px-3 font-semibold text-red-700">Error</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.errors.map((e, i) => (
                            <tr key={i} className="border-t border-red-50">
                              <td className="py-1.5 px-3 text-slate-500">{e.row}</td>
                              <td className="py-1.5 px-3 text-slate-500">{e.field}</td>
                              <td className="py-1.5 px-3 text-red-600">{e.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Template downloads */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Download className="w-4 h-4 text-indigo-600" />
                CSV Templates
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-slate-500 mb-4">Download a template with sample data and correct column headers</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {DATA_TYPES.flatMap(g => g.items).map(t => (
                  <Button
                    key={t.value}
                    variant="outline"
                    size="sm"
                    onClick={() => downloadTemplate(t.value)}
                    className="gap-1.5 justify-start text-xs"
                  >
                    <Download className="w-3 h-3 shrink-0" />
                    {t.label}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {tab === 'history' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-600" />
                Upload History
              </CardTitle>
              <span className="text-xs text-slate-400">{history?.length ?? 0} uploads</span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {historyLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
              </div>
            ) : !history?.length ? (
              <div className="py-16 text-center">
                <Upload className="w-10 h-10 text-slate-200 mx-auto mb-3" />
                <p className="text-slate-500 font-medium">No uploads yet</p>
                <p className="text-slate-400 text-sm mt-1">Your import history will appear here</p>
                <Button size="sm" className="mt-4" onClick={() => setTab('upload')}>
                  Start uploading
                </Button>
              </div>
            ) : (
              <div>
                {history.map(u => <HistoryRow key={u.id} u={u} />)}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
