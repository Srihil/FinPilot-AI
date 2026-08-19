import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity, X, Clock, CheckCircle2, XCircle, RotateCcw,
  Loader2, AlertCircle, Package,
} from 'lucide-react';
import { tallyApi, type TallyJobItem } from '../../api/endpoints';
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
  const entity = OP_ENTITY[item.operation] ?? 'Record';
  const total   = (item as any).total   ?? 0;
  const success = (item as any).success ?? 0;
  const failed  = (item as any).failed  ?? 0;
  const active  = (item as any).active  ?? 0;
  const pending = total - success - failed;

  const overallStatus = failed > 0 && active === 0 ? 'PARTIAL'
    : active > 0 ? 'RUNNING'
    : 'SUCCESS';

  return (
    <div className={`rounded-xl border p-3.5 space-y-2.5 transition-all ${
      overallStatus === 'PARTIAL' ? 'border-amber-200 bg-amber-50/40' :
      overallStatus === 'RUNNING' ? 'border-indigo-200 bg-indigo-50/40' :
      'border-emerald-200 bg-emerald-50/40'
    }`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Package className="w-4 h-4 text-indigo-500 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800">Bulk Import</p>
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
            : <><CheckCircle2 className="w-3 h-3" /> Done</>
          }
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        {success > 0 && <span className="text-emerald-700 font-medium">{success} synced</span>}
        {pending > 0 && <span className="text-blue-600 font-medium">{pending} pending</span>}
        {failed  > 0 && <span className="text-red-600 font-medium">{failed} failed</span>}
      </div>
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

// ─── Drawer ───────────────────────────────────────────────────────────────────

export function TallyActivityDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['tally-activity', 30],
    queryFn: () => tallyApi.activity(30),
    refetchInterval: open ? 5000 : false,
    staleTime: 3000,
  });

  const retryMut = useMutation({
    mutationFn: (jobId: string) => tallyApi.retryJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tally-activity'] }),
  });

  const jobs = data?.items ?? [];
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

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
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
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <div className="w-14 h-14 rounded-full bg-indigo-50 flex items-center justify-center">
                <Activity className="w-7 h-7 text-indigo-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-700">No activity yet</p>
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

        {/* Footer */}
        <div className="px-5 py-3 border-t bg-slate-50 shrink-0">
          <p className="text-[11px] text-slate-400 text-center">
            Auto-refreshes every 5s while open
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
