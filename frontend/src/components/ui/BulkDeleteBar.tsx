import { useState, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Trash2, Loader2, CheckSquare } from 'lucide-react';
import { toast } from './use-toast';
import { cn } from '../../utils/cn';

export interface BulkDeleteResult {
  batch_id: string | null;
  deleted_immediately: number;
  errors: Array<{ id: string; name?: string; reason: string }>;
  has_connector: boolean;
  tally_queued?: number;
}

export interface BulkDeleteBarProps {
  selectedIds: Set<string>;
  entityLabel: string;          // singular, e.g. "ledger", "stock item"
  queryKeys: string[][];        // react-query keys to invalidate after delete
  onClear: () => void;
  onDelete: (ids: string[]) => Promise<BulkDeleteResult>;
}

type State = 'idle' | 'ready' | 'deleting';

export function BulkDeleteBar({
  selectedIds,
  entityLabel,
  queryKeys,
  onClear,
  onDelete,
}: BulkDeleteBarProps) {
  const qc = useQueryClient();
  const [barState, setBarState] = useState<State>('idle');

  // Sync idle ↔ ready with selection
  useEffect(() => {
    if (barState === 'idle' && selectedIds.size > 0) setBarState('ready');
    if (barState === 'ready' && selectedIds.size === 0) setBarState('idle');
  }, [selectedIds.size, barState]);

  const handleDelete = useCallback(async () => {
    if (barState !== 'ready') return;
    setBarState('deleting');
    try {
      const ids = [...selectedIds];
      const res = await onDelete(ids);

      // Invalidate immediately — pages refetch every 5s and items disappear
      // once TallyPrime confirms; or immediately for local-only deletes.
      queryKeys.forEach(k => qc.invalidateQueries({ queryKey: k }));
      onClear();
      setBarState('idle');

      const queued  = res.tally_queued   ?? 0;
      const deleted = res.deleted_immediately ?? 0;
      const errs    = res.errors ?? [];
      const plural  = (n: number) => `${n} ${entityLabel}${n !== 1 ? 's' : ''}`;

      if (queued > 0) {
        toast({
          title: `${plural(queued)} queued for deletion`,
          description: 'TallyPrime is processing — track live status in Sync Activity',
        });
      } else if (deleted > 0) {
        toast({
          title: `${plural(deleted)} deleted`,
        });
      }

      if (errs.length > 0) {
        const names = errs.map(e => e.name || e.id).filter(Boolean).join(', ');
        toast({
          title: `${errs.length} could not be deleted`,
          description: names || errs[0]?.reason,
          variant: 'destructive',
        });
      }
    } catch {
      setBarState('ready');
      toast({ title: 'Delete failed', description: 'An unexpected error occurred.', variant: 'destructive' });
    }
  }, [barState, selectedIds, onDelete, queryKeys, qc, onClear, entityLabel]);

  const count = selectedIds.size;
  const label = `${count} ${entityLabel}${count !== 1 ? 's' : ''}`;

  if (barState === 'idle') return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-xl px-4">
      <div className={cn(
        'rounded-2xl shadow-2xl border p-4 bg-white border-slate-200 transition-all',
        barState === 'deleting' && 'opacity-70 pointer-events-none',
      )}>
        <div className="flex items-center gap-3">
          {barState === 'deleting'
            ? <Loader2 className="w-4 h-4 animate-spin text-indigo-500 shrink-0" />
            : <CheckSquare className="w-4 h-4 text-indigo-600 shrink-0" />
          }
          <span className="text-sm font-semibold text-slate-700 flex-1">
            {barState === 'deleting' ? 'Sending to TallyPrime…' : `${label} selected`}
          </span>
          {barState === 'ready' && (
            <>
              <button
                onClick={() => { onClear(); setBarState('idle'); }}
                className="text-xs text-slate-500 hover:text-slate-800 px-2 py-1 rounded-lg hover:bg-slate-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-semibold hover:bg-red-700 active:scale-95 transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete {count}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
