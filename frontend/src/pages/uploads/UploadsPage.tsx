import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Upload, FileText, CheckCircle, AlertTriangle, Download,
  Clock, RefreshCw, ChevronDown, ChevronUp, History, Zap,
  ArrowRight, ArrowLeft, Table2, Info, XCircle, Filter,
  CheckSquare, Square, AlertCircle,
} from 'lucide-react';
import apiClient from '../../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../components/ui/select';
import { Label } from '../../components/ui/label';
import { Progress } from '../../components/ui/progress';
import { Skeleton } from '../../components/ui/skeleton';
import { toast } from '../../components/ui/use-toast';
import { formatFileSize } from '../../utils/format';
import { cn } from '../../utils/cn';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ParseResponse {
  upload_id: string;
  detected_entity_type: string;
  entity_subtype: string;
  entity_confidence: 'high' | 'medium' | 'low';
  from_cache: boolean;
  file_columns: string[];
  mapping_suggestions: Record<string, string>;
  schema_fields: string[];
  sample_rows: Record<string, unknown>[];
  total_rows: number;
  file_format: string;
}

type RowStatus =
  | 'new' | 'valid'              // clean rows (valid is legacy alias)
  | 'warning'                    // non-blocking field issues
  | 'duplicate_exact'            // exact name match in DB (default unchecked)
  | 'duplicate_exact_forced'     // user explicitly force-importing
  | 'duplicate_fuzzy'            // similar name match
  | 'ref_missing'                // foreign-key reference not found (resolvable)
  | 'ref_similar'                // reference has a close-but-not-exact match
  | 'error';                     // blocking validation error

interface RefIssue {
  field: string;
  ref_entity_type: string;
  ref_name: string;
  match_type: 'ok' | 'intra_file' | 'similar' | 'missing';
  suggestions: Array<{ name: string; id: string | null; similarity: number }>;
}

interface RowResult {
  row_id: number;
  status: RowStatus;
  errors: Array<{ field: string; message: string }>;
  warnings: Array<{ field: string; message: string }>;
  mapped: Record<string, unknown>;
  duplicate_info: { match_type: 'exact' | 'fuzzy'; matched_name: string; matched_id: string; similarity: number } | null;
  ref_issues: RefIssue[];
  check_default: boolean;
  force_import: boolean;
}

interface SyncFreshness {
  last_sync_at: string | null;
  connector_online: boolean;
  connector_id: string | null;
}

interface ValidateResponse {
  upload_id: string;
  summary: { valid: number; warnings: number; errors: number; total: number };
  rows: RowResult[];
}

interface StatusResponse {
  upload_id: string;
  status: string;
  entity_type: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  imported_rows: number;
  tally_queued: number;
  commit_summary: Record<string, unknown> | null;
  completed_at: string | null;
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

type WizardStep = 'drop' | 'mapping' | 'preview' | 'progress' | 'done';
type RowFilter = 'all' | 'new' | 'warning' | 'duplicate_exact' | 'duplicate_fuzzy' | 'ref_missing' | 'ref_similar' | 'error';

// ─── Constants ────────────────────────────────────────────────────────────────

const ENTITY_LABELS: Record<string, string> = {
  Ledger: 'Ledger',
  'Stock Item': 'Stock Item',
  'Stock Group': 'Stock Group',
  'Stock Category': 'Stock Category',
  Voucher: 'Voucher',
};

const CONFIDENCE_CFG: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
  high:   { cls: 'bg-emerald-100 text-emerald-700 border-emerald-200', label: 'High confidence', icon: <CheckCircle className="w-3.5 h-3.5" /> },
  medium: { cls: 'bg-amber-100 text-amber-700 border-amber-200',       label: 'Medium — please confirm', icon: <AlertTriangle className="w-3.5 h-3.5" /> },
  low:    { cls: 'bg-red-100 text-red-700 border-red-200',             label: 'Low — please select type', icon: <XCircle className="w-3.5 h-3.5" /> },
};

const ROW_STATUS: Record<string, { cls: string; label: string }> = {
  new:                    { cls: 'bg-emerald-100 text-emerald-700', label: 'New' },
  valid:                  { cls: 'bg-emerald-100 text-emerald-700', label: 'New' },
  warning:                { cls: 'bg-amber-100 text-amber-700',     label: 'Warning' },
  error:                  { cls: 'bg-red-100 text-red-700',         label: 'Error' },
  duplicate_exact:        { cls: 'bg-red-100 text-red-800',         label: 'Exact dup' },
  duplicate_exact_forced: { cls: 'bg-orange-100 text-orange-700',   label: 'Force import' },
  duplicate_fuzzy:        { cls: 'bg-amber-100 text-amber-800',     label: 'Possible dup' },
  ref_missing:            { cls: 'bg-orange-100 text-orange-700',   label: 'Missing ref' },
  ref_similar:            { cls: 'bg-sky-100 text-sky-700',         label: 'Ref suggestion' },
};

const HISTORY_BADGE: Record<string, string> = {
  COMPLETED:  'bg-emerald-100 text-emerald-700',
  PARTIAL:    'bg-amber-100 text-amber-700',
  FAILED:     'bg-red-100 text-red-700',
  PROCESSING: 'bg-blue-100 text-blue-700',
  PENDING:    'bg-slate-100 text-slate-600',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return d.toLocaleDateString();
}

function friendlyCol(col: string) {
  return col.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Step indicators ──────────────────────────────────────────────────────────

const STEPS: Array<{ id: WizardStep; label: string }> = [
  { id: 'drop',     label: '1. Upload file' },
  { id: 'mapping',  label: '2. Map columns' },
  { id: 'preview',  label: '3. Review rows' },
  { id: 'progress', label: '4. Import' },
];

function StepIndicator({ current }: { current: WizardStep }) {
  const active = STEPS.findIndex(s => s.id === current);
  return (
    <div className="flex items-center gap-1 mb-6">
      {STEPS.map((step, i) => (
        <div key={step.id} className="flex items-center gap-1">
          <div className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all",
            i <= active
              ? "bg-indigo-600 text-white"
              : "bg-slate-100 text-slate-400",
          )}>
            <span>{i + 1}</span>
            <span className="hidden sm:inline">{step.label.slice(3)}</span>
          </div>
          {i < STEPS.length - 1 && (
            <div className={cn("h-px w-4 flex-shrink-0", i < active ? "bg-indigo-400" : "bg-slate-200")} />
          )}
        </div>
      ))}
    </div>
  );
}

// ─── History row ──────────────────────────────────────────────────────────────

function HistoryRow({ u }: { u: UploadHistory }) {
  const [expanded, setExpanded] = useState(false);
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
          <span className="text-xs text-slate-500 hidden sm:block">{u.imported_rows}/{u.total_rows || 0} imported</span>
          <span className={cn("px-2 py-0.5 rounded-full text-xs font-medium", HISTORY_BADGE[u.status] ?? HISTORY_BADGE.PENDING)}>
            {u.status.charAt(0) + u.status.slice(1).toLowerCase()}
          </span>
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </div>
      </div>
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Total', value: u.total_rows, color: 'text-slate-700' },
              { label: 'Imported', value: u.imported_rows, color: 'text-emerald-600' },
              { label: 'Invalid', value: u.invalid_rows, color: 'text-red-600' },
            ].map(s => (
              <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
                <p className={cn("text-xl font-bold", s.color)}>{s.value}</p>
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
  const [tab, setTab] = useState<'import' | 'history'>('import');

  // Wizard state
  const [step, setStep] = useState<WizardStep>('drop');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [parseResult, setParseResult] = useState<ParseResponse | null>(null);
  const [entityType, setEntityType] = useState('');
  const [colMapping, setColMapping] = useState<Record<string, string>>({});
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<ValidateResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [rowFilter, setRowFilter] = useState<RowFilter>('all');
  const [syncToTally, setSyncToTally] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [statusData, setStatusData] = useState<StatusResponse | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const [syncFreshness, setSyncFreshness] = useState<SyncFreshness | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data: history, isLoading: historyLoading } = useQuery<UploadHistory[]>({
    queryKey: ['upload-history'],
    queryFn: () => apiClient.get('/api/uploads').then(r => r.data),
    refetchInterval: tab === 'history' ? 15_000 : false,
  });

  // Clean up poll on unmount
  useEffect(() => () => { if (pollInterval) clearInterval(pollInterval); }, [pollInterval]);

  const resetWizard = () => {
    setStep('drop'); setFile(null); setParseResult(null); setEntityType('');
    setColMapping({}); setValidateResult(null); setSelectedIds(new Set());
    setRowFilter('all'); setCommitting(false); setStatusData(null); setUploadId(null);
    setSyncFreshness(null);
    if (pollInterval) { clearInterval(pollInterval); setPollInterval(null); }
  };

  // ── Step 1: file selection ──────────────────────────────────────────────────

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback(() => setIsDragging(false), []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  const handleParse = async () => {
    if (!file) return;
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await apiClient.post<ParseResponse>('/api/uploads/ingest/parse', fd, {
        headers: { 'Content-Type': undefined },
      });
      setParseResult(data);
      setEntityType(data.detected_entity_type);
      setColMapping(data.mapping_suggestions);
      setUploadId(data.upload_id);
      setStep('mapping');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const d = e?.response?.data?.detail;
      const desc = Array.isArray(d) ? d.map((x: { msg?: string }) => x?.msg || String(x)).join('; ') : (typeof d === 'string' ? d : 'Could not read file');
      toast({ title: 'Parse failed', description: desc, variant: 'destructive' });
    } finally {
      setParsing(false);
    }
  };

  // ── Step 2: column mapping + validate ──────────────────────────────────────

  const handleValidate = async () => {
    if (!uploadId) return;
    setValidating(true);
    try {
      const [{ data }, freshness] = await Promise.all([
        apiClient.post<ValidateResponse>(
          `/api/uploads/ingest/${uploadId}/validate`,
          { entity_type: entityType, column_mapping: colMapping },
        ),
        apiClient.get<SyncFreshness>('/api/uploads/sync-freshness').catch(() => ({ data: null })),
      ]);
      setValidateResult(data);
      setSyncFreshness(freshness.data);
      // Auto-select rows based on check_default from backend
      const autoSel = new Set(
        data.rows.filter(r => r.check_default && r.status !== 'error').map(r => r.row_id)
      );
      setSelectedIds(autoSel);
      setStep('preview');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const d = e?.response?.data?.detail;
      const desc = Array.isArray(d) ? d.map((x: { msg?: string }) => x?.msg || String(x)).join('; ') : (typeof d === 'string' ? d : 'Server error');
      toast({ title: 'Validation failed', description: desc, variant: 'destructive' });
    } finally {
      setValidating(false);
    }
  };

  // ── Step 3: row selection + commit ─────────────────────────────────────────

  const filteredRows = (validateResult?.rows ?? []).filter(r => {
    if (rowFilter === 'all') return true;
    return r.status === rowFilter;
  });

  const toggleRow = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    const all = filteredRows.map(r => r.row_id);
    const allSelected = all.every(id => selectedIds.has(id));
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allSelected) all.forEach(id => next.delete(id));
      else all.forEach(id => next.add(id));
      return next;
    });
  };

  const selectAllValid = () => {
    const valid = (validateResult?.rows ?? []).filter(r => r.status !== 'error').map(r => r.row_id);
    setSelectedIds(new Set(valid));
  };

  const deselectWarnings = () => {
    const warnings = (validateResult?.rows ?? []).filter(r => r.status === 'warning').map(r => r.row_id);
    setSelectedIds(prev => {
      const next = new Set(prev);
      warnings.forEach(id => next.delete(id));
      return next;
    });
  };

  // Apply a row-level action and sync back updated row from server
  const applyRowAction = async (
    rowId: number,
    action: string,
    field?: string,
    resolvedValue?: string,
  ) => {
    if (!uploadId || !validateResult) return;
    try {
      const { data } = await apiClient.post<{ row: RowResult }>(
        `/api/uploads/ingest/${uploadId}/row-action`,
        { row_id: rowId, action, field, resolved_value: resolvedValue },
      );
      setValidateResult(prev => {
        if (!prev) return prev;
        const rows = prev.rows.map(r => (r.row_id === rowId ? data.row : r));
        return { ...prev, rows };
      });
      // If force_import — auto-check that row
      if (action === 'force_import') {
        setSelectedIds(prev => { const n = new Set(prev); n.add(rowId); return n; });
      }
    } catch {
      toast({ title: 'Action failed', variant: 'destructive' });
    }
  };

  // Quick-create a referenced entity via management API, then re-validate the row
  const createReference = async (rowId: number, refEntityType: string, refName: string, field: string) => {
    if (!uploadId) return;
    try {
      const endpointMap: Record<string, string> = {
        'Stock Group':    '/api/management/stock-groups',
        'Stock Category': '/api/inventory/stock-categories',
        'Unit':           '/api/management/units',
        'Group':          '/api/management/groups',
      };
      const endpoint = endpointMap[refEntityType];
      if (!endpoint) { toast({ title: `Cannot auto-create ${refEntityType}`, variant: 'destructive' }); return; }
      await apiClient.post(endpoint, { name: refName });
      // Now re-resolve: use_existing with the just-created name
      await applyRowAction(rowId, 'use_existing', field, refName);
      toast({ title: `${refEntityType} "${refName}" created`, variant: 'success' });
    } catch {
      toast({ title: `Failed to create ${refEntityType}`, variant: 'destructive' });
    }
  };

  const syncNow = async () => {
    try {
      await apiClient.post('/api/tally/sync');
      toast({ title: 'Sync triggered', description: 'TallyPrime sync queued — re-validate after it completes.' });
      const { data } = await apiClient.get<SyncFreshness>('/api/uploads/sync-freshness');
      setSyncFreshness(data);
    } catch {
      toast({ title: 'Sync failed', variant: 'destructive' });
    }
  };

  const handleCommit = async () => {
    if (!uploadId || selectedIds.size === 0) return;
    setCommitting(true);
    try {
      await apiClient.post(`/api/uploads/ingest/${uploadId}/commit`, {
        selected_row_ids: [...selectedIds],
        sync_to_tally: syncToTally,
      });
      setStep('progress');

      // Poll status
      const interval = setInterval(async () => {
        try {
          const { data } = await apiClient.get<StatusResponse>(`/api/uploads/ingest/${uploadId}/status`);
          setStatusData(data);
          if (data.status === 'COMPLETED' || data.status === 'PARTIAL' || data.status === 'FAILED') {
            clearInterval(interval);
            setPollInterval(null);
            setStep('done');
            qc.invalidateQueries({ queryKey: ['upload-history'] });
          }
        } catch { /* network hiccup — continue polling */ }
      }, 1500);
      setPollInterval(interval);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const d = e?.response?.data?.detail;
      const desc = Array.isArray(d) ? d.map((x: { msg?: string }) => x?.msg || String(x)).join('; ') : (typeof d === 'string' ? d : 'Server error');
      toast({ title: 'Commit failed', description: desc, variant: 'destructive' });
      setCommitting(false);
    }
  };

  // ── Download template helper (legacy) ──────────────────────────────────────

  const downloadTemplate = async (type: string) => {
    try {
      const res = await apiClient.get(`/api/uploads/template/${type}`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a'); a.href = url; a.download = `${type}_template.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast({ title: 'Download failed', variant: 'destructive' }); }
  };

  const summary = validateResult?.summary;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header + tabs */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Bulk Imports</h2>
          <p className="text-sm text-slate-500">Smart import: auto-detects entity type, maps columns, and validates rows</p>
        </div>
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg">
          {(['import', 'history'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all capitalize",
                tab === t ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-900",
              )}
            >
              {t === 'import' ? <Upload className="w-3.5 h-3.5" /> : <History className="w-3.5 h-3.5" />}
              {t === 'import' ? 'Import' : `History${history?.length ? ` (${history.length})` : ''}`}
            </button>
          ))}
        </div>
      </div>

      {/* ── Import wizard ────────────────────────────────────────────────────── */}
      {tab === 'import' && (
        <div className="max-w-4xl space-y-6">
          {step !== 'drop' && <StepIndicator current={step} />}

          {/* Step 1: Drop zone */}
          {step === 'drop' && (
            <div className="space-y-4 max-w-xl">
              <div
                className={cn(
                  "border-2 border-dashed rounded-xl p-12 text-center transition-all cursor-pointer",
                  isDragging ? "border-indigo-400 bg-indigo-50" : "border-slate-200 hover:border-indigo-300 hover:bg-slate-50",
                )}
                onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.json" className="hidden"
                  onChange={e => e.target.files?.[0] && setFile(e.target.files[0])}
                />
                {file ? (
                  <div className="space-y-2">
                    <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center mx-auto">
                      <FileText className="w-6 h-6 text-indigo-600" />
                    </div>
                    <p className="font-semibold text-slate-900">{file.name}</p>
                    <p className="text-sm text-slate-500">{formatFileSize(file.size)}</p>
                    <p className="text-xs text-indigo-500">Click to change file</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto">
                      <Upload className="w-6 h-6 text-slate-400" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-700">Drop file here or click to browse</p>
                      <p className="text-sm text-slate-400 mt-1">CSV, XLSX, or JSON · max {10}MB</p>
                    </div>
                  </div>
                )}
              </div>

              <Button onClick={handleParse} disabled={!file || parsing} size="lg" className="w-full gap-2">
                {parsing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                {parsing ? 'Parsing file…' : 'Parse File'}
              </Button>

              {/* Quick-download templates */}
              <div className="pt-2">
                <p className="text-xs text-slate-400 mb-2 font-medium uppercase tracking-wide">Sample templates</p>
                <div className="flex flex-wrap gap-1.5">
                  {['ledgers', 'stock_items', 'stock_groups', 'units'].map(t => (
                    <button
                      key={t}
                      onClick={() => downloadTemplate(t)}
                      className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 bg-slate-100 hover:bg-indigo-50 px-2 py-1 rounded transition-colors"
                    >
                      <Download className="w-3 h-3" />
                      {t.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Step 2: Entity type + column mapping */}
          {step === 'mapping' && parseResult && (
            <div className="space-y-5">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Table2 className="w-4 h-4 text-indigo-600" />
                    Entity Type
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Detection result */}
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className={cn(
                      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
                      CONFIDENCE_CFG[parseResult.entity_confidence]?.cls,
                    )}>
                      {CONFIDENCE_CFG[parseResult.entity_confidence]?.icon}
                      {CONFIDENCE_CFG[parseResult.entity_confidence]?.label}
                    </div>
                    {parseResult.from_cache && (
                      <span className="inline-flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                        <CheckCircle className="w-3 h-3" /> Loaded from saved mapping
                      </span>
                    )}
                    {parseResult.entity_subtype && (
                      <span className="text-xs text-slate-500">Sub-type: <b>{parseResult.entity_subtype}</b></span>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
                    <Label className="shrink-0">Entity type</Label>
                    <Select value={entityType} onValueChange={v => {
                      setEntityType(v);
                      // Re-run mapping suggestions for new type (client-side)
                      const newMap: Record<string, string> = {};
                      parseResult.file_columns.forEach(col => {
                        if (parseResult.mapping_suggestions[col]) {
                          newMap[col] = parseResult.mapping_suggestions[col];
                        }
                      });
                      setColMapping(newMap);
                    }}>
                      <SelectTrigger className="w-48">
                        <SelectValue placeholder="Select type" />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(ENTITY_LABELS).map(([val, label]) => (
                          <SelectItem key={val} value={val}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <p className="text-xs text-slate-400">
                    {parseResult.total_rows.toLocaleString()} rows · {parseResult.file_columns.length} columns · {parseResult.file_format.toUpperCase()}
                  </p>
                </CardContent>
              </Card>

              {/* Column mapping table */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Column Mapping</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-slate-500 mb-4">
                    Map each file column to a schema field. Columns left unmapped will be ignored.
                  </p>
                  <div className="rounded-lg border border-slate-200 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50">
                        <tr>
                          <th className="text-left py-2.5 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide w-1/2">File Column</th>
                          <th className="text-left py-2.5 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide w-1/2">Maps to Schema Field</th>
                        </tr>
                      </thead>
                      <tbody>
                        {parseResult.file_columns.map(col => (
                          <tr key={col} className="border-t border-slate-100">
                            <td className="py-2 px-4 font-mono text-xs text-slate-700">{col}</td>
                            <td className="py-2 px-4">
                              <Select
                                value={colMapping[col] || '__none__'}
                                onValueChange={v => setColMapping(prev => {
                                  const next = { ...prev };
                                  if (v === '__none__') delete next[col];
                                  else next[col] = v;
                                  return next;
                                })}
                              >
                                <SelectTrigger className="h-7 text-xs">
                                  <SelectValue placeholder="— not mapped —" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">— not mapped —</SelectItem>
                                  {parseResult.schema_fields.map(f => (
                                    <SelectItem key={f} value={f}>{friendlyCol(f)}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Sample rows */}
                  {parseResult.sample_rows.length > 0 && (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-xs text-indigo-600 hover:underline select-none">
                        Preview first {Math.min(3, parseResult.sample_rows.length)} rows
                      </summary>
                      <div className="mt-2 overflow-x-auto rounded border border-slate-200">
                        <table className="text-xs min-w-full">
                          <thead className="bg-slate-50">
                            <tr>
                              {parseResult.file_columns.map(c => (
                                <th key={c} className="py-1.5 px-2 text-left font-medium text-slate-500 whitespace-nowrap">{c}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {parseResult.sample_rows.slice(0, 3).map((row, i) => (
                              <tr key={i} className="border-t border-slate-100">
                                {parseResult.file_columns.map(c => (
                                  <td key={c} className="py-1.5 px-2 text-slate-600 max-w-[120px] truncate">
                                    {String(row[c] ?? '')}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  )}
                </CardContent>
              </Card>

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('drop')} className="gap-2">
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>
                <Button onClick={handleValidate} disabled={!entityType || validating} className="gap-2 flex-1">
                  {validating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />}
                  {validating ? 'Validating…' : `Validate ${parseResult.total_rows.toLocaleString()} Rows`}
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Row preview + selection */}
          {step === 'preview' && validateResult && summary && (
            <div className="space-y-4">
              {/* Sync freshness banner */}
              {syncFreshness !== null && (
                <div className={cn(
                  "flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-xs border",
                  syncFreshness.connector_online
                    ? "bg-slate-50 border-slate-200 text-slate-600"
                    : "bg-amber-50 border-amber-200 text-amber-700",
                )}>
                  <span className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 shrink-0" />
                    {syncFreshness.last_sync_at
                      ? <>Data last synced: <b>{relTime(syncFreshness.last_sync_at)}</b> — duplicate and reference checks are based on this snapshot</>
                      : 'No Tally sync recorded yet — reference and duplicate checks may be incomplete'}
                  </span>
                  {syncFreshness.connector_online && (
                    <button
                      onClick={syncNow}
                      className="shrink-0 flex items-center gap-1 px-2 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                    >
                      <RefreshCw className="w-3 h-3" /> Sync now
                    </button>
                  )}
                </div>
              )}

              {/* Summary bar */}
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2 text-sm text-slate-700 font-medium flex-wrap">
                  <span className="text-emerald-600 font-bold">{summary.valid} new</span>
                  {summary.warnings > 0 && <><span className="text-slate-300">·</span><span className="text-amber-600 font-bold">{summary.warnings} flagged</span></>}
                  {summary.errors > 0 && <><span className="text-slate-300">·</span><span className="text-red-600 font-bold">{summary.errors} blocked</span></>}
                  <span className="text-slate-400">of {summary.total} total</span>
                </div>
                <div className="flex flex-wrap gap-1 ml-auto">
                  {([
                    { id: 'all', label: 'All' },
                    { id: 'new', label: 'New' },
                    { id: 'warning', label: 'Warning' },
                    { id: 'duplicate_exact', label: 'Exact dup' },
                    { id: 'duplicate_fuzzy', label: 'Possible dup' },
                    { id: 'ref_missing', label: 'Missing ref' },
                    { id: 'ref_similar', label: 'Ref suggestion' },
                    { id: 'error', label: 'Error' },
                  ] as const).map(({ id, label }) => {
                    const count = id === 'all'
                      ? validateResult.rows.length
                      : validateResult.rows.filter(r => r.status === id || (id === 'new' && r.status === 'valid')).length;
                    if (count === 0 && id !== 'all') return null;
                    return (
                      <button
                        key={id}
                        onClick={() => setRowFilter(id as RowFilter)}
                        className={cn(
                          "px-2 py-0.5 rounded text-xs font-medium transition-all",
                          rowFilter === id ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
                        )}
                      >
                        {label}{id !== 'all' ? ` (${count})` : ''}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Bulk actions */}
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <span className="text-slate-500">{selectedIds.size} selected</span>
                <button onClick={selectAllValid} className="text-indigo-600 hover:underline">Select all new</button>
                <button onClick={deselectWarnings} className="text-amber-600 hover:underline">Deselect warnings</button>
                <button onClick={() => setSelectedIds(new Set())} className="text-slate-400 hover:underline">Clear all</button>
              </div>

              {/* Table */}
              <div className="rounded-lg border border-slate-200 overflow-hidden">
                <div className="overflow-x-auto max-h-[460px] overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 sticky top-0 z-10">
                      <tr>
                        <th className="py-2.5 px-3 w-8">
                          <button onClick={toggleAll} className="text-slate-400 hover:text-slate-700">
                            {filteredRows.length > 0 && filteredRows.every(r => selectedIds.has(r.row_id))
                              ? <CheckSquare className="w-4 h-4" />
                              : <Square className="w-4 h-4" />}
                          </button>
                        </th>
                        <th className="py-2.5 px-2 text-left font-semibold text-slate-500 w-24">Status</th>
                        <th className="py-2.5 px-2 text-left font-semibold text-slate-500 w-10">Row</th>
                        {Object.keys(filteredRows[0]?.mapped ?? {}).slice(0, 4).map(f => (
                          <th key={f} className="py-2.5 px-2 text-left font-semibold text-slate-500 whitespace-nowrap">
                            {friendlyCol(f)}
                          </th>
                        ))}
                        <th className="py-2.5 px-2 text-left font-semibold text-slate-500">Issues / Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map(row => {
                        const badgeCfg = ROW_STATUS[row.status] ?? ROW_STATUS.new;
                        const isBlocked = row.status === 'error';
                        const isDupExact = row.status === 'duplicate_exact';
                        return (
                          <tr
                            key={row.row_id}
                            className={cn(
                              "border-t border-slate-100 align-top transition-colors",
                              selectedIds.has(row.row_id) ? "bg-indigo-50/40" : "hover:bg-slate-50",
                            )}
                          >
                            {/* Checkbox */}
                            <td className="py-2 px-3 pt-2.5">
                              <button
                                onClick={() => toggleRow(row.row_id)}
                                disabled={isBlocked}
                              >
                                {selectedIds.has(row.row_id)
                                  ? <CheckSquare className="w-3.5 h-3.5 text-indigo-600" />
                                  : <Square className={cn("w-3.5 h-3.5", isBlocked ? "text-slate-200" : "text-slate-400")} />}
                              </button>
                            </td>
                            {/* Status badge */}
                            <td className="py-2 px-2 pt-2.5">
                              <span className={cn("px-1.5 py-0.5 rounded text-xs font-medium whitespace-nowrap", badgeCfg.cls)}>
                                {badgeCfg.label}
                              </span>
                            </td>
                            {/* Row number */}
                            <td className="py-2 px-2 pt-2.5 text-slate-400">{row.row_id + 2}</td>
                            {/* Mapped field values */}
                            {Object.values(row.mapped).slice(0, 4).map((val, vi) => (
                              <td key={vi} className="py-2 px-2 pt-2.5 text-slate-700 max-w-[110px] truncate">
                                {String(val ?? '')}
                              </td>
                            ))}
                            {/* Issues + inline actions */}
                            <td className="py-2 px-2 pt-2 max-w-[280px] space-y-1">
                              {/* Field errors */}
                              {row.errors.map((e, i) => (
                                <div key={i} className="flex items-start gap-1 text-red-600">
                                  <XCircle className="w-3 h-3 mt-0.5 shrink-0" />
                                  <span>{e.field}: {e.message}</span>
                                </div>
                              ))}
                              {/* Field warnings */}
                              {row.warnings.map((w, i) => (
                                <div key={i} className="flex items-start gap-1 text-amber-600">
                                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                                  <span>{w.message}</span>
                                </div>
                              ))}
                              {/* Duplicate info */}
                              {row.duplicate_info && (
                                <div className="flex items-start gap-1.5 flex-wrap">
                                  <span className={cn("flex items-center gap-1", isDupExact ? "text-red-700" : "text-amber-700")}>
                                    <AlertTriangle className="w-3 h-3 shrink-0" />
                                    {isDupExact
                                      ? <>Exact match: <b>"{row.duplicate_info.matched_name}"</b></>
                                      : <>Similar to: <b>"{row.duplicate_info.matched_name}"</b> ({Math.round(row.duplicate_info.similarity * 100)}%)</>
                                    }
                                  </span>
                                  {isDupExact && (
                                    <button
                                      onClick={() => applyRowAction(row.row_id, 'force_import')}
                                      className="px-1.5 py-0.5 bg-orange-100 text-orange-700 hover:bg-orange-200 rounded text-xs font-medium transition-colors"
                                    >
                                      Force import
                                    </button>
                                  )}
                                  {!isDupExact && row.duplicate_info.match_type === 'fuzzy' && (
                                    <button
                                      onClick={() => applyRowAction(row.row_id, 'dismiss_dup')}
                                      className="px-1.5 py-0.5 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded text-xs transition-colors"
                                    >
                                      Confirm as new
                                    </button>
                                  )}
                                </div>
                              )}
                              {/* Reference issues */}
                              {row.ref_issues.map((ri, i) => (
                                <div key={i} className="space-y-1">
                                  <div className={cn(
                                    "flex items-center gap-1 flex-wrap",
                                    ri.match_type === 'missing' ? "text-orange-700" : "text-sky-700",
                                  )}>
                                    <Info className="w-3 h-3 shrink-0" />
                                    <span>
                                      {ri.match_type === 'missing'
                                        ? <>{ri.ref_entity_type} <b>"{ri.ref_name}"</b> not found</>
                                        : ri.match_type === 'intra_file'
                                          ? <span className="text-slate-500">{ri.ref_entity_type} "{ri.ref_name}" (in this file)</span>
                                          : <>{ri.ref_entity_type} <b>"{ri.ref_name}"</b> — suggestions:</>
                                      }
                                    </span>
                                  </div>
                                  {/* Action buttons for reference issues */}
                                  {ri.match_type === 'missing' && (
                                    <div className="flex gap-1 flex-wrap pl-4">
                                      <button
                                        onClick={() => createReference(row.row_id, ri.ref_entity_type, ri.ref_name, ri.field)}
                                        className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 hover:bg-indigo-200 rounded text-xs font-medium transition-colors whitespace-nowrap"
                                      >
                                        + Create {ri.ref_entity_type}
                                      </button>
                                    </div>
                                  )}
                                  {ri.match_type === 'similar' && ri.suggestions.length > 0 && (
                                    <div className="flex gap-1 flex-wrap pl-4">
                                      {ri.suggestions.slice(0, 2).map((s, si) => (
                                        <button
                                          key={si}
                                          onClick={() => applyRowAction(row.row_id, 'use_existing', ri.field, s.name)}
                                          className="px-1.5 py-0.5 bg-sky-50 text-sky-700 hover:bg-sky-100 border border-sky-200 rounded text-xs transition-colors whitespace-nowrap"
                                        >
                                          Use "{s.name}" ({Math.round(s.similarity * 100)}%)
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {filteredRows.length === 0 && (
                    <div className="py-10 text-center text-slate-400 text-sm">
                      No rows match the current filter
                    </div>
                  )}
                </div>
              </div>

              {/* Tally sync + commit */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox" checked={syncToTally} onChange={e => setSyncToTally(e.target.checked)}
                    className="w-4 h-4 text-indigo-600 rounded"
                  />
                  <Zap className="w-3.5 h-3.5 text-indigo-500" />
                  <span className="text-slate-700">Sync to TallyPrime after import</span>
                </label>
                <div className="flex gap-3 sm:ml-auto">
                  <Button variant="outline" onClick={() => setStep('mapping')} className="gap-2">
                    <ArrowLeft className="w-4 h-4" /> Back
                  </Button>
                  <Button
                    onClick={handleCommit}
                    disabled={selectedIds.size === 0 || committing}
                    className="gap-2"
                  >
                    {committing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                    Import {selectedIds.size} Row{selectedIds.size !== 1 ? 's' : ''}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Progress */}
          {(step === 'progress' || step === 'done') && (
            <div className="space-y-5 max-w-xl">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    {step === 'done'
                      ? <CheckCircle className="w-4 h-4 text-emerald-600" />
                      : <RefreshCw className="w-4 h-4 text-indigo-600 animate-spin" />}
                    {step === 'done' ? 'Import complete' : 'Importing…'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {statusData && (
                    <>
                      <Progress
                        value={statusData.total_rows > 0
                          ? Math.round((statusData.imported_rows / Math.min(statusData.total_rows, selectedIds.size)) * 100)
                          : 0}
                      />
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { label: 'Imported', value: statusData.imported_rows, color: 'text-emerald-600' },
                          { label: 'Total', value: Math.min(statusData.total_rows, selectedIds.size), color: 'text-slate-700' },
                          { label: 'Tally Jobs', value: statusData.tally_queued, color: 'text-indigo-600' },
                        ].map(s => (
                          <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
                            <p className={cn("text-2xl font-bold", s.color)}>{s.value}</p>
                            <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
                          </div>
                        ))}
                      </div>

                      {statusData.commit_summary?.errors && Array.isArray(statusData.commit_summary.errors) &&
                        statusData.commit_summary.errors.length > 0 && (
                        <div className="rounded-lg border border-red-100 overflow-hidden">
                          <div className="bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 flex items-center gap-2">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            {statusData.commit_summary.errors.length} commit errors
                          </div>
                          {(statusData.commit_summary.errors as Array<{row_id: number; message: string}>).slice(0, 5).map((e, i) => (
                            <div key={i} className="px-3 py-1.5 text-xs border-t border-red-50 text-red-600">
                              Row {(e.row_id ?? 0) + 2}: {e.message}
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}

                  {step === 'done' && (
                    <Button onClick={resetWizard} className="w-full gap-2">
                      <Upload className="w-4 h-4" /> Import another file
                    </Button>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}

      {/* ── History tab ──────────────────────────────────────────────────────── */}
      {tab === 'history' && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="w-4 h-4 text-indigo-600" /> Upload History
              </CardTitle>
              <span className="text-xs text-slate-400">{history?.length ?? 0} uploads</span>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {historyLoading ? (
              <div className="p-4 space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
            ) : !history?.length ? (
              <div className="py-16 text-center">
                <Upload className="w-10 h-10 text-slate-200 mx-auto mb-3" />
                <p className="text-slate-500 font-medium">No uploads yet</p>
                <Button size="sm" className="mt-4" onClick={() => setTab('import')}>Start importing</Button>
              </div>
            ) : (
              <div>{history.map(u => <HistoryRow key={u.id} u={u} />)}</div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
