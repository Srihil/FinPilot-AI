import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Upload, CheckCircle, AlertTriangle, Download,
  Clock, RefreshCw, ChevronDown, ChevronUp, History, Zap,
  ArrowRight, ArrowLeft, Table2, Info, XCircle,
  CheckSquare, Square, AlertCircle, Sparkles, Database,
  ShieldCheck, TrendingUp, FileSpreadsheet, Pencil, Save, X,
  Trash2, ChevronLeft, ChevronRight,
} from 'lucide-react';
import apiClient from '../../api/client';
import { BulkDeleteBar } from '../../components/ui/BulkDeleteBar';
import { bulkDeleteApi } from '../../api/endpoints';
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
  | 'new' | 'valid'
  | 'warning'
  | 'duplicate_exact'
  | 'duplicate_exact_forced'
  | 'duplicate_fuzzy'
  | 'ref_missing'
  | 'ref_similar'
  | 'error';

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
  row_counts: { imported?: number; failed?: number; pending?: number };
}

interface UploadHistoryPage {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: UploadHistory[];
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

const ROW_STATUS: Record<string, { dot: string; badge: string; label: string }> = {
  new:                    { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200',  label: 'New' },
  valid:                  { dot: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200',  label: 'New' },
  warning:                { dot: 'bg-amber-400',   badge: 'bg-amber-50 text-amber-700 ring-amber-200',        label: 'Warning' },
  error:                  { dot: 'bg-red-500',     badge: 'bg-red-50 text-red-700 ring-red-200',              label: 'Error' },
  duplicate_exact:        { dot: 'bg-red-400',     badge: 'bg-red-50 text-red-700 ring-red-200',              label: 'Exact dup' },
  duplicate_exact_forced: { dot: 'bg-orange-400',  badge: 'bg-orange-50 text-orange-700 ring-orange-200',     label: 'Force import' },
  duplicate_fuzzy:        { dot: 'bg-amber-400',   badge: 'bg-amber-50 text-amber-800 ring-amber-200',        label: 'Possible dup' },
  ref_missing:            { dot: 'bg-orange-400',  badge: 'bg-orange-50 text-orange-700 ring-orange-200',     label: 'Missing ref' },
  ref_similar:            { dot: 'bg-sky-400',     badge: 'bg-sky-50 text-sky-700 ring-sky-200',              label: 'Ref match' },
};

const HISTORY_STATUS: Record<string, { cls: string; label: string }> = {
  COMPLETED:  { cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', label: 'Completed' },
  PARTIAL:    { cls: 'bg-amber-50 text-amber-700 ring-amber-200',       label: 'Partial' },
  FAILED:     { cls: 'bg-red-50 text-red-700 ring-red-200',             label: 'Failed' },
  PROCESSING: { cls: 'bg-blue-50 text-blue-700 ring-blue-200',          label: 'Processing' },
  PENDING:    { cls: 'bg-slate-100 text-slate-600 ring-slate-200',      label: 'Pending' },
};

const STEPS: Array<{ id: WizardStep; label: string; desc: string }> = [
  { id: 'drop',     label: 'Upload',  desc: 'Choose file' },
  { id: 'mapping',  label: 'Map',     desc: 'Confirm columns' },
  { id: 'preview',  label: 'Review',  desc: 'Check rows' },
  { id: 'progress', label: 'Import',  desc: 'Processing' },
];

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

function safeDetail(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const d = e?.response?.data?.detail;
  return Array.isArray(d)
    ? d.map((x: { msg?: string }) => x?.msg || String(x)).join('; ')
    : typeof d === 'string' ? d : fallback;
}

// ─── Step Indicator ───────────────────────────────────────────────────────────

function StepIndicator({ current }: { current: WizardStep }) {
  const activeIdx = STEPS.findIndex(s => s.id === current);
  return (
    <div className="flex items-center mb-8">
      {STEPS.map((step, i) => {
        const done    = i < activeIdx;
        const active  = i === activeIdx;
        const future  = i > activeIdx;
        return (
          <div key={step.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all",
                done   ? "bg-indigo-600 text-white"
                : active ? "bg-indigo-600 text-white ring-4 ring-indigo-100"
                : "bg-slate-100 text-slate-400",
              )}>
                {done ? <CheckCircle className="w-4 h-4" /> : i + 1}
              </div>
              <div className="text-center">
                <p className={cn("text-xs font-semibold", active ? "text-indigo-700" : done ? "text-slate-600" : "text-slate-400")}>
                  {step.label}
                </p>
                <p className="text-[10px] text-slate-400 hidden sm:block">{step.desc}</p>
              </div>
            </div>
            {i < STEPS.length - 1 && (
              <div className={cn(
                "flex-1 h-0.5 mx-3 mb-5 rounded-full transition-all",
                i < activeIdx ? "bg-indigo-500" : "bg-slate-200",
              )} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── History Row ──────────────────────────────────────────────────────────────

function HistoryRow({ u, onDelete, isSelected, onToggleSelect }: {
  u: UploadHistory;
  onDelete: (id: string) => void;
  isSelected?: boolean;
  onToggleSelect?: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const st = HISTORY_STATUS[u.status] ?? HISTORY_STATUS.PENDING;
  const pct = u.total_rows > 0 ? Math.round((u.imported_rows / u.total_rows) * 100) : 0;

  const downloadFile = async (type: 'remaining' | 'report') => {
    try {
      const res = await apiClient.get(`/api/uploads/ingest/${u.id}/${type}`, { responseType: 'blob' });
      // Prefer server-supplied filename (needs Content-Disposition exposed via CORS).
      // Fall back to original filename base + correct extension so format always matches.
      const cd = res.headers['content-disposition'] || '';
      const cdMatch = cd.match(/filename="?([^";]+)"?/);
      let filename = cdMatch ? cdMatch[1].trim() : '';
      if (!filename) {
        const origExt = (u.original_filename || '').split('.').pop()?.toLowerCase() || 'csv';
        const base = (u.original_filename || 'upload').replace(/\.[^.]+$/, '');
        const ts = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14);
        filename = `${base}_${type === 'remaining' ? 'remaining' : 'report'}_${ts}.${origExt}`;
      }
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
    } catch { toast({ title: `Download failed`, variant: 'destructive' }); }
  };

  const rc = u.row_counts ?? {};
  // pending rows in upload_rows = imported to DB, awaiting Tally sync (NOT "remaining to import")
  // failed rows in upload_rows = failed during DB commit (need re-import)
  const hasRows = (rc.imported ?? 0) + (rc.failed ?? 0) + (rc.pending ?? 0) > 0;
  const isDone = ['COMPLETED', 'PARTIAL', 'FAILED'].includes(u.status);
  // Show "Download Remaining" when there are failed rows OR when the upload is partial/failed
  // (which means some rows weren't selected or errored — row_report has the full picture)
  const hasRemaining = (rc.failed ?? 0) > 0
    || (isDone && u.status !== 'COMPLETED')
    || (isDone && u.imported_rows > 0 && u.imported_rows < u.total_rows);
  // Show download buttons for any completed upload that processed rows
  const canDownload = hasRows || (isDone && u.total_rows > 0);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await apiClient.delete(`/api/uploads/${u.id}`);
      onDelete(u.id);
      toast({ title: 'Import entry deleted', variant: 'success' });
    } catch {
      toast({ title: 'Delete failed', variant: 'destructive' });
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <div className="border-b border-slate-100 last:border-0">
      <div
        className="flex items-center gap-4 py-3.5 px-5 hover:bg-slate-50/70 cursor-pointer transition-colors group"
        onClick={() => setExpanded(e => !e)}
      >
        {onToggleSelect && (
          <button
            onClick={e => { e.stopPropagation(); onToggleSelect(u.id); }}
            className="p-0.5 rounded shrink-0 text-slate-300 hover:text-indigo-600 transition-colors"
          >
            {isSelected ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4" />}
          </button>
        )}
        <FileSpreadsheet className="w-4 h-4 text-slate-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-900 truncate">{u.original_filename}</p>
          <p className="text-xs text-slate-400 mt-0.5">{u.upload_type?.replace(/_/g, ' ') || 'Unknown type'} · {relTime(u.created_at)}</p>
        </div>
        <div className="hidden sm:flex items-center gap-1.5 w-32 shrink-0">
          <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-xs text-slate-500 shrink-0">{pct}%</span>
        </div>
        <span className="text-xs text-slate-500 hidden md:block shrink-0">{u.imported_rows} / {u.total_rows} rows</span>
        <span className={cn("px-2.5 py-0.5 rounded-full text-xs font-medium ring-1 shrink-0", st.cls)}>{st.label}</span>
        <div className="flex items-center gap-1 shrink-0">
          {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          <button
            onClick={e => { e.stopPropagation(); setConfirmDelete(true); setExpanded(false); }}
            className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all"
            title="Delete history entry"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {confirmDelete && (
        <div className="mx-5 mb-3 rounded-xl border border-red-200 bg-red-50 p-4 flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center shrink-0 mt-0.5">
            <Trash2 className="w-4 h-4 text-red-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-red-900">Delete this import entry?</p>
            <p className="text-xs text-red-700 mt-0.5 truncate">
              <span className="font-medium">"{u.original_filename}"</span> — only the history record is removed, imported data stays.
            </p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-semibold hover:bg-red-700 disabled:opacity-60 transition-colors"
              >
                {deleting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                {deleting ? 'Deleting…' : 'Yes, delete'}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="px-3 py-1.5 rounded-lg bg-white border border-red-200 text-red-700 text-xs font-medium hover:bg-red-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {expanded && (
        <div className="px-5 pb-4 space-y-3">
          {/* Row-level outcome counts (from upload_rows table) */}
          {hasRows && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-slate-500 font-medium">Row outcomes:</span>
              {(rc.imported ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 font-medium">
                  <CheckCircle className="w-3 h-3" /> {rc.imported} imported
                </span>
              )}
              {(rc.pending ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 ring-1 ring-blue-200 font-medium">
                  <RefreshCw className="w-3 h-3" /> {rc.pending} pending
                </span>
              )}
              {(rc.failed ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-700 ring-1 ring-red-200 font-medium">
                  <XCircle className="w-3 h-3" /> {rc.failed} failed
                </span>
              )}
            </div>
          )}

          {/* Download buttons */}
          {canDownload && (
            <div className="flex gap-2 flex-wrap">
              {hasRemaining && (
                <button
                  onClick={() => downloadFile('remaining')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-amber-200 text-amber-700 bg-amber-50 hover:bg-amber-100 transition-colors"
                  title="Download unimported rows (unselected + failed) for re-upload"
                >
                  <Download className="w-3.5 h-3.5" /> Download Remaining Rows
                </button>
              )}
              <button
                onClick={() => downloadFile('report')}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 bg-slate-50 hover:bg-slate-100 transition-colors"
                title="Download full audit report with status & error details"
              >
                <Download className="w-3.5 h-3.5" /> Download Full Report
              </button>
            </div>
          )}

          <div className="grid grid-cols-4 gap-3">
            {[
              { label: 'Total Rows',  value: u.total_rows,    cls: 'text-slate-700' },
              { label: 'Imported',    value: u.imported_rows, cls: 'text-emerald-600' },
              { label: 'Invalid',     value: u.invalid_rows,  cls: 'text-red-500' },
              { label: 'Valid',       value: u.valid_rows,    cls: 'text-indigo-600' },
            ].map(s => (
              <div key={s.label} className="bg-slate-50 rounded-xl p-3.5 text-center border border-slate-100">
                <p className={cn("text-2xl font-bold", s.cls)}>{s.value}</p>
                <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>
          {u.errors?.length > 0 && (
            <div className="rounded-xl border border-red-100 overflow-hidden">
              <div className="bg-red-50 px-4 py-2.5 text-xs font-semibold text-red-700 flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5" /> Sample errors
              </div>
              {u.errors.slice(0, 5).map((e, i) => (
                <div key={i} className="flex gap-4 px-4 py-2 text-xs border-t border-red-50">
                  <span className="text-slate-400 shrink-0 font-mono">Row {e.row}</span>
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

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function UploadsPage() {
  const [tab, setTab] = useState<'import' | 'history'>('import');
  const [historyPage, setHistoryPage] = useState(1);
  const [historySelectedIds, setHistorySelectedIds] = useState<Set<string>>(new Set());
  const toggleHistorySelect = (id: string) => setHistorySelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const clearHistorySelection = () => setHistorySelectedIds(new Set());
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
  const [committing, setCommitting] = useState(false);
  const [statusData, setStatusData] = useState<StatusResponse | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [pollInterval, setPollInterval] = useState<ReturnType<typeof setInterval> | null>(null);
  const [syncFreshness, setSyncFreshness] = useState<SyncFreshness | null>(null);
  const [editingRowId, setEditingRowId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<Record<string, string>>({});
  const [savingEdit, setSavingEdit] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data: historyData, isLoading: historyLoading } = useQuery<UploadHistoryPage>({
    queryKey: ['upload-history', historyPage],
    queryFn: () => apiClient.get('/api/uploads', { params: { page: historyPage, page_size: 10 } }).then(r => r.data),
    refetchInterval: tab === 'history' ? 15_000 : false,
  });
  const history = historyData?.items ?? [];
  const historyTotal = historyData?.total ?? 0;
  const historyPages = historyData?.pages ?? 1;

  useEffect(() => () => { if (pollInterval) clearInterval(pollInterval); }, [pollInterval]);

  // ── Session restore on mount ───────────────────────────────────────────────
  useEffect(() => {
    const savedId = sessionStorage.getItem('fp_wizard_upload_id');
    if (!savedId) return;
    apiClient.get(`/api/uploads/ingest/${savedId}/restore`)
      .then(({ data }) => {
        setUploadId(data.upload_id);
        setEntityType(data.entity_type);
        setColMapping(data.column_mapping || {});
        if (data.wizard_step === 'mapping' && data.parse_result) {
          setParseResult(data.parse_result);
          setStep('mapping');
          toast({ title: 'Session restored', description: 'Continue mapping your columns.' });
        } else if (data.wizard_step === 'preview' && data.validate_result) {
          setParseResult(data.parse_result);
          setValidateResult(data.validate_result);
          const autoSel = new Set<number>(
            data.validate_result.rows.filter((r: { check_default: boolean; status: string }) => r.check_default && r.status !== 'error').map((r: { row_id: number }) => r.row_id)
          );
          setSelectedIds(autoSel);
          setStep('preview');
          toast({ title: 'Session restored', description: 'Continue reviewing your rows.' });
        } else if (data.wizard_step === 'progress') {
          setStatusData(data.status_data);
          setStep('progress');
        } else if (data.wizard_step === 'done') {
          setStatusData(data.status_data);
          setStep('done');
        }
      })
      .catch(() => sessionStorage.removeItem('fp_wizard_upload_id'));
  }, []);

  // Save uploadId to sessionStorage whenever it changes
  useEffect(() => {
    if (uploadId) sessionStorage.setItem('fp_wizard_upload_id', uploadId);
  }, [uploadId]);

  const deleteCurrentUpload = async (id: string | null) => {
    if (!id) return;
    try { await apiClient.delete(`/api/uploads/${id}`); } catch { /* best effort */ }
    qc.invalidateQueries({ queryKey: ['upload-history'] });
  };

  const resetWizard = (keepHistory = false) => {
    if (!keepHistory && uploadId) deleteCurrentUpload(uploadId);
    sessionStorage.removeItem('fp_wizard_upload_id');
    setStep('drop'); setFile(null); setParseResult(null); setEntityType('');
    setColMapping({}); setValidateResult(null); setSelectedIds(new Set());
    setRowFilter('all'); setCommitting(false); setStatusData(null); setUploadId(null);
    setSyncFreshness(null);
    if (pollInterval) { clearInterval(pollInterval); setPollInterval(null); }
  };

  const goBackToUpload = () => {
    // Delete the upload record so no orphan remains in history
    if (uploadId) deleteCurrentUpload(uploadId);
    sessionStorage.removeItem('fp_wizard_upload_id');
    setStep('drop'); setFile(null); setParseResult(null); setEntityType('');
    setColMapping({}); setUploadId(null); setSyncFreshness(null);
  };

  const goBackToMapping = () => {
    // Keep the upload (rows are still valid), just go back one step
    setStep('mapping'); setValidateResult(null); setSelectedIds(new Set()); setRowFilter('all');
  };

  // ── Drag & Drop ────────────────────────────────────────────────────────────

  const handleDragOver  = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback(() => setIsDragging(false), []);
  const handleDrop      = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  // ── Step 1: Parse ──────────────────────────────────────────────────────────

  const handleParse = async () => {
    if (!file) return;
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await apiClient.post<ParseResponse>('/api/uploads/ingest/parse', fd, {
        headers: { 'Content-Type': undefined },
      });
      setParseResult(data); setEntityType(data.detected_entity_type);
      setColMapping(data.mapping_suggestions); setUploadId(data.upload_id);
      setStep('mapping');
    } catch (err) {
      toast({ title: 'Parse failed', description: safeDetail(err, 'Could not read file'), variant: 'destructive' });
    } finally { setParsing(false); }
  };

  // ── Step 2: Validate ───────────────────────────────────────────────────────

  const handleValidate = async () => {
    if (!uploadId) return;
    setValidating(true);
    try {
      const [{ data }, freshness] = await Promise.all([
        apiClient.post<ValidateResponse>(`/api/uploads/ingest/${uploadId}/validate`,
          { entity_type: entityType, column_mapping: colMapping }),
        apiClient.get<SyncFreshness>('/api/uploads/sync-freshness').catch(() => ({ data: null })),
      ]);
      setValidateResult(data); setSyncFreshness(freshness.data);
      setSelectedIds(new Set(data.rows.filter(r => r.check_default && r.status !== 'error').map(r => r.row_id)));
      setStep('preview');
    } catch (err) {
      toast({ title: 'Validation failed', description: safeDetail(err, 'Server error'), variant: 'destructive' });
    } finally { setValidating(false); }
  };

  // ── Step 3: Selection helpers ──────────────────────────────────────────────

  const filteredRows = (validateResult?.rows ?? []).filter(r =>
    rowFilter === 'all' ? true : r.status === rowFilter
  );

  const toggleRow = (id: number) => setSelectedIds(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });

  const toggleAll = () => {
    const all = filteredRows.map(r => r.row_id);
    const allSel = all.every(id => selectedIds.has(id));
    setSelectedIds(prev => {
      const n = new Set(prev);
      if (allSel) all.forEach(id => n.delete(id)); else all.forEach(id => n.add(id));
      return n;
    });
  };

  const applyRowAction = async (rowId: number, action: string, field?: string, resolvedValue?: string) => {
    if (!uploadId || !validateResult) return;
    try {
      const { data } = await apiClient.post<{ row: RowResult }>(
        `/api/uploads/ingest/${uploadId}/row-action`,
        { row_id: rowId, action, field, resolved_value: resolvedValue },
      );
      setValidateResult(prev => prev ? { ...prev, rows: prev.rows.map(r => r.row_id === rowId ? data.row : r) } : prev);
      if (action === 'force_import') setSelectedIds(prev => { const n = new Set(prev); n.add(rowId); return n; });
    } catch { toast({ title: 'Action failed', variant: 'destructive' }); }
  };

  const ENTITY_CREATE_ENDPOINTS: Record<string, { url: string; body: (name: string) => object }> = {
    'Ledger':         { url: '/api/management/ledgers',       body: n => ({ name: n, parent_group: 'Sundry Debtors', opening_balance: 0 }) },
    'Stock Group':    { url: '/api/management/stock-groups',  body: n => ({ name: n }) },
    'Stock Category': { url: '/api/inventory/stock-categories', body: n => ({ name: n }) },
    'Unit':           { url: '/api/management/units',         body: n => ({ name: n, symbol: n.slice(0, 8), decimal_places: 0 }) },
    'Group':          { url: '/api/management/groups',        body: n => ({ name: n, parent: 'Primary' }) },
  };

  const createReference = async (rowId: number, refEntityType: string, refName: string, field: string) => {
    if (!uploadId) return;
    const cfg = ENTITY_CREATE_ENDPOINTS[refEntityType];
    if (!cfg) { toast({ title: `Cannot auto-create ${refEntityType}`, description: 'Please create it manually first', variant: 'destructive' }); return; }
    try {
      await apiClient.post(cfg.url, cfg.body(refName));
      await applyRowAction(rowId, 'use_existing', field, refName);
      toast({ title: `${refEntityType} "${refName}" created`, variant: 'success' });
    } catch { toast({ title: `Failed to create ${refEntityType}`, variant: 'destructive' }); }
  };

  const startEdit = (row: RowResult) => {
    const draft: Record<string, string> = {};
    Object.entries(row.mapped).forEach(([k, v]) => { draft[k] = String(v ?? ''); });
    setEditDraft(draft);
    setEditingRowId(row.row_id);
  };

  const cancelEdit = () => { setEditingRowId(null); setEditDraft({}); };

  const saveEdit = async (rowId: number) => {
    if (!uploadId) return;
    setSavingEdit(true);
    try {
      const { data } = await apiClient.post<{ row: RowResult }>(
        `/api/uploads/ingest/${uploadId}/row-action`,
        { row_id: rowId, action: 'update_mapped', updates: editDraft },
      );
      setValidateResult(prev => prev ? { ...prev, rows: prev.rows.map(r => r.row_id === rowId ? data.row : r) } : prev);
      // Auto-select if now importable
      if (data.row.check_default && data.row.status !== 'error') {
        setSelectedIds(prev => { const n = new Set(prev); n.add(rowId); return n; });
      }
      setEditingRowId(null); setEditDraft({});
      toast({ title: 'Row updated', variant: 'success' });
    } catch { toast({ title: 'Failed to update row', variant: 'destructive' }); }
    finally { setSavingEdit(false); }
  };

  const syncNow = async () => {
    try {
      await apiClient.post('/api/tally/sync');
      toast({ title: 'Sync triggered' });
      const { data } = await apiClient.get<SyncFreshness>('/api/uploads/sync-freshness');
      setSyncFreshness(data);
    } catch { toast({ title: 'Sync failed', variant: 'destructive' }); }
  };

  // ── Step 4: Commit ─────────────────────────────────────────────────────────

  const handleCommit = async () => {
    if (!uploadId || selectedIds.size === 0) return;
    setCommitting(true);
    try {
      await apiClient.post(`/api/uploads/ingest/${uploadId}/commit`, {
        selected_row_ids: [...selectedIds], sync_to_tally: true,
      });
      setStep('progress');
      const interval = setInterval(async () => {
        try {
          const { data } = await apiClient.get<StatusResponse>(`/api/uploads/ingest/${uploadId}/status`);
          setStatusData(data);
          if (['COMPLETED', 'PARTIAL', 'FAILED'].includes(data.status)) {
            clearInterval(interval); setPollInterval(null);
            sessionStorage.removeItem('fp_wizard_upload_id'); // import done — clear session
            setStep('done');
            // Invalidate all pages that may show bulk-imported data
            [
              ['upload-history'],
              ['ledgers-tree'],
              ['stock-items-tree'],
              ['stock-groups-tree'],
              ['stock-groups-all'],
              ['stock-categories-tree'],
              ['stock-categories'],
              ['units-all'],
              ['godowns-all'],
              ['tally-activity'],
            ].forEach(key => qc.invalidateQueries({ queryKey: key }));
          }
        } catch { /* continue */ }
      }, 1500);
      setPollInterval(interval);
    } catch (err) {
      toast({ title: 'Commit failed', description: safeDetail(err, 'Server error'), variant: 'destructive' });
      setCommitting(false);
    }
  };

  const downloadTemplate = async (type: string) => {
    try {
      const res = await apiClient.get(`/api/uploads/template/${type}`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }));
      const a = document.createElement('a'); a.href = url; a.download = `${type}_template.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast({ title: 'Download failed', variant: 'destructive' }); }
  };

  const summary = validateResult?.summary;

  // Filter tabs config
  const FILTER_TABS = [
    { id: 'all'            as RowFilter, label: 'All',          color: 'text-slate-600' },
    { id: 'new'            as RowFilter, label: 'New',          color: 'text-emerald-600' },
    { id: 'warning'        as RowFilter, label: 'Warnings',     color: 'text-amber-600' },
    { id: 'duplicate_fuzzy'as RowFilter, label: 'Possible dup', color: 'text-amber-700' },
    { id: 'duplicate_exact'as RowFilter, label: 'Exact dup',    color: 'text-red-600' },
    { id: 'ref_missing'    as RowFilter, label: 'Missing ref',  color: 'text-orange-600' },
    { id: 'ref_similar'    as RowFilter, label: 'Ref match',    color: 'text-sky-600' },
    { id: 'error'          as RowFilter, label: 'Errors',       color: 'text-red-700' },
  ] as const;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-0 h-full flex flex-col">

      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pb-5 border-b border-slate-100">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-600" />
            Bulk Imports
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">Smart import — auto-detects entity type, maps columns, and validates rows before importing</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex p-1 bg-slate-100 rounded-xl gap-1">
            {(['import', 'history'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  tab === t ? "bg-white text-indigo-700 shadow-sm" : "text-slate-500 hover:text-slate-800",
                )}
              >
                {t === 'import' ? <Upload className="w-4 h-4" /> : <History className="w-4 h-4" />}
                {t === 'import' ? 'Import' : `History${history?.length ? ` (${history.length})` : ''}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Import Wizard ─────────────────────────────────────────────────────── */}
      {tab === 'import' && (
        <div className="flex-1 pt-6 space-y-6">
          {step !== 'drop' && <StepIndicator current={step} />}

          {/* ── Step 1: Drop Zone ────────────────────────────────────────────── */}
          {step === 'drop' && (
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
              {/* Drop area */}
              <div className="lg:col-span-3 space-y-4">
                <div
                  className={cn(
                    "relative border-2 border-dashed rounded-2xl p-10 text-center transition-all cursor-pointer group",
                    isDragging
                      ? "border-indigo-400 bg-indigo-50/80 scale-[1.01]"
                      : "border-slate-200 hover:border-indigo-300 hover:bg-slate-50/80",
                  )}
                  onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls,.json" className="hidden"
                    onChange={e => e.target.files?.[0] && setFile(e.target.files[0])} />

                  {file ? (
                    <div className="space-y-3">
                      <div className="w-16 h-16 rounded-2xl bg-indigo-100 flex items-center justify-center mx-auto shadow-sm">
                        <FileSpreadsheet className="w-8 h-8 text-indigo-600" />
                      </div>
                      <div>
                        <p className="font-semibold text-slate-900 text-base">{file.name}</p>
                        <p className="text-sm text-slate-500 mt-1">{formatFileSize(file.size)}</p>
                      </div>
                      <p className="text-xs text-indigo-500 group-hover:underline">Click to change file</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-100 to-slate-100 flex items-center justify-center mx-auto shadow-sm group-hover:from-indigo-200 transition-all">
                        <Upload className="w-8 h-8 text-indigo-500" />
                      </div>
                      <div>
                        <p className="text-base font-semibold text-slate-700">Drop your file here</p>
                        <p className="text-sm text-slate-400 mt-1">or <span className="text-indigo-600 font-medium">browse to upload</span></p>
                        <p className="text-xs text-slate-400 mt-2">CSV, XLSX, XLS, JSON · max 10 MB</p>
                      </div>
                    </div>
                  )}
                </div>

                <Button
                  onClick={handleParse}
                  disabled={!file || parsing}
                  size="lg"
                  className="w-full gap-2 h-12 text-base rounded-xl"
                >
                  {parsing ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                  {parsing ? 'Analysing file…' : 'Parse & Auto-detect'}
                </Button>
              </div>

              {/* Info panel */}
              <div className="lg:col-span-2 space-y-4">
                <div className="rounded-2xl border border-slate-100 bg-slate-50 p-5 space-y-4">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">What happens next</p>
                  {[
                    { icon: Sparkles,    title: 'Auto-detection',     desc: 'AI identifies the entity type from your column names' },
                    { icon: Table2,      title: 'Column mapping',     desc: 'Map your file columns to the correct schema fields' },
                    { icon: ShieldCheck, title: 'Row validation',     desc: 'Each row is checked for duplicates, missing refs, and errors' },
                    { icon: TrendingUp,  title: 'Import & sync',      desc: 'Import to FinPilot and optionally push to TallyPrime' },
                  ].map(({ icon: Icon, title, desc }) => (
                    <div key={title} className="flex items-start gap-3">
                      <div className="w-7 h-7 rounded-lg bg-indigo-100 flex items-center justify-center shrink-0 mt-0.5">
                        <Icon className="w-3.5 h-3.5 text-indigo-600" />
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-slate-700">{title}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="rounded-2xl border border-slate-100 p-5">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Sample templates</p>
                  <div className="grid grid-cols-2 gap-2">
                    {['ledgers', 'stock_items', 'stock_groups', 'units'].map(t => (
                      <button
                        key={t}
                        onClick={() => downloadTemplate(t)}
                        className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-indigo-700 bg-white hover:bg-indigo-50 border border-slate-200 hover:border-indigo-200 px-3 py-2 rounded-lg transition-all font-medium"
                      >
                        <Download className="w-3.5 h-3.5 shrink-0" />
                        {t.replace('_', ' ')}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Step 2: Column Mapping ───────────────────────────────────────── */}
          {step === 'mapping' && parseResult && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                {/* Entity type card */}
                <div className="rounded-2xl border border-slate-200 p-5 space-y-4 bg-white">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center">
                      <Database className="w-4 h-4 text-indigo-600" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-800">Entity Type</p>
                      <p className="text-xs text-slate-500">What are you importing?</p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {/* Confidence badge */}
                    <div className={cn(
                      "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ring-1",
                      parseResult.entity_confidence === 'high'
                        ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                        : parseResult.entity_confidence === 'medium'
                        ? 'bg-amber-50 text-amber-700 ring-amber-200'
                        : 'bg-red-50 text-red-700 ring-red-200',
                    )}>
                      {parseResult.entity_confidence === 'high'
                        ? <><CheckCircle className="w-3.5 h-3.5" /> High confidence</>
                        : parseResult.entity_confidence === 'medium'
                        ? <><AlertTriangle className="w-3.5 h-3.5" /> Please confirm</>
                        : <><XCircle className="w-3.5 h-3.5" /> Please select</>}
                    </div>

                    {parseResult.from_cache && (
                      <div className="flex items-center gap-1.5 text-xs text-indigo-600 bg-indigo-50 px-3 py-1.5 rounded-lg">
                        <Sparkles className="w-3.5 h-3.5" /> Loaded from saved mapping
                      </div>
                    )}

                    <div className="space-y-1.5">
                      <Label className="text-xs text-slate-600">Entity type</Label>
                      <Select value={entityType} onValueChange={v => {
                        setEntityType(v);
                        const m: Record<string, string> = {};
                        parseResult.file_columns.forEach(col => {
                          if (parseResult.mapping_suggestions[col]) m[col] = parseResult.mapping_suggestions[col];
                        });
                        setColMapping(m);
                      }}>
                        <SelectTrigger className="rounded-lg">
                          <SelectValue placeholder="Select type…" />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ENTITY_LABELS).map(([val, label]) => (
                            <SelectItem key={val} value={val}>{label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-100 space-y-1.5">
                    <div className="flex justify-between text-xs text-slate-500">
                      <span>Rows detected</span>
                      <span className="font-semibold text-slate-700">{parseResult.total_rows.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between text-xs text-slate-500">
                      <span>Columns</span>
                      <span className="font-semibold text-slate-700">{parseResult.file_columns.length}</span>
                    </div>
                    <div className="flex justify-between text-xs text-slate-500">
                      <span>Format</span>
                      <span className="font-semibold text-slate-700 uppercase">{parseResult.file_format}</span>
                    </div>
                  </div>
                </div>

                {/* Column mapping table */}
                <div className="lg:col-span-2 rounded-2xl border border-slate-200 overflow-hidden bg-white">
                  <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-semibold text-slate-800">Column Mapping</p>
                      <p className="text-xs text-slate-500 mt-0.5">Map file columns to schema fields — unmapped columns are ignored</p>
                    </div>
                    <span className="text-xs text-slate-400 bg-slate-50 px-2 py-1 rounded-lg">
                      {Object.keys(colMapping).length} / {parseResult.file_columns.length} mapped
                    </span>
                  </div>
                  <div className="overflow-y-auto max-h-[380px]">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          <th className="text-left py-2.5 px-5 text-xs font-semibold text-slate-500 uppercase tracking-wide">File Column</th>
                          <th className="text-left py-2.5 px-5 text-xs font-semibold text-slate-500 uppercase tracking-wide">Maps To</th>
                        </tr>
                      </thead>
                      <tbody>
                        {parseResult.file_columns.map((col, i) => (
                          <tr key={col} className={cn("border-t border-slate-50", i % 2 === 0 ? "" : "bg-slate-50/40")}>
                            <td className="py-2.5 px-5">
                              <span className="font-mono text-xs text-slate-700 bg-slate-100 px-2 py-1 rounded">{col}</span>
                            </td>
                            <td className="py-2 px-5">
                              <Select
                                value={colMapping[col] || '__none__'}
                                onValueChange={v => setColMapping(prev => {
                                  const next = { ...prev };
                                  if (v === '__none__') delete next[col]; else next[col] = v;
                                  return next;
                                })}
                              >
                                <SelectTrigger className="h-8 text-xs rounded-lg">
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

                  {parseResult.sample_rows.length > 0 && (
                    <details className="border-t border-slate-100">
                      <summary className="px-5 py-3 cursor-pointer text-xs font-medium text-indigo-600 hover:bg-indigo-50 transition-colors select-none flex items-center gap-1.5">
                        <Table2 className="w-3.5 h-3.5" />
                        Preview first {Math.min(3, parseResult.sample_rows.length)} rows
                      </summary>
                      <div className="overflow-x-auto border-t border-slate-100">
                        <table className="text-xs min-w-full">
                          <thead className="bg-slate-50">
                            <tr>
                              {parseResult.file_columns.map(c => (
                                <th key={c} className="py-2 px-4 text-left font-medium text-slate-500 whitespace-nowrap">{c}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {parseResult.sample_rows.slice(0, 3).map((row, i) => (
                              <tr key={i} className="border-t border-slate-50">
                                {parseResult.file_columns.map(c => (
                                  <td key={c} className="py-2 px-4 text-slate-600 whitespace-nowrap max-w-[180px] truncate" title={String(row[c] ?? '')}>
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
                </div>
              </div>

              <div className="flex gap-3">
                <Button variant="outline" onClick={goBackToUpload} className="gap-2 rounded-xl">
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>
                <Button onClick={handleValidate} disabled={!entityType || validating} className="gap-2 flex-1 rounded-xl h-11">
                  {validating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                  {validating ? 'Validating rows…' : `Validate ${parseResult.total_rows.toLocaleString()} Rows`}
                </Button>
              </div>
            </div>
          )}

          {/* ── Step 3: Row Preview ──────────────────────────────────────────── */}
          {step === 'preview' && validateResult && summary && (
            <div className="space-y-4">

              {/* Sync freshness banner */}
              {syncFreshness !== null && (
                <div className={cn(
                  "flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl text-xs border",
                  syncFreshness.connector_online
                    ? "bg-slate-50 border-slate-200 text-slate-600"
                    : "bg-amber-50 border-amber-200 text-amber-700",
                )}>
                  <span className="flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 shrink-0" />
                    {syncFreshness.last_sync_at
                      ? <>Data synced <b>{relTime(syncFreshness.last_sync_at)}</b> — duplicate and reference checks use this snapshot</>
                      : 'No Tally sync yet — reference and duplicate checks may be incomplete'}
                  </span>
                  {syncFreshness.connector_online && (
                    <button onClick={syncNow}
                      className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium">
                      <RefreshCw className="w-3 h-3" /> Sync now
                    </button>
                  )}
                </div>
              )}

              {/* Summary + filter bar */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                {/* Counts */}
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
                    <span className="text-sm font-bold text-emerald-700">{summary.valid} new</span>
                  </div>
                  {summary.warnings > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                      <span className="text-sm font-bold text-amber-700">{summary.warnings} flagged</span>
                    </div>
                  )}
                  {summary.errors > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
                      <span className="text-sm font-bold text-red-700">{summary.errors} blocked</span>
                    </div>
                  )}
                  <span className="text-sm text-slate-400">of {summary.total} total</span>
                </div>

                {/* Filter chips */}
                <div className="flex flex-wrap gap-1.5 sm:ml-auto">
                  {FILTER_TABS.map(({ id, label }) => {
                    const count = id === 'all'
                      ? validateResult.rows.length
                      : validateResult.rows.filter(r => r.status === id || (id === 'new' && r.status === 'valid')).length;
                    if (count === 0 && id !== 'all') return null;
                    return (
                      <button
                        key={id}
                        onClick={() => setRowFilter(id)}
                        className={cn(
                          "px-3 py-1 rounded-full text-xs font-medium transition-all ring-1",
                          rowFilter === id
                            ? "bg-indigo-600 text-white ring-indigo-600"
                            : "bg-white text-slate-600 ring-slate-200 hover:ring-indigo-300 hover:text-indigo-700",
                        )}
                      >
                        {label} {id !== 'all' && <span className="opacity-70">({count})</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Bulk-action bar */}
              <div className="flex items-center gap-4 text-xs bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5">
                <span className="font-semibold text-slate-700">{selectedIds.size} selected</span>
                <div className="w-px h-3.5 bg-slate-300" />
                <button onClick={() => {
                  const valid = validateResult.rows.filter(r => r.status !== 'error').map(r => r.row_id);
                  setSelectedIds(new Set(valid));
                }} className="text-indigo-600 hover:text-indigo-800 font-medium transition-colors">Select all importable</button>
                <button onClick={() => {
                  const warn = validateResult.rows.filter(r => r.status === 'warning').map(r => r.row_id);
                  setSelectedIds(prev => { const n = new Set(prev); warn.forEach(id => n.delete(id)); return n; });
                }} className="text-amber-600 hover:text-amber-800 font-medium transition-colors">Deselect warnings</button>
                <button onClick={() => setSelectedIds(new Set())} className="text-slate-400 hover:text-slate-700 font-medium transition-colors">Clear all</button>
              </div>

              {/* Table */}
              <div className="rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <div className="max-h-[520px] overflow-y-auto">
                    <table className="w-full text-sm min-w-[900px]">
                      <thead className="bg-slate-50 sticky top-0 z-10 shadow-[0_1px_0_0_#e2e8f0]">
                        <tr>
                          <th className="py-3 px-4 w-10">
                            <button onClick={toggleAll} className="text-slate-400 hover:text-indigo-600 transition-colors">
                              {filteredRows.length > 0 && filteredRows.every(r => selectedIds.has(r.row_id))
                                ? <CheckSquare className="w-4 h-4 text-indigo-600" />
                                : <Square className="w-4 h-4" />}
                            </button>
                          </th>
                          <th className="py-3 px-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-28">Status</th>
                          <th className="py-3 px-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-12">#</th>
                          {Object.keys(filteredRows[0]?.mapped ?? {}).map(f => (
                            <th key={f} className="py-3 px-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap min-w-[120px]">
                              {friendlyCol(f)}
                            </th>
                          ))}
                          <th className="py-3 px-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide w-10" />
                          <th className="py-3 px-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide min-w-[260px]">Issues / Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {filteredRows.map(row => {
                          const cfg       = ROW_STATUS[row.status] ?? ROW_STATUS.new;
                          const isBlocked = row.status === 'error';
                          const isDupEx   = row.status === 'duplicate_exact';
                          const isSel     = selectedIds.has(row.row_id);
                          const isEditing = editingRowId === row.row_id;

                          return (
                            <tr key={row.row_id}
                              className={cn(
                                "align-top transition-colors group",
                                isEditing ? "bg-amber-50/60 ring-1 ring-inset ring-amber-200" :
                                isSel ? "bg-indigo-50/50" : "hover:bg-slate-50/70",
                                isBlocked && !isEditing && "opacity-75",
                              )}
                            >
                              {/* Checkbox */}
                              <td className="py-3 px-4 pt-3.5">
                                <button onClick={() => !isBlocked && !isEditing && toggleRow(row.row_id)} disabled={isBlocked || isEditing}>
                                  {isSel
                                    ? <CheckSquare className="w-4 h-4 text-indigo-600" />
                                    : <Square className={cn("w-4 h-4", isBlocked ? "text-slate-200" : "text-slate-300 group-hover:text-slate-500")} />}
                                </button>
                              </td>

                              {/* Status */}
                              <td className="py-3 px-3 pt-3.5">
                                <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ring-1", cfg.badge)}>
                                  <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />
                                  {cfg.label}
                                </span>
                              </td>

                              {/* Row # */}
                              <td className="py-3 px-3 pt-3.5 text-slate-400 font-mono text-xs">{row.row_id + 2}</td>

                              {/* Mapped values — editable when in edit mode */}
                              {Object.entries(row.mapped).map(([key, val]) => (
                                <td key={key} className="py-2 px-3 text-slate-700 text-sm">
                                  {isEditing ? (
                                    <input
                                      value={editDraft[key] ?? ''}
                                      onChange={e => setEditDraft(prev => ({ ...prev, [key]: e.target.value }))}
                                      className="w-full min-w-[100px] max-w-[180px] px-2 py-1 text-xs border border-amber-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
                                      placeholder={key}
                                    />
                                  ) : (
                                    <span className="block whitespace-nowrap overflow-hidden text-ellipsis max-w-[180px]" title={String(val ?? '')}>
                                      {String(val ?? '') || <span className="text-slate-300 italic text-xs">—</span>}
                                    </span>
                                  )}
                                </td>
                              ))}

                              {/* Edit button */}
                              <td className="py-3 px-2 pt-3.5">
                                {isEditing ? (
                                  <div className="flex gap-1">
                                    <button
                                      onClick={() => saveEdit(row.row_id)}
                                      disabled={savingEdit}
                                      className="p-1.5 rounded-lg bg-emerald-100 text-emerald-700 hover:bg-emerald-200 transition-colors"
                                      title="Save changes"
                                    >
                                      {savingEdit ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                                    </button>
                                    <button
                                      onClick={cancelEdit}
                                      className="p-1.5 rounded-lg bg-slate-100 text-slate-500 hover:bg-slate-200 transition-colors"
                                      title="Cancel"
                                    >
                                      <X className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                ) : (
                                  <button
                                    onClick={() => startEdit(row)}
                                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 transition-colors whitespace-nowrap"
                                    title="Edit row values"
                                  >
                                    <Pencil className="w-3 h-3" /> Edit
                                  </button>
                                )}
                              </td>

                              {/* Issues + Actions */}
                              <td className="py-3 px-3 pt-3 space-y-1.5">
                                {/* Errors */}
                                {row.errors.map((e, i) => (
                                  <div key={i} className="flex items-start gap-1.5 text-xs text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
                                    <XCircle className="w-3.5 h-3.5 mt-px shrink-0" />
                                    <span className="font-medium">{e.field}:</span> <span>{e.message}</span>
                                  </div>
                                ))}

                                {/* Warnings */}
                                {row.warnings.map((w, i) => (
                                  <div key={i} className="flex items-start gap-1.5 text-xs text-amber-700 bg-amber-50 rounded-lg px-2.5 py-1.5">
                                    <AlertCircle className="w-3.5 h-3.5 mt-px shrink-0" />
                                    <span>{w.message}</span>
                                  </div>
                                ))}

                                {/* Duplicate info */}
                                {row.duplicate_info && (
                                  <div className={cn(
                                    "rounded-lg px-2.5 py-1.5 text-xs space-y-1",
                                    isDupEx ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700",
                                  )}>
                                    <div className="flex items-center gap-1.5">
                                      <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                                      {isDupEx
                                        ? <span>Exact match: <b>"{row.duplicate_info.matched_name}"</b></span>
                                        : <span>Similar to: <b>"{row.duplicate_info.matched_name}"</b> ({Math.round(row.duplicate_info.similarity * 100)}%)</span>}
                                    </div>
                                    <div className="flex gap-1.5">
                                      {isDupEx && (
                                        <button onClick={() => applyRowAction(row.row_id, 'force_import')}
                                          className="px-2.5 py-1 bg-orange-100 text-orange-700 hover:bg-orange-200 rounded-md text-xs font-medium transition-colors">
                                          Force import
                                        </button>
                                      )}
                                      {!isDupEx && row.duplicate_info.match_type === 'fuzzy' && (
                                        <button onClick={() => applyRowAction(row.row_id, 'dismiss_dup')}
                                          className="px-2.5 py-1 bg-white text-slate-600 hover:bg-slate-100 border border-slate-200 rounded-md text-xs transition-colors">
                                          Confirm as new
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {/* Reference issues */}
                                {row.ref_issues.map((ri, i) => (
                                  <div key={i} className={cn(
                                    "rounded-lg px-2.5 py-1.5 text-xs space-y-1.5",
                                    ri.match_type === 'missing' ? "bg-orange-50 text-orange-700" : "bg-sky-50 text-sky-700",
                                  )}>
                                    <div className="flex items-center gap-1.5">
                                      <Info className="w-3.5 h-3.5 shrink-0" />
                                      {ri.match_type === 'missing'
                                        ? <span><b>{ri.ref_entity_type}</b> "{ri.ref_name}" not found</span>
                                        : ri.match_type === 'intra_file'
                                        ? <span className="text-slate-500">{ri.ref_entity_type} "{ri.ref_name}" (in this file)</span>
                                        : <span><b>{ri.ref_entity_type}</b> "{ri.ref_name}" — suggestions:</span>}
                                    </div>
                                    {ri.match_type === 'missing' && (
                                      <button onClick={() => createReference(row.row_id, ri.ref_entity_type, ri.ref_name, ri.field)}
                                        className="flex items-center gap-1 px-2.5 py-1 bg-indigo-100 text-indigo-700 hover:bg-indigo-200 rounded-md text-xs font-medium transition-colors whitespace-nowrap">
                                        + Create {ri.ref_entity_type}
                                      </button>
                                    )}
                                    {ri.match_type === 'similar' && (
                                      <div className="flex flex-wrap gap-1">
                                        {ri.suggestions.slice(0, 2).map((s, si) => (
                                          <button key={si} onClick={() => applyRowAction(row.row_id, 'use_existing', ri.field, s.name)}
                                            className="px-2.5 py-1 bg-white text-sky-700 hover:bg-sky-100 border border-sky-200 rounded-md text-xs transition-colors whitespace-nowrap">
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
                      <div className="py-16 text-center text-slate-400 text-sm">
                        No rows match this filter
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Footer actions */}
              <div className="flex gap-3 pt-1 border-t border-slate-100">
                <Button variant="outline" onClick={goBackToMapping} className="gap-2 rounded-xl">
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>
                <Button
                  onClick={handleCommit}
                  disabled={selectedIds.size === 0 || committing}
                  className="gap-2 rounded-xl flex-1"
                >
                  {committing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {committing ? 'Importing…' : `Import ${selectedIds.size} Row${selectedIds.size !== 1 ? 's' : ''}`}
                </Button>
              </div>
            </div>
          )}

          {/* ── Step 4: Progress / Done ──────────────────────────────────────── */}
          {(step === 'progress' || step === 'done') && (
            <div className="max-w-2xl mx-auto space-y-6 py-8">
              {/* Status header */}
              <div className="text-center space-y-3">
                <div className={cn(
                  "w-20 h-20 rounded-full flex items-center justify-center mx-auto shadow-lg",
                  step === 'done' ? "bg-emerald-100" : "bg-indigo-100",
                )}>
                  {step === 'done'
                    ? <CheckCircle className="w-10 h-10 text-emerald-600" />
                    : <RefreshCw className="w-10 h-10 text-indigo-600 animate-spin" />}
                </div>
                <div>
                  <h3 className="text-xl font-bold text-slate-900">
                    {step === 'done' ? 'Import Complete!' : 'Importing…'}
                  </h3>
                  <p className="text-sm text-slate-500 mt-1">
                    {step === 'done' ? 'Your data has been successfully imported' : 'Please wait while we process your rows'}
                  </p>
                </div>
              </div>

              {/* Progress bar */}
              {statusData && (
                <>
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-slate-500">
                      <span>Progress</span>
                      <span>{statusData.imported_rows} / {Math.min(statusData.total_rows, selectedIds.size)} rows</span>
                    </div>
                    <Progress
                      value={statusData.total_rows > 0
                        ? Math.round((statusData.imported_rows / Math.min(statusData.total_rows, selectedIds.size)) * 100)
                        : 0}
                      className="h-2.5 rounded-full"
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    {[
                      { label: 'Imported', value: statusData.imported_rows, cls: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-100' },
                      { label: 'Selected', value: Math.min(statusData.total_rows, selectedIds.size), cls: 'text-slate-700', bg: 'bg-slate-50 border-slate-100' },
                      { label: 'Tally Jobs', value: statusData.tally_queued, cls: 'text-indigo-600', bg: 'bg-indigo-50 border-indigo-100' },
                    ].map(s => (
                      <div key={s.label} className={cn("rounded-2xl border p-5 text-center", s.bg)}>
                        <p className={cn("text-3xl font-bold", s.cls)}>{s.value}</p>
                        <p className="text-xs text-slate-500 mt-1.5">{s.label}</p>
                      </div>
                    ))}
                  </div>

                  {statusData.commit_summary?.errors && Array.isArray(statusData.commit_summary.errors) &&
                    statusData.commit_summary.errors.length > 0 && (
                    <div className="rounded-xl border border-red-100 overflow-hidden">
                      <div className="bg-red-50 px-4 py-3 text-xs font-semibold text-red-700 flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {statusData.commit_summary.errors.length} commit error{statusData.commit_summary.errors.length > 1 ? 's' : ''}
                      </div>
                      {(statusData.commit_summary.errors as Array<{row_id: number; message: string}>).slice(0, 5).map((e, i) => (
                        <div key={i} className="px-4 py-2.5 text-xs border-t border-red-50 text-red-600 flex gap-3">
                          <span className="text-slate-400 font-mono shrink-0">Row {(e.row_id ?? 0) + 2}</span>
                          <span>{e.message}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {step === 'done' && (
                <div className="flex gap-3">
                  <Button variant="outline" onClick={() => setTab('history')} className="flex-1 gap-2 rounded-xl">
                    <History className="w-4 h-4" /> View History
                  </Button>
                  <Button onClick={() => resetWizard(true)} className="flex-1 gap-2 rounded-xl">
                    <Upload className="w-4 h-4" /> Import Another File
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── History Tab ──────────────────────────────────────────────────────── */}
      {tab === 'history' && (
        <div className="flex-1 pt-6">
          <div className="rounded-2xl border border-slate-200 overflow-hidden shadow-sm bg-white">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
              <div className="flex items-center gap-2.5">
                <History className="w-5 h-5 text-indigo-600" />
                <div>
                  <p className="text-sm font-semibold text-slate-800">Upload History</p>
                  <p className="text-xs text-slate-500">{historyTotal} total imports</p>
                </div>
              </div>
            </div>

            {historyLoading ? (
              <div className="p-6 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
              </div>
            ) : !history?.length ? (
              <div className="py-24 text-center space-y-4">
                <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto">
                  <Upload className="w-8 h-8 text-slate-300" />
                </div>
                <div>
                  <p className="text-slate-700 font-semibold">No imports yet</p>
                  <p className="text-sm text-slate-400 mt-1">Start by importing a CSV, XLSX, or JSON file</p>
                </div>
                <Button size="sm" onClick={() => setTab('import')} className="gap-2 rounded-xl">
                  <Upload className="w-4 h-4" /> Start Importing
                </Button>
              </div>
            ) : (
              <div>
                <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto] gap-4 px-5 py-2.5 bg-slate-50 border-b border-slate-100 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  <div />
                  <div>File</div>
                  <div className="hidden sm:block">Progress</div>
                  <div className="hidden md:block">Rows</div>
                  <div>Status</div>
                  <div />
                </div>
                {history.map(u => (
                  <HistoryRow
                    key={u.id}
                    u={u}
                    onDelete={() => qc.invalidateQueries({ queryKey: ['upload-history'] })}
                    isSelected={historySelectedIds.has(u.id)}
                    onToggleSelect={toggleHistorySelect}
                  />
                ))}
              </div>
            )}
            {/* Pagination */}
            {historyPages > 1 && (
              <div className="flex items-center justify-between px-6 py-3 border-t border-slate-100 bg-slate-50">
                <p className="text-xs text-slate-500">
                  Page {historyPage} of {historyPages} · {historyTotal} imports
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setHistoryPage(p => Math.max(1, p - 1))}
                    disabled={historyPage === 1}
                    className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-200 disabled:opacity-40 transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  {Array.from({ length: historyPages }, (_, i) => i + 1).map(p => (
                    <button
                      key={p}
                      onClick={() => setHistoryPage(p)}
                      className={cn(
                        "w-7 h-7 rounded-lg text-xs font-medium transition-colors",
                        p === historyPage ? "bg-indigo-600 text-white" : "text-slate-600 hover:bg-slate-200",
                      )}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    onClick={() => setHistoryPage(p => Math.min(historyPages, p + 1))}
                    disabled={historyPage === historyPages}
                    className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-200 disabled:opacity-40 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <BulkDeleteBar
        selectedIds={historySelectedIds}
        entityLabel="import history entry"
        queryKeys={[['upload-history']]}
        onClear={clearHistorySelection}
        onDelete={ids => bulkDeleteApi.uploads(ids)}
      />
    </div>
  );
}
