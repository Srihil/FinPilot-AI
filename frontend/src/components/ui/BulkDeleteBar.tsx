import { useState, useEffect, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2, Loader2, CheckCircle2, X, CheckSquare } from 'lucide-react';
import apiClient from '../../api/client';
import { toast } from './use-toast';
import { cn } from '../../utils/cn';

// ─── Types ────────────────────────────────────────────────────────────────────

interface BatchJob {
  job_id: string;
  entity_id: string;
  name: string;
  status: string;
  error: string;
}

export interface BatchResults {
  batch_id: string;
  total: number;
  pending: number;
  success: number;
  failed: number;
  is_complete: boolean;
  jobs: BatchJob[];
}

export interface BulkDeleteResult {
  batch_id: string | null;
  deleted_immediately: number;
  errors: Array<{ id: string; name?: string; reason: string }>;
  has_connector: boolean;
}

export interface BulkDeleteBarProps {
  selectedIds: Set<string>;
  entityLabel: string;          // singular, e.g. "ledger", "stock item"
  queryKeys: string[][];        // react-query keys to invalidate after delete
  onClear: () => void;
  onDelete: (ids: string[]) => Promise<BulkDeleteResult>;
}

type State = 'idle' | 'ready' | 'deleting' | 'done';

// ─── Component ────────────────────────────────────────────────────────────────

export function BulkDeleteBar({
  selectedIds,
  entityLabel,
  queryKeys,
  onClear,
  onDelete,
}: BulkDeleteBarProps) {
  const qc = useQueryClient();
  const [barState, setBarState] = useState<State>('idle');
  const [batchId, setBatchId]   = useState<string | null>(null);
  const [result, setResult]     = useState<BulkDeleteResult | null>(null);

  // Sync idle ↔ ready with selection
  useEffect(() => {
    if (barState === 'idle' && selectedIds.size > 0) setBarState('ready');
    if (barState === 'ready' && selectedIds.size === 0) setBarState('idle');
  }, [selectedIds.size, barState]);

  // Poll batch results while deleting
  const { data: batchData } = useQuery<BatchResults>({
    queryKey: ['bulk-delete-batch', batchId],
    queryFn:  () => apiClient.get(`/api/tally/batch/${batchId}/results`).then(r => r.data),
    enabled:  !!batchId && barState === 'deleting',
    refetchInterval: batchId && barState === 'deleting' ? 2000 : false,
    staleTime: 0,
  });

  // Transition to done when all pending jobs finish
  useEffect(() => {
    if (batchData?.is_complete && barState === 'deleting') {
      setBarState('done');
      queryKeys.forEach(k => qc.invalidateQueries({ queryKey: k }));
      onClear();
    }
  }, [batchData?.is_complete, barState]);

  const handleDelete = useCallback(async () => {
    if (barState !== 'ready') return;
    setBarState('deleting');
    try {
      const ids = [...selectedIds];
      const res = await onDelete(ids);
      setResult(res);
      if (res.batch_id) {
        setBatchId(res.batch_id);
        // polling via useQuery kicks in
      } else {
        // All deleted immediately — no connector or local-only
        setBarState('done');
        queryKeys.forEach(k => qc.invalidateQueries({ queryKey: k }));
        onClear();
      }
    } catch {
      setBarState('ready');
      toast({ title: 'Delete failed', description: 'An unexpected error occurred.', variant: 'destructive' });
    }
  }, [barState, selectedIds, onDelete, queryKeys, qc, onClear]);

  const handleDismiss = useCallback(() => {
    setBarState('idle');
    setBatchId(null);
    setResult(null);
  }, []);

  const count = selectedIds.size;
  const label = `${count} ${entityLabel}${count !== 1 ? 's' : ''}`;

  if (barState === 'idle') return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-xl px-4">
      <div className={cn(
        'rounded-2xl shadow-2xl border p-4 transition-all',
        barState === 'done'     ? 'bg-emerald-50 border-emerald-200' :
        barState === 'deleting'                      ? 'bg-indigo-50 border-indigo-200' :
        'bg-white border-slate-200',
      )}>

        {/* ── Ready ─────────────────────────────────────────────────────────── */}
        {barState === 'ready' && (
          <div className="flex items-center gap-3">
            <CheckSquare className="w-4 h-4 text-indigo-600 shrink-0" />
            <span className="text-sm font-semibold text-slate-700 flex-1">{label} selected</span>
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
          </div>
        )}

        {/* ── Deleting ──────────────────────────────────────────────────────── */}
        {barState === 'deleting' && (
          <div className="flex items-center gap-3">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-600 shrink-0" />
            <span className="text-sm font-semibold text-indigo-800 flex-1">
              Deleting from TallyPrime…
            </span>
            {batchData && (
              <span className="text-xs text-indigo-500 tabular-nums">
                {batchData.success + batchData.failed} / {batchData.total} done
              </span>
            )}
          </div>
        )}

        {/* ── Done ──────────────────────────────────────────────────────────── */}
        {barState === 'done' && (
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="text-sm font-semibold text-emerald-700 flex-1">
              {result?.batch_id
                ? 'Delete jobs queued — check Sync Activity drawer for live status'
                : `${result?.deleted_immediately ?? 0} deleted locally`}
            </span>
            <button
              onClick={handleDismiss}
              className="p-1 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
