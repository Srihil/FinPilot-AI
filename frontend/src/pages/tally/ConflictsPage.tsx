import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { toast } from '../../components/ui/use-toast';
import { useState } from 'react';
import { cn } from '../../utils/cn';
import apiClient from '../../api/client';

interface Conflict {
  id: string;
  entity_type: string;
  name: string;
  conflict_data: {
    finpilot: Record<string, string | null>;
    tally: Record<string, string | null>;
    differences: Record<string, { finpilot: string; tally: string }>;
  };
  conflict_detected_at?: string;
}

const ENTITY_LABELS: Record<string, string> = {
  ledger: 'Ledger',
  stock_group: 'Stock Group',
  unit: 'Unit',
  godown: 'Godown',
  group: 'Account Group',
};

const api = {
  list: () => apiClient.get('/api/management/conflicts').then(r => r.data),
  resolve: (d: object) => apiClient.post('/api/management/conflicts/resolve', d).then(r => r.data),
};

export default function ConflictsPage() {
  const qc = useQueryClient();
  const [resolveItem, setResolveItem] = useState<Conflict | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['conflicts'],
    queryFn: api.list,
    refetchInterval: 30000,
  });

  const resolveMut = useMutation({
    mutationFn: (resolution: string) =>
      api.resolve({
        entity_type: resolveItem!.entity_type,
        entity_id: resolveItem!.id,
        resolution,
      }),
    onSuccess: (_data, resolution) => {
      toast({
        title: 'Conflict resolved',
        description: `Kept ${resolution === 'keep_finpilot' ? 'FinPilot' : 'TallyPrime'} version.`,
      });
      qc.invalidateQueries({ queryKey: ['conflicts'] });
      qc.invalidateQueries({ queryKey: ['ledgers'] });
      qc.invalidateQueries({ queryKey: ['stock-groups'] });
      setResolveItem(null);
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      toast({ title: 'Error', description: e.response?.data?.detail || 'Failed', variant: 'destructive' });
    },
  });

  const conflicts: Conflict[] = data?.conflicts ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <AlertTriangle className="w-6 h-6 text-amber-500" /> Sync Conflicts
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Records where FinPilot and TallyPrime have different values — choose which to keep
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} className="gap-2">
          <RefreshCw className="w-4 h-4" /> Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-red-600 p-6 bg-red-50 rounded-lg">
          <AlertCircle className="w-5 h-5" /> Failed to load conflicts.
        </div>
      ) : conflicts.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <CheckCircle className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
            <p className="text-lg font-medium text-slate-700">No conflicts</p>
            <p className="text-sm text-slate-500 mt-1">All TallyPrime records are in sync with FinPilot.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
            <strong>{total} conflict{total !== 1 ? 's' : ''} detected.</strong> These records were modified in FinPilot and TallyPrime independently.
            Choose which version to keep — this cannot be undone.
          </div>

          <div className="space-y-4">
            {conflicts.map(c => (
              <Card key={c.id} className="border-amber-200">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base flex items-center gap-2">
                        <span className="bg-amber-100 text-amber-700 text-xs px-2 py-0.5 rounded font-medium">
                          {ENTITY_LABELS[c.entity_type] || c.entity_type}
                        </span>
                        {c.name}
                      </CardTitle>
                      {c.conflict_detected_at && (
                        <p className="text-xs text-slate-400 mt-1">
                          Detected: {new Date(c.conflict_detected_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <Button size="sm" onClick={() => setResolveItem(c)} className="gap-1.5">
                      Resolve
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="grid grid-cols-2 gap-4">
                    {/* FinPilot version */}
                    <div className="bg-indigo-50 rounded-lg p-3">
                      <p className="text-xs font-semibold text-indigo-600 mb-2">FinPilot Version</p>
                      {Object.entries(c.conflict_data?.finpilot || {}).map(([k, v]) => (
                        <div key={k} className="flex gap-2 text-xs">
                          <span className="text-slate-500 capitalize">{k.replace(/_/g, ' ')}:</span>
                          <span className={cn(
                            'font-medium',
                            c.conflict_data?.differences?.[k] ? 'text-indigo-700' : 'text-slate-700'
                          )}>{String(v) || '—'}</span>
                        </div>
                      ))}
                    </div>
                    {/* Tally version */}
                    <div className="bg-teal-50 rounded-lg p-3">
                      <p className="text-xs font-semibold text-teal-600 mb-2">TallyPrime Version</p>
                      {Object.entries(c.conflict_data?.tally || {}).map(([k, v]) => (
                        <div key={k} className="flex gap-2 text-xs">
                          <span className="text-slate-500 capitalize">{k.replace(/_/g, ' ')}:</span>
                          <span className={cn(
                            'font-medium',
                            c.conflict_data?.differences?.[k] ? 'text-teal-700' : 'text-slate-700'
                          )}>{String(v) || '—'}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* Differences summary */}
                  {Object.entries(c.conflict_data?.differences || {}).length > 0 && (
                    <div className="mt-3 text-xs text-slate-500">
                      <span className="font-medium text-amber-600">Conflicting fields: </span>
                      {Object.keys(c.conflict_data.differences).join(', ')}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {/* Resolve Dialog */}
      <Dialog open={!!resolveItem} onOpenChange={() => setResolveItem(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Resolve Conflict: {resolveItem?.name}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-slate-600">Choose which version to keep. The other version will be discarded.</p>
            <p className="text-xs text-red-600 bg-red-50 p-2 rounded">
              This action cannot be undone. The record will be marked as synced with the chosen version.
            </p>
          </div>
          <DialogFooter className="flex gap-2 sm:justify-between">
            <Button
              variant="outline"
              className="flex-1 border-indigo-200 text-indigo-700 hover:bg-indigo-50"
              onClick={() => resolveMut.mutate('keep_finpilot')}
              disabled={resolveMut.isPending}
            >
              {resolveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Keep FinPilot
            </Button>
            <Button
              className="flex-1 bg-teal-600 hover:bg-teal-700"
              onClick={() => resolveMut.mutate('keep_tally')}
              disabled={resolveMut.isPending}
            >
              {resolveMut.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
              Keep TallyPrime
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
