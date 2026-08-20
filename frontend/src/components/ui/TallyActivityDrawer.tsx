import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity, X, Clock, CheckCircle2, XCircle, RotateCcw,
  Loader2, AlertCircle, Package, Trash2, ChevronDown, ChevronUp,
  Download, FileBarChart,
} from 'lucide-react';
import { tallyApi, activityApi, type TallyJobItem, type ExportActivity } from '../../api/endpoints';
import { Skeleton } from './skeleton';

// ─── Smart job label ─────────────────────────────────────────────────────────

const OP_ENTITY: Record<string, string> = {
  CREATE_LEDGER:           'Ledger',
  CREATE_GROUP:            'Account Group',
  CREATE_STOCK_ITEM:       'Stock Item',
  CREATE_STOCK_GROUP:      'Stock Group',
  CREATE_UNIT:             'Unit',
  CREATE_GODOWN:           'Godown',
  CREATE_STOCK_CATEGORY:   'Stock Category',
  CREATE_VOUCHER_TYPE:     'Voucher Type',
  CREATE_SALES_VOUCHER:    'Sales Voucher',
  CREATE_PURCHASE_VOUCHER: 'Purchase Voucher',
  CREATE_RECEIPT_VOUCHER:  'Receipt',
  CREATE_PAYMENT_VOUCHER:  'Payment',
  CREATE_JOURNAL_VOUCHER:  'Journal Entry',
  CREATE_CREDIT_NOTE:      'Credit Note',
  CREATE_DEBIT_NOTE:       'Debit Note',
  CREATE_CONTRA_VOUCHER:   'Contra (Bank/Cash Transfer)',
  CREATE_STOCK_JOURNAL:    'Stock Journal',
  CREATE_PHYSICAL_STOCK:   'Physical Stock',
  CREATE_DELIVERY_NOTE:    'Delivery Note',
  CREATE_RECEIPT_NOTE:     'Receipt Note',
  CREATE_REJECTION_IN:     'Rejection In',
  CREATE_REJECTION_OUT:    'Rejection Out',
  DELETE_LEDGER:           'Ledger',
  DELETE_STOCK_ITEM:       'Stock Item',
  DELETE_STOCK_GROUP:      'Stock Group',
  DELETE_UNIT:             'Unit',
  DELETE_GODOWN:           'Godown',
  DELETE_STOCK_CATEGORY:   'Stock Category',
  DELETE_VOUCHER_TYPE:     'Voucher Type',
  DELETE_VOUCHER:          'Voucher',
  CANCEL_VOUCHER:          'Voucher',
  READ_COMPANIES:          'Companies',
  READ_LEDGERS:            'Ledgers',
  READ_VOUCHERS:           'Vouchers',
  READ_SALES:              'Sales',
  READ_PURCHASES:          'Purchases',
  READ_RECEIVABLES:        'Receivables',
  READ_PAYABLES:           'Payables',
  READ_STOCK_ITEMS:        'Stock Items',
  SYNC_FULL:               'Full Sync',
  SYNC_PARTIAL:            'Partial Sync',
};

function fmtJob(job: TallyJobItem): { verb: string; entity: string; name: string; verbColor: string; badgeCls: string } {
  const op       = job.operation;
  const p        = job.payload ?? {};
  const isUpdate = !!(p.is_update);
  const isDelete = op.startsWith('DELETE_') || op === 'CANCEL_VOUCHER';
  const isRead   = op.startsWith('READ_') || op.startsWith('SYNC_');

  const verb = isRead ? 'Sync' : isDelete ? 'Delete' : isUpdate ? 'Update' : 'Create';

  const verbColor = isDelete ? 'text-red-600'
                  : isUpdate ? 'text-indigo-600'
                  : isRead   ? 'text-slate-500'
                  : 'text-emerald-700';

  const badgeCls = isDelete ? 'bg-red-50 border-red-200'
                 : isUpdate ? 'bg-indigo-50 border-indigo-200'
                 : isRead   ? 'bg-slate-50 border-slate-200'
                 : 'bg-emerald-50 border-emerald-200';

  const entity = OP_ENTITY[op] ?? op.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());

  const name = (
    (p.name as string) ||
    (p.narration as string) ||
    (p.voucher_number as string) ||
    (p.transaction_number as string) ||
    ''
  );

  return { verb, entity, name, verbColor, badgeCls };
}

// ─── Error interpreter ───────────────────────────────────────────────────────

function interpretError(error: string | null | undefined): string {
  if (!error) return '';
  const e = error.toLowerCase();
  if (e.includes('voucher date is missing') || (e.includes('date') && e.includes('missing')))
    return 'Date rejected — use the Current Date shown in TallyPrime\'s Gateway, not your PC\'s date.';
  if (e.includes('bad unit name'))
    return 'Unit symbol must be short with no spaces (e.g. "Nos", "Kgs"). Create it in TallyPrime first.';
  if (e.includes('already exists') || e.includes('duplicate'))
    return 'Already exists in TallyPrime — no action needed.';
  if (e.includes('no company') || e.includes('company not open'))
    return 'No company is open in TallyPrime. Open your company and retry.';
  if (e.includes('does not exist'))
    return 'Referenced master not found in TallyPrime — create it there first, then retry.';
  return error.replace(/^TallyPrime error:\s*/i, '').trim();
}

// ─── Time helper ─────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ─── Status badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; label: string; Icon: typeof Clock; spin?: boolean }> = {
    PENDING:  { cls: 'bg-amber-100 text-amber-800',     label: 'Pending',    Icon: Clock },
    CLAIMED:  { cls: 'bg-blue-100 text-blue-800',       label: 'Processing', Icon: Loader2, spin: true },
    RUNNING:  { cls: 'bg-blue-100 text-blue-800',       label: 'Running',    Icon: Loader2, spin: true },
    RETRYING: { cls: 'bg-orange-100 text-orange-800',   label: 'Retrying',   Icon: RotateCcw },
    SUCCESS:  { cls: 'bg-emerald-100 text-emerald-800', label: 'Success',    Icon: CheckCircle2 },
    FAILED:   { cls: 'bg-red-100 text-red-800',         label: 'Failed',     Icon: XCircle },
    CANCELLED:{ cls: 'bg-slate-100 text-slate-600',     label: 'Cancelled',  Icon: X },
  };
  const c = cfg[status] ?? { cls: 'bg-slate-100 text-slate-700', label: status, Icon: Clock };
  const Icon = c.Icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${c.cls}`}>
      <Icon className={`w-3 h-3 ${c.spin ? 'animate-spin' : ''}`} />
      {c.label}
    </span>
  );
}

// ─── Batch summary card ───────────────────────────────────────────────────────

function BatchJobCard({ item }: { item: TallyJobItem }) {
  const [showFailed, setShowFailed] = useState(false);

  const b         = item as any;
  const entity    = OP_ENTITY[item.operation] ?? 'Record';
  const total     = b.total   ?? 0;
  const success   = b.success ?? 0;
  const failed    = b.failed  ?? 0;
  const active    = b.active  ?? 0;
  const pending   = total - success - failed;
  const isDelete  = b.batch_type === 'bulk_delete';
  const failedJobs: Array<{ name: string; error: string }> = b.failed_jobs ?? [];

  const overallStatus = failed > 0 && active === 0 ? 'PARTIAL'
    : active > 0 ? 'RUNNING'
    : 'SUCCESS';

  const borderCls = overallStatus === 'PARTIAL' ? 'border-amber-200 bg-amber-50/40'
    : overallStatus === 'RUNNING' ? 'border-indigo-200 bg-indigo-50/40'
    : 'border-emerald-200 bg-emerald-50/40';

  const Icon = isDelete ? Trash2 : Package;
  const iconCls = isDelete ? 'text-red-500' : 'text-indigo-500';
  const label = isDelete ? 'Bulk Delete' : 'Bulk Import';
  const actionWord = isDelete ? 'deleted' : 'synced';

  return (
    <div className={`rounded-xl border p-3.5 space-y-2.5 transition-all ${borderCls}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className={`w-4 h-4 shrink-0 ${iconCls}`} />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800">{label}</p>
            <p className="text-xs text-slate-500 mt-0.5">{total} {entity}{total !== 1 ? 's' : ''}</p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold shrink-0 ${
          overallStatus === 'RUNNING' ? 'bg-blue-100 text-blue-800' :
          overallStatus === 'PARTIAL' ? 'bg-amber-100 text-amber-800' :
          'bg-emerald-100 text-emerald-800'
        }`}>
          {overallStatus === 'RUNNING'
            ? <><Loader2 className="w-3 h-3 animate-spin" /> In progress</>
            : overallStatus === 'PARTIAL'
            ? <><AlertCircle className="w-3 h-3" /> Partial</>
            : <><CheckCircle2 className="w-3 h-3" /> Done</>}
        </span>
      </div>

      {/* Counts */}
      <div className="flex items-center gap-3 text-xs">
        {success > 0 && <span className="text-emerald-700 font-medium">{success} {actionWord}</span>}
        {pending > 0 && <span className="text-blue-600 font-medium">{pending} pending</span>}
        {failed  > 0 && <span className="text-red-600 font-medium">{failed} failed</span>}
      </div>

      {/* Expandable failures */}
      {failed > 0 && failedJobs.length > 0 && (
        <div>
          <button
            onClick={() => setShowFailed(v => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-red-600 hover:text-red-800 transition-colors"
          >
            {showFailed ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showFailed ? 'Hide failed entries' : `Show ${failed} failed entr${failed === 1 ? 'y' : 'ies'}`}
          </button>
          {showFailed && (
            <div className="mt-2 rounded-lg border border-red-100 overflow-hidden">
              <div className="bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700">
                TallyPrime rejected these — not deleted
              </div>
              <div className="divide-y divide-red-50 max-h-44 overflow-y-auto">
                {failedJobs.map((fj, i) => (
                  <div key={i} className="px-3 py-2 text-xs">
                    {fj.name && (
                      <p className="font-medium text-slate-700 truncate" title={fj.name}>{fj.name}</p>
                    )}
                    {fj.error && (
                      <p className="text-red-600 mt-0.5 leading-relaxed">{interpretError(fj.error)}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Timestamp */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400">
        <Clock className="w-3 h-3 shrink-0" />
        <span>{timeAgo(item.created_at)}</span>
      </div>
    </div>
  );
}

// ─── Job card ─────────────────────────────────────────────────────────────────

function JobCard({ job, onRetry }: { job: TallyJobItem; onRetry: (id: string) => void }) {
  const { verb, entity, name, verbColor, badgeCls } = fmtJob(job);
  const smart   = interpretError(job.error_message);
  const isActive = ['PENDING', 'CLAIMED', 'RUNNING', 'RETRYING'].includes(job.status);

  return (
    <div className={`rounded-xl border p-3.5 space-y-2.5 transition-all ${
      job.status === 'FAILED'   ? 'border-red-200 bg-red-50/60' :
      job.status === 'SUCCESS'  ? `border-emerald-200 bg-emerald-50/40` :
      isActive                  ? `${badgeCls} bg-opacity-60` :
      'border-slate-200 bg-white'
    }`}>
      {/* Top row: label + status */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-800 leading-snug">
            <span className={verbColor}>{verb}</span>
            <span className="text-slate-600 font-normal"> {entity}</span>
          </p>
          {name && (
            <p className="text-xs text-slate-400 mt-0.5 truncate" title={name}>· {name}</p>
          )}
        </div>
        <StatusBadge status={job.status} />
      </div>

      {/* Time row */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400">
        <Clock className="w-3 h-3 shrink-0" />
        <span>{timeAgo(job.created_at)}</span>
        {job.retry_count > 0 && (
          <span className="ml-auto text-orange-600 font-medium">retry {job.retry_count}</span>
        )}
      </div>

      {/* Error message */}
      {job.status === 'FAILED' && smart && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-red-100 border border-red-200">
          <AlertCircle className="w-3.5 h-3.5 text-red-600 shrink-0 mt-0.5" />
          <p className="text-xs text-red-800 leading-relaxed">{smart}</p>
        </div>
      )}

      {/* Retry button */}
      {job.status === 'FAILED' && (
        <button
          onClick={() => onRetry(job.id)}
          className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-800
            bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5 transition-colors w-full justify-center"
        >
          <RotateCcw className="w-3 h-3" /> Retry Job
        </button>
      )}

      {/* Success line */}
      {job.status === 'SUCCESS' && (
        <p className="text-xs text-emerald-700 font-medium flex items-center gap-1">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Synced to TallyPrime successfully
        </p>
      )}
    </div>
  );
}

// ─── Export event card ────────────────────────────────────────────────────────

const ENTITY_LABEL: Record<string, string> = {
  ledger_export:            'Ledgers',
  group_export:             'Account Groups',
  stock_group_export:       'Stock Groups',
  stock_item_export:        'Stock Items',
  stock_category_export:    'Stock Categories',
  voucher_export:           'Vouchers',
  stock_transaction_export: 'Stock Transactions',
  report:                   'Report',
};

function ExportEventCard({ event }: { event: ExportActivity }) {
  const isReport = event.action === 'GENERATE_REPORT';
  const label = isReport ? 'Report Generated' : `Export — ${ENTITY_LABEL[event.entity_type] ?? event.entity_type}`;
  const Icon = isReport ? FileBarChart : Download;
  const iconCls = isReport ? 'text-indigo-600 bg-indigo-50 border-indigo-100' : 'text-emerald-600 bg-emerald-50 border-emerald-100';

  // Extract format badge from description e.g. "...as XLSX (42 rows)..."
  const fmtMatch = event.description.match(/as\s+(CSV|XLSX|JSON|PDF)/i);
  const rowMatch = event.description.match(/\((\d+)\s+rows?\)/i);
  const fmt = fmtMatch ? fmtMatch[1].toUpperCase() : null;
  const rows = rowMatch ? rowMatch[1] : null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-2">
      <div className="flex items-start gap-2.5">
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center border shrink-0 ${iconCls}`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800 leading-snug">{label}</p>
          <p className="text-xs text-slate-400 mt-0.5 truncate leading-snug" title={event.description}>
            {event.description.replace(/^Exported .* as \w+ \(\d+ rows?\) — /, '').replace(/^Generated /, '') || event.description}
          </p>
        </div>
        {fmt && (
          <span className="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
            {fmt}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-400 pl-9">
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" /> {timeAgo(event.created_at)}
        </span>
        {rows && <span>{rows} rows</span>}
        <span className="truncate">{event.user_name}</span>
      </div>
    </div>
  );
}


// ─── Drawer ───────────────────────────────────────────────────────────────────

export function TallyActivityDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [showExports, setShowExports] = useState(true);

  const { data, isLoading } = useQuery({
    queryKey: ['tally-activity', 30],
    queryFn: () => tallyApi.activity(30),
    refetchInterval: open ? 5000 : false,
    staleTime: 3000,
  });

  const { data: exportEvents, isLoading: exportsLoading } = useQuery({
    queryKey: ['recent-exports'],
    queryFn: () => activityApi.recentExports(15),
    refetchInterval: open ? 10000 : false,
    staleTime: 5000,
    enabled: open,
  });

  const retryMut = useMutation({
    mutationFn: (jobId: string) => tallyApi.retryJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tally-activity'] }),
  });

  const jobs = data?.items ?? [];
  const exports = exportEvents ?? [];
  const activeCount = jobs.filter(j => ['PENDING', 'CLAIMED', 'RUNNING', 'RETRYING'].includes(j.status)).length;

  return (
    <>
      {/* Backdrop with blur */}
      <div
        className={`fixed inset-0 bg-black/40 backdrop-blur-sm z-40 transition-opacity duration-300
          ${open ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-[420px] max-w-[95vw] bg-white shadow-2xl z-50
          flex flex-col transform transition-transform duration-300 ease-out
          ${open ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <Activity className="w-5 h-5" />
              {activeCount > 0 && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-amber-400 rounded-full animate-pulse border border-indigo-600" />
              )}
            </div>
            <div>
              <p className="font-semibold text-sm">Tally Sync Activity</p>
              <p className="text-indigo-200 text-xs">
                {activeCount > 0 ? `${activeCount} job${activeCount > 1 ? 's' : ''} in progress` : 'Latest jobs at the top'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/20 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tally jobs — capped height so exports section gets the rest */}
        <div className="max-h-56 overflow-y-auto shrink-0 p-4 space-y-3 border-b border-slate-100">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="rounded-xl border border-slate-200 p-3.5 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <Skeleton className="h-4 w-40" />
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-3 w-24" />
                </div>
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
              <div className="w-14 h-14 rounded-full bg-indigo-50 flex items-center justify-center">
                <Activity className="w-7 h-7 text-indigo-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-700">No Tally activity yet</p>
                <p className="text-xs text-slate-400 mt-1 max-w-[200px]">
                  Tally sync jobs will appear here as you create or update records
                </p>
              </div>
            </div>
          ) : (
            jobs.map(job =>
              (job as any).is_batch
                ? <BatchJobCard key={job.id} item={job} />
                : <JobCard key={job.id} job={job} onRetry={id => retryMut.mutate(id)} />
            )
          )}
        </div>

        {/* Recent Exports & Reports — flex-1: fills all remaining drawer height */}
        <div className="flex-1 flex flex-col min-h-0 border-t border-slate-200 bg-slate-50/60">
          {/* Toggle header */}
          <button
            type="button"
            onClick={() => setShowExports(v => !v)}
            className="w-full flex items-center justify-between px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hover:bg-slate-100 transition-colors"
          >
            <span className="flex items-center gap-2">
              <Download className="w-3.5 h-3.5 text-emerald-500" />
              Recent Exports &amp; Reports
              {exports.length > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">
                  {exports.length}
                </span>
              )}
            </span>
            {showExports ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {/* Card list — flex-1 so it fills all space below the header */}
          {showExports && (
            <div className="flex-1 overflow-y-auto px-4 pb-3 space-y-2">
              {exportsLoading ? (
                <div className="space-y-2 pt-1">
                  {[1, 2].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
                </div>
              ) : exports.length === 0 ? (
                <div className="text-center py-5 text-xs text-slate-400">
                  <Download className="w-5 h-5 mx-auto mb-1.5 text-slate-300" />
                  No exports yet — use the Export button on any data page
                </div>
              ) : (
                exports.map(e => <ExportEventCard key={e.id} event={e} />)
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-2.5 border-t bg-slate-50 shrink-0">
          <p className="text-[11px] text-slate-400 text-center">
            Tally sync refreshes every 5s · Exports refresh every 10s
          </p>
        </div>
      </div>
    </>
  );
}

// ─── Trigger button (used in TopBar) ─────────────────────────────────────────

export function ActivityTriggerButton({ onClick }: { onClick: () => void }) {
  const { data } = useQuery({
    queryKey: ['tally-activity', 10],
    queryFn: () => tallyApi.activity(10),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  const jobs = data?.items ?? [];
  const activeCount = jobs.filter(j => ['PENDING', 'CLAIMED', 'RUNNING', 'RETRYING'].includes(j.status)).length;

  return (
    <button
      onClick={onClick}
      title="Tally Sync Activity"
      className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-600
        hover:bg-slate-100 border border-slate-200 transition-colors"
    >
      <Activity className="w-4 h-4 text-indigo-600" />
      <span className="hidden sm:inline font-medium text-slate-700">Activity</span>
      {activeCount > 0 && (
        <span className="absolute -top-1 -right-1 w-3 h-3 bg-amber-400 rounded-full animate-pulse border-2 border-white" />
      )}
    </button>
  );
}
