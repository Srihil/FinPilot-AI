import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, XCircle, Clock, AlertTriangle, Eye } from 'lucide-react';
import { approvalsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Label } from '../../components/ui/label';
import { formatCurrency, formatDateTime, formatRelativeTime } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import { useAuth } from '../../auth/AuthContext';
import type { Approval } from '../../types';

function ApprovalDetailModal({
  approval,
  onClose,
  onApprove,
  onReject,
  canAct,
}: {
  approval: Approval;
  onClose: () => void;
  onApprove: (id: string, notes: string) => void;
  onReject: (id: string, notes: string) => void;
  canAct: boolean;
}) {
  const [notes, setNotes] = useState('');
  const [acting, setActing] = useState(false);

  const handleApprove = async () => {
    setActing(true);
    await onApprove(approval.id, notes);
    setActing(false);
    onClose();
  };

  const handleReject = async () => {
    if (!notes.trim()) {
      toast({ title: 'Please add a rejection reason', variant: 'destructive' });
      return;
    }
    setActing(true);
    await onReject(approval.id, notes);
    setActing(false);
    onClose();
  };

  return (
    <DialogContent className="max-w-lg">
      <DialogHeader>
        <DialogTitle>Approval Request</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <div className="bg-slate-50 rounded-lg p-4 space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Reference</span>
            <span className="font-medium">{approval.transaction_ref}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Type</span>
            <span className="font-medium">{approval.transaction_type}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Amount</span>
            <span className="font-bold text-lg">{formatCurrency(approval.amount)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Requested by</span>
            <span className="font-medium">{approval.requested_by_name}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Submitted</span>
            <span className="font-medium">{formatDateTime(approval.created_at)}</span>
          </div>
        </div>

        {approval.validation_warnings && approval.validation_warnings.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
            <div className="flex items-center gap-2 text-amber-700 text-sm font-semibold">
              <AlertTriangle className="w-4 h-4" />
              Validation Warnings
            </div>
            {approval.validation_warnings.map((w, i) => (
              <p key={i} className="text-amber-600 text-xs">{w}</p>
            ))}
          </div>
        )}

        {canAct && (
          <div className="space-y-1.5">
            <Label>Notes (required for rejection)</Label>
            <Textarea
              placeholder="Add notes or reason for your decision..."
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
            />
          </div>
        )}
      </div>

      {canAct && (
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={handleReject} loading={acting}>
            <XCircle className="w-4 h-4 mr-2" />
            Reject
          </Button>
          <Button variant="success" onClick={handleApprove} loading={acting}>
            <CheckCircle className="w-4 h-4 mr-2" />
            Approve
          </Button>
        </DialogFooter>
      )}
    </DialogContent>
  );
}

export default function ApprovalsPage() {
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canAct = user?.role === 'ADMIN';

  const { data: approvals, isLoading } = useQuery({
    queryKey: ['approvals'],
    queryFn: approvalsApi.list,
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => approvalsApi.approve(id, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      toast({ title: 'Transaction approved', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to approve', variant: 'destructive' }),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => approvalsApi.reject(id, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals'] });
      toast({ title: 'Transaction rejected', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to reject', variant: 'destructive' }),
  });

  const pendingCount = approvals?.filter(a => a.status === 'PENDING').length || 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Approval Queue</h2>
          <p className="text-sm text-slate-500">{pendingCount} pending approvals</p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Pending', count: approvals?.filter(a => a.status === 'PENDING').length || 0, color: 'text-amber-600', bg: 'bg-amber-50', icon: Clock },
          { label: 'Approved', count: approvals?.filter(a => a.status === 'APPROVED').length || 0, color: 'text-emerald-600', bg: 'bg-emerald-50', icon: CheckCircle },
          { label: 'Rejected', count: approvals?.filter(a => a.status === 'REJECTED').length || 0, color: 'text-red-600', bg: 'bg-red-50', icon: XCircle },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="p-5 flex items-center gap-4">
              <div className={`w-10 h-10 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-5 h-5 ${s.color}`} />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{s.count}</p>
                <p className="text-sm text-slate-500">{s.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">All Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">{[1,2,3,4].map(i => <Skeleton key={i} className="h-16" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Type</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Reference</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Amount</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Requested By</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Submitted</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {approvals?.length ? approvals.map((approval: Approval) => (
                    <tr key={approval.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 text-slate-600">{approval.transaction_type}</td>
                      <td className="py-3 px-4 font-medium text-slate-900">{approval.transaction_ref}</td>
                      <td className="py-3 px-4 text-right font-bold text-slate-900">{formatCurrency(approval.amount)}</td>
                      <td className="py-3 px-4 text-slate-600">{approval.requested_by_name}</td>
                      <td className="py-3 px-4 text-slate-500 text-xs">{formatRelativeTime(approval.created_at)}</td>
                      <td className="py-3 px-4">
                        {approval.status === 'PENDING' && <Badge variant="secondary">Pending</Badge>}
                        {approval.status === 'APPROVED' && <Badge variant="success">Approved</Badge>}
                        {approval.status === 'REJECTED' && <Badge variant="destructive">Rejected</Badge>}
                      </td>
                      <td className="py-3 px-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedApproval(approval)}
                          className="text-indigo-600 hover:text-indigo-700"
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          View
                        </Button>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="py-16 text-center">
                        <CheckCircle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                        <p className="text-slate-400 text-sm">No approvals to review</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!selectedApproval} onOpenChange={() => setSelectedApproval(null)}>
        {selectedApproval && (
          <ApprovalDetailModal
            approval={selectedApproval}
            onClose={() => setSelectedApproval(null)}
            onApprove={(id, notes) => approveMutation.mutateAsync({ id, notes })}
            onReject={(id, notes) => rejectMutation.mutateAsync({ id, notes })}
            canAct={canAct && selectedApproval.status === 'PENDING'}
          />
        )}
      </Dialog>
    </div>
  );
}
