import { cn } from '../../utils/cn';

type SyncStatus = string;

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  synced:         { label: 'Synced', cls: 'bg-emerald-100 text-emerald-700' },
  pending:        { label: 'Pending', cls: 'bg-amber-100 text-amber-700' },
  failed:         { label: 'Failed', cls: 'bg-red-100 text-red-700' },
  finpilot:       { label: 'FinPilot', cls: 'bg-indigo-100 text-indigo-700' },
  tally_sync:     { label: 'TallyPrime', cls: 'bg-teal-100 text-teal-700' },
  delete_pending: { label: 'Deleting…', cls: 'bg-orange-100 text-orange-700' },
  delete_failed:  { label: 'Del.Failed', cls: 'bg-red-100 text-red-700' },
  local_only:     { label: 'Local Only', cls: 'bg-slate-100 text-slate-600' },
};

export function SyncBadge({
  status,
  source,
  className,
}: {
  status: SyncStatus;
  source?: string;
  className?: string;
}) {
  const key = source === 'tally_sync' ? 'tally_sync' : status;
  const cfg = STATUS_CONFIG[key] ?? { label: status, cls: 'bg-slate-100 text-slate-600' };
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        cfg.cls,
        className,
      )}
    >
      {cfg.label}
    </span>
  );
}
