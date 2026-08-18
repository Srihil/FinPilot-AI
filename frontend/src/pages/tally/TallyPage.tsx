import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Zap, CheckCircle, XCircle, RefreshCw, Settings, Info,
  Copy, Clock, AlertTriangle, Activity, Wifi, WifiOff,
  Monitor, Database, Shield, ChevronRight, Loader2, Download,
  ExternalLink, FolderOpen, CheckSquare, TrendingUp, Trash2,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { managementApi } from '../../api/endpoints';
import type { SyncHealth } from '../../types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Separator } from '../../components/ui/separator';
import { toast } from '../../components/ui/use-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import apiClient from '../../api/client';

// ─── Types ───────────────────────────────────────────────────────────────────

interface ConnectorInfo {
  id: string;
  name: string;
  device: string;
  status: string;
  tally_company: string | null;
  tally_host: string;
  tally_port: number;
  last_heartbeat: string | null;
  last_sync_at: string | null;
  paired_at: string;
}

interface TallyStatus {
  connected: boolean;
  connector: ConnectorInfo | null;
  tally_online: boolean;
  message: string;
}

interface ActivityJob {
  id: string;
  operation: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
  payload?: Record<string, unknown>;
}

interface PairingCode {
  code: string;
  expires_in_minutes: number;
  expires_at: string;
}

// ─── API helpers ─────────────────────────────────────────────────────────────

const tallyApi = {
  status: () => apiClient.get<TallyStatus>('/api/tally/status'),
  generatePairing: () => apiClient.post<PairingCode>('/api/tally/pairing/generate'),
  disconnect: () => apiClient.post('/api/tally/disconnect'),
  sync: () => apiClient.post('/api/tally/sync'),
  activity: (limit = 15) => apiClient.get<{ items: ActivityJob[] }>(`/api/tally/activity?limit=${limit}`),
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return 'Never';
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString();
}

// Maps operation string → human label. Prefix is determined by is_update / DELETE / other.
const OP_ENTITY: Record<string, string> = {
  CREATE_LEDGER:          'Ledger',
  CREATE_GROUP:           'Account Group',
  CREATE_STOCK_ITEM:      'Stock Item',
  CREATE_STOCK_GROUP:     'Stock Group',
  CREATE_UNIT:            'Unit',
  CREATE_GODOWN:          'Godown',
  CREATE_STOCK_CATEGORY:  'Stock Category',
  CREATE_VOUCHER_TYPE:    'Voucher Type',
  CREATE_SALES_VOUCHER:   'Sales Voucher',
  CREATE_PURCHASE_VOUCHER:'Purchase Voucher',
  CREATE_RECEIPT_VOUCHER: 'Receipt Voucher',
  CREATE_PAYMENT_VOUCHER: 'Payment Voucher',
  CREATE_JOURNAL_VOUCHER: 'Journal Voucher',
  CREATE_CREDIT_NOTE:     'Credit Note',
  CREATE_DEBIT_NOTE:      'Debit Note',
  CREATE_CONTRA_VOUCHER:  'Contra Voucher',
  CREATE_STOCK_JOURNAL:   'Stock Journal',
  CREATE_PHYSICAL_STOCK:  'Physical Stock',
  CREATE_DELIVERY_NOTE:   'Delivery Note',
  CREATE_RECEIPT_NOTE:    'Receipt Note',
  CREATE_REJECTION_IN:    'Rejection In',
  CREATE_REJECTION_OUT:   'Rejection Out',
  DELETE_LEDGER:          'Ledger',
  DELETE_STOCK_ITEM:      'Stock Item',
  DELETE_STOCK_GROUP:     'Stock Group',
  DELETE_UNIT:            'Unit',
  DELETE_GODOWN:          'Godown',
  DELETE_STOCK_CATEGORY:  'Stock Category',
  DELETE_VOUCHER_TYPE:    'Voucher Type',
  DELETE_VOUCHER:         'Voucher',
  CANCEL_VOUCHER:         'Voucher',
  READ_COMPANIES:         'Companies',
  READ_LEDGERS:           'Ledgers',
  READ_VOUCHERS:          'Vouchers',
  READ_SALES:             'Sales',
  READ_PURCHASES:         'Purchases',
  READ_RECEIVABLES:       'Receivables',
  READ_PAYABLES:          'Payables',
  READ_STOCK_ITEMS:       'Stock Items',
  SYNC_FULL:              'Full Sync',
  SYNC_PARTIAL:           'Partial Sync',
};

function fmtJob(job: ActivityJob): { verb: string; entity: string; name: string; verbColor: string } {
  const op  = job.operation;
  const p   = job.payload ?? {};
  const isUpdate = !!(p.is_update);
  const isDelete = op.startsWith('DELETE_') || op === 'DELETE_VOUCHER' || op === 'CANCEL_VOUCHER';
  const isRead   = op.startsWith('READ_') || op.startsWith('SYNC_');

  const verb = isRead   ? 'Sync'
             : isDelete ? 'Delete'
             : isUpdate ? 'Update'
             : 'Create';

  const verbColor = isDelete ? 'text-red-600'
                  : isUpdate ? 'text-indigo-600'
                  : isRead   ? 'text-slate-500'
                  : 'text-emerald-700';

  const entity = OP_ENTITY[op] ?? op.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());

  // Best human-readable name from payload
  const name = (
    (p.name as string)               ||
    (p.narration as string)          ||
    (p.voucher_number as string)     ||
    (p.transaction_number as string) ||
    ''
  );

  return { verb, entity, name, verbColor };
}

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-red-100 text-red-700',
  PENDING: 'bg-amber-100 text-amber-700',
  CLAIMED: 'bg-blue-100 text-blue-700',
  RUNNING: 'bg-indigo-100 text-indigo-700',
  RETRYING: 'bg-orange-100 text-orange-700',
  CANCELLED: 'bg-slate-100 text-slate-600',
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function ConnectionBadge({ online }: { online: boolean }) {
  return online ? (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700">
      <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      TallyPrime Online
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500">
      <span className="w-2 h-2 rounded-full bg-slate-300" />
      TallyPrime Offline
    </span>
  );
}

const DOWNLOAD_URL = 'https://github.com/Srihil/FinPilot-AI/releases/latest/download/finpilot-tally-connector.exe';
const RELEASES_API = 'https://api.github.com/repos/Srihil/FinPilot-AI/releases/latest';

function useLatestVersion() {
  const [version, setVersion] = useState<string>('');
  useEffect(() => {
    fetch(RELEASES_API, { cache: 'no-store' })
      .then(r => r.json())
      .then(d => setVersion(d.tag_name || ''))
      .catch(() => {});
  }, []);
  return version;
}

function DownloadModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<'info' | 'downloading' | 'done'>('info');
  const linkRef = useRef<HTMLAnchorElement>(null);
  const version = useLatestVersion();

  const startDownload = () => {
    setStep('downloading');
    // Trigger browser save-as dialog via hidden anchor
    linkRef.current?.click();
    // After a short delay show "done" state with next steps
    setTimeout(() => setStep('done'), 1500);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      {/* Hidden anchor — browser will show its native Save As dialog when clicked */}
      <a
        ref={linkRef}
        href={DOWNLOAD_URL}
        download={version ? `finpilot-tally-connector-${version}.exe` : 'finpilot-tally-connector.exe'}
        className="hidden"
      />

      <Card className="w-[480px] shadow-2xl">
        <CardHeader className="pb-3 border-b border-slate-100">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Download className="w-4 h-4 text-indigo-600" />
              Download FinPilot Tally Connector
              {version && (
                <span className="ml-1 px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold">
                  {version}
                </span>
              )}
            </CardTitle>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>
          </div>
          <CardDescription>Windows application · 18 MB · No installation required</CardDescription>
        </CardHeader>

        <CardContent className="pt-5 space-y-4">
          {step === 'info' && (
            <>
              {/* Requirements */}
              <div className="bg-slate-50 rounded-lg p-4 space-y-2">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Before you download</p>
                {[
                  { ok: true,  text: 'Windows 10 or 11' },
                  { ok: true,  text: 'TallyPrime 2.x or higher already installed' },
                  { ok: true,  text: 'TallyPrime HTTP server enabled (F1 → Settings → Connectivity)' },
                  { ok: true,  text: 'Active FinPilot account with Admin role' },
                ].map(({ ok, text }) => (
                  <div key={text} className="flex items-center gap-2.5">
                    <CheckSquare className={`w-4 h-4 shrink-0 ${ok ? 'text-emerald-500' : 'text-slate-300'}`} />
                    <span className="text-sm text-slate-700">{text}</span>
                  </div>
                ))}
              </div>

              {/* What happens after */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">After downloading</p>
                <div className="space-y-2">
                  {[
                    { n: '1', t: 'Choose where to save the file', d: 'Your browser will ask — pick any folder (Desktop works great)' },
                    { n: '2', t: 'Double-click the .exe', d: 'No installation needed — it runs directly' },
                    { n: '3', t: 'Enter your pairing code', d: 'Generate one here by clicking "Connect TallyPrime"' },
                    { n: '4', t: 'Done', d: 'Connector lives in your system tray and runs in the background' },
                  ].map(({ n, t, d }) => (
                    <div key={n} className="flex gap-3">
                      <div className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                        {n}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-900">{t}</p>
                        <p className="text-xs text-slate-500">{d}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-1">
                <Button onClick={startDownload} className="flex-1 gap-2">
                  <FolderOpen className="w-4 h-4" />
                  Download {version || 'Latest'} — Choose Location
                </Button>
                <Button variant="outline" onClick={onClose}>Cancel</Button>
              </div>
            </>
          )}

          {step === 'downloading' && (
            <div className="py-6 text-center space-y-3">
              <Loader2 className="w-10 h-10 animate-spin text-indigo-500 mx-auto" />
              <p className="font-medium text-slate-900">Opening save dialog…</p>
              {version && (
                <p className="text-sm font-semibold text-indigo-700">
                  FinPilot Tally Connector {version}
                </p>
              )}
              <p className="text-sm text-slate-500">
                Your browser will ask where to save{' '}
                <span className="font-mono text-slate-700">
                  finpilot-tally-connector{version ? `-${version}` : ''}.exe
                </span>
              </p>
            </div>
          )}

          {step === 'done' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
                <CheckCircle className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-emerald-900">Download started</p>
                  <p className="text-sm text-emerald-700 mt-0.5">
                    Check your browser's download bar or the folder you selected.
                    If nothing happened, <a href={DOWNLOAD_URL} download className="underline font-medium">click here to try again</a>.
                  </p>
                </div>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                <p className="text-sm font-semibold text-amber-900">Windows SmartScreen Warning — Expected</p>
                <p className="text-sm text-amber-800">
                  Windows may show <em>"Windows protected your PC — Unknown publisher"</em>.
                  This is normal for apps without a paid code-signing certificate.
                </p>
                <p className="text-sm text-amber-800">
                  <strong>To proceed:</strong> Click <strong>"More info"</strong> → then <strong>"Run anyway"</strong>.
                </p>
              </div>

              <div className="flex gap-3">
                <Button onClick={onClose} className="flex-1">Done</Button>
                <Button variant="outline" onClick={() => setStep('info')}>Back</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PairingModal({
  pairing,
  onClose,
}: {
  pairing: PairingCode;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [timeLeft, setTimeLeft] = useState(pairing.expires_in_minutes * 60);

  useEffect(() => {
    const t = setInterval(() => setTimeLeft(p => Math.max(0, p - 1)), 1000);
    return () => clearInterval(t);
  }, []);

  const copy = () => {
    navigator.clipboard.writeText(pairing.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const mins = Math.floor(timeLeft / 60);
  const secs = timeLeft % 60;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="w-[420px] shadow-2xl">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="w-5 h-5 text-indigo-600" />
            Connect TallyPrime Connector
          </CardTitle>
          <CardDescription>
            Enter this code in the FinPilot Tally Connector on your Windows PC.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="text-center p-6 bg-slate-50 rounded-xl border-2 border-dashed border-slate-200">
            <p className="text-xs font-medium text-slate-500 mb-2 uppercase tracking-wider">Pairing Code</p>
            <p className="text-4xl font-mono font-bold text-slate-900 tracking-widest">{pairing.code}</p>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-1.5 text-slate-500">
              <Clock className="w-4 h-4" />
              Expires in {mins}:{secs.toString().padStart(2, '0')}
            </span>
            <Button size="sm" variant="outline" onClick={copy} className="gap-1.5">
              <Copy className="w-3.5 h-3.5" />
              {copied ? 'Copied!' : 'Copy'}
            </Button>
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
            <strong>Steps:</strong> Open the FinPilot Connector on your PC → enter this code → connector will pair automatically.
          </div>

          <div className="space-y-1.5 text-sm text-slate-600">
            <p className="font-medium text-slate-900">Setup checklist:</p>
            {[
              'TallyPrime is running with a company open',
              'HTTP server enabled in Tally (F12 → Configure → Connectivity)',
              'FinPilot Connector installed on same PC as Tally',
            ].map((s, i) => (
              <div key={i} className="flex items-start gap-2">
                <ChevronRight className="w-4 h-4 text-indigo-500 mt-0.5 shrink-0" />
                <span>{s}</span>
              </div>
            ))}
          </div>

          <Button variant="outline" className="w-full" onClick={onClose}>
            Close
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TallyPage() {
  const [status, setStatus] = useState<TallyStatus | null>(null);
  const [activity, setActivity] = useState<ActivityJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [pairing, setPairing] = useState<PairingCode | null>(null);
  const [showDownload, setShowDownload] = useState(false);
  const [showWipeConfirm, setShowWipeConfirm] = useState(false);
  const latestVersion = useLatestVersion();
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qc = useQueryClient();

  const wipeMut = useMutation({
    mutationFn: () => managementApi.wipeAllLocalData(),
    onSuccess: (res) => {
      const total =
        res.invoices + res.expenses + res.stock_transactions +
        res.voucher_types + res.ledgers + res.account_groups +
        res.stock_groups + res.stock_items + res.stock_categories +
        res.units + res.godowns;
      toast({
        title: 'All local data wiped',
        description: `${total} records removed. Click Sync Now to re-import from TallyPrime.`,
      });
      setShowWipeConfirm(false);
      qc.invalidateQueries({ queryKey: ['vouchers'] });
      qc.invalidateQueries({ queryKey: ['tally-sync-health'] });
    },
    onError: () => {
      toast({ title: 'Error', description: 'Failed to wipe local data', variant: 'destructive' });
    },
  });

  const { data: syncHealth } = useQuery<SyncHealth>({
    queryKey: ['tally-sync-health'],
    queryFn: managementApi.syncHealth,
    refetchInterval: 30_000,
  });

  const fetchStatus = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        tallyApi.status(),
        tallyApi.activity(),
      ]);
      setStatus(s.data);
      setActivity(a.data.items);
    } catch {
      // status fetch errors are non-fatal
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 15_000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  useEffect(() => {
    return () => {
      if (syncPollRef.current) clearInterval(syncPollRef.current);
    };
  }, []);

  const handleGeneratePairing = async () => {
    setActionLoading('pair');
    try {
      const res = await tallyApi.generatePairing();
      setPairing(res.data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Error', description: err?.response?.data?.detail || 'Failed to generate pairing code', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSync = async () => {
    setActionLoading('sync');
    try {
      const res = await tallyApi.sync();
      const data = res.data as { message?: string; job_id?: string };
      toast({ title: 'Sync queued', description: 'Syncing data from TallyPrime…' });

      const jobId = data.job_id;
      if (!jobId) {
        setActionLoading(null);
        setTimeout(fetchStatus, 2000);
        return;
      }

      let polls = 0;
      syncPollRef.current = setInterval(async () => {
        polls++;
        try {
          const jobRes = await apiClient.get<{
            status: string;
            result: Record<string, unknown> | null;
            error_message: string | null;
          }>(`/api/tally/jobs/${jobId}`);
          const job = jobRes.data;

          if (job.status === 'SUCCESS') {
            clearInterval(syncPollRef.current!);
            syncPollRef.current = null;
            setActionLoading(null);
            const stats = (job.result as { import_stats?: Record<string, number> } | null)?.import_stats;
            const parts = stats
              ? ([
                  stats.imported_customers ? `${stats.imported_customers} customer${stats.imported_customers !== 1 ? 's' : ''}` : null,
                  stats.imported_vendors ? `${stats.imported_vendors} vendor${stats.imported_vendors !== 1 ? 's' : ''}` : null,
                  stats.imported_invoices ? `${stats.imported_invoices} invoice${stats.imported_invoices !== 1 ? 's' : ''}` : null,
                  stats.imported_expenses ? `${stats.imported_expenses} expense${stats.imported_expenses !== 1 ? 's' : ''}` : null,
                ] as (string | null)[]).filter((x): x is string => x !== null)
              : [];
            const desc = parts.length
              ? `Imported: ${parts.join(', ')}. Check the Customers & Invoices pages.`
              : 'Sync complete — no new records to import.';
            toast({ title: 'Sync complete', description: desc });
            fetchStatus();
          } else if (job.status === 'FAILED') {
            clearInterval(syncPollRef.current!);
            syncPollRef.current = null;
            setActionLoading(null);
            toast({
              title: 'Sync failed',
              description: job.error_message || 'Connector could not complete the sync',
              variant: 'destructive',
            });
            fetchStatus();
          }
        } catch {
          // ignore transient poll errors
        }

        if (polls >= 40) { // stop after ~2 min
          clearInterval(syncPollRef.current!);
          syncPollRef.current = null;
          setActionLoading(null);
          fetchStatus();
        }
      }, 3000);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Sync failed', description: err?.response?.data?.detail || 'Could not start sync', variant: 'destructive' });
      setActionLoading(null);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Disconnect and revoke the Tally connector? The connector will stop working immediately.')) return;
    setActionLoading('disconnect');
    try {
      await tallyApi.disconnect();
      toast({ title: 'Disconnected', description: 'Connector revoked successfully.' });
      await fetchStatus();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast({ title: 'Error', description: err?.response?.data?.detail || 'Failed to disconnect', variant: 'destructive' });
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  const connector = status?.connector;
  const connected = status?.connected ?? false;
  const tallyOnline = status?.tally_online ?? false;

  return (
    <div className="space-y-6 max-w-3xl">
      {showDownload && <DownloadModal onClose={() => setShowDownload(false)} />}
      {pairing && <PairingModal pairing={pairing} onClose={() => { setPairing(null); fetchStatus(); }} />}

      {/* ── Wipe All Local Data Confirm Dialog ── */}
      <Dialog open={showWipeConfirm} onOpenChange={setShowWipeConfirm}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-red-600 flex items-center gap-2">
              <Trash2 className="w-4 h-4" /> Wipe All Local Data
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 text-sm text-slate-700">
            <p>
              This will permanently remove <strong>all data</strong> stored in FinPilot for your company.
              After wiping, click <strong>Sync Now</strong> to re-import everything fresh from TallyPrime.
            </p>
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1 text-xs text-red-800">
              <p className="font-semibold mb-1">The following will be deleted:</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                {[
                  'Sales & Purchase Invoices',
                  'Receipts, Payments, Journals',
                  'Contra, Credit & Debit Notes',
                  'All Stock Transactions',
                  'Voucher Types (custom & base)',
                  'Ledgers',
                  'Account Groups',
                  'Stock Groups & Items',
                  'Stock Categories',
                  'Units of Measure',
                  'Godowns / Warehouses',
                ].map(item => (
                  <div key={item} className="flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-red-400 shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs text-slate-600">
              <p className="font-semibold text-slate-700 mb-0.5">Safe — these are NOT deleted:</p>
              <p>Customers, vendors, users, company settings, audit logs, TallyPrime connector pairing.</p>
            </div>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              <strong>This action cannot be undone.</strong> Make sure TallyPrime is running and connected before syncing afterward.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowWipeConfirm(false)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={() => wipeMut.mutate()}
              disabled={wipeMut.isPending}
              className="gap-2"
            >
              {wipeMut.isPending
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Trash2 className="w-4 h-4" />}
              Yes, Wipe All Local Data
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">TallyPrime Integration</h2>
          <p className="text-sm text-slate-500">
            Connect your local TallyPrime installation through the FinPilot Connector.
          </p>
        </div>
        <Button
          variant="destructive"
          size="sm"
          className="gap-2 shrink-0"
          onClick={() => setShowWipeConfirm(true)}
          disabled={wipeMut.isPending}
        >
          {wipeMut.isPending
            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
            : <Trash2 className="w-3.5 h-3.5" />}
          Wipe All Local Data
        </Button>
      </div>

      {/* ── Status Card ── */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
                connected ? 'bg-emerald-100' : 'bg-slate-100'
              }`}>
                {connected ? (
                  <Wifi className="w-6 h-6 text-emerald-600" />
                ) : (
                  <WifiOff className="w-6 h-6 text-slate-400" />
                )}
              </div>
              <div>
                <p className="font-semibold text-slate-900">
                  {connected ? 'Connector Paired' : 'No Connector Paired'}
                </p>
                {connected && connector ? (
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                    <ConnectionBadge online={tallyOnline} />
                    <span className="text-xs text-slate-400">·</span>
                    <span className="text-xs text-slate-500">{connector.device}</span>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 mt-0.5">{status?.message}</p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {connected && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSync}
                    disabled={!tallyOnline || actionLoading === 'sync'}
                    className="gap-1.5"
                  >
                    {actionLoading === 'sync' ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    Sync Now
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleDisconnect}
                    disabled={actionLoading === 'disconnect'}
                  >
                    Disconnect
                  </Button>
                </>
              )}
              {!connected && (
                <Button
                  onClick={handleGeneratePairing}
                  disabled={actionLoading === 'pair'}
                  className="gap-1.5"
                >
                  {actionLoading === 'pair' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Zap className="w-4 h-4" />
                  )}
                  Connect TallyPrime
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={fetchStatus} className="gap-1.5">
                <RefreshCw className="w-3.5 h-3.5" />
                Refresh
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Connector Details ── */}
      {connected && connector && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2">
              <Monitor className="w-4 h-4 text-indigo-600" />
              Connector Details
            </CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-slate-100">
            {[
              { label: 'Connector Name', value: connector.name },
              { label: 'Device', value: connector.device || '—' },
              { label: 'TallyPrime Company', value: connector.tally_company || 'Not detected yet' },
              { label: 'Tally Address', value: `${connector.tally_host}:${connector.tally_port}` },
              { label: 'Last Heartbeat', value: relTime(connector.last_heartbeat) },
              { label: 'Last Sync', value: relTime(connector.last_sync_at) },
              { label: 'Paired On', value: new Date(connector.paired_at).toLocaleString() },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-slate-500">{label}</span>
                <span className="font-medium text-slate-900">{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* ── Sync Health ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-indigo-600" />
            Sync Health
          </CardTitle>
          <CardDescription>Cumulative statistics for all Tally integration jobs</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {[
              { label: 'Total Jobs', value: syncHealth?.total_jobs ?? 0, color: 'text-slate-900' },
              { label: 'Successful', value: syncHealth?.successful ?? 0, color: 'text-emerald-600' },
              { label: 'Failed', value: syncHealth?.failed ?? 0, color: 'text-red-600' },
              { label: 'Pending', value: syncHealth?.pending ?? 0, color: 'text-amber-600' },
              { label: 'Retrying', value: syncHealth?.retrying ?? 0, color: 'text-orange-600' },
            ].map(({ label, value, color }) => (
              <div key={label} className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <p className={`text-xl font-bold ${color}`}>{value}</p>
                <p className="text-xs text-slate-500 mt-0.5">{label}</p>
              </div>
            ))}
          </div>
          {syncHealth?.last_successful_sync && (
            <p className="text-xs text-slate-400 mt-3">
              Last successful sync: {new Date(syncHealth.last_successful_sync).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Activity Log ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            Integration Activity
          </CardTitle>
          <CardDescription>Recent Tally jobs and sync operations</CardDescription>
        </CardHeader>
        <CardContent>
          {activity.length === 0 ? (
            <div className="py-8 text-center">
              <Database className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm text-slate-500">No activity yet. Sync will appear here once the connector is paired.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {activity.map(job => {
                const { verb, entity, name, verbColor } = fmtJob(job);
                return (
                  <div key={job.id} className="flex items-start justify-between py-2.5 text-sm gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <span className={`shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[job.status] ?? 'bg-slate-100 text-slate-600'}`}>
                        {job.status}
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900 leading-snug">
                          <span className={verbColor}>{verb}</span>
                          <span className="text-slate-500 font-normal"> {entity}</span>
                        </p>
                        {name && (
                          <p className="text-xs text-slate-500 truncate mt-0.5" title={name}>· {name}</p>
                        )}
                        {job.retry_count > 0 && (
                          <p className="text-xs text-orange-500 mt-0.5">retry {job.retry_count}</p>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-slate-400 text-xs">{relTime(job.completed_at || job.created_at)}</p>
                      {job.error_message && (
                        <p className="text-red-500 text-xs break-words whitespace-normal mt-0.5 max-w-[200px]">
                          {job.error_message}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Safety Notice ── */}
      <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div>
          <p className="font-semibold mb-0.5">Tally Data Safety</p>
          <p>Records cannot be deleted or modified through the connector. To modify or delete data, do so directly in TallyPrime and re-sync to update FinPilot. Financial records are never silently overwritten.</p>
        </div>
      </div>

      {/* ── Download Connector ── */}
      <Card className="border-indigo-100 bg-gradient-to-br from-indigo-50 to-white">
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-5">
            <div className="w-12 h-12 rounded-xl bg-indigo-600 flex items-center justify-center shrink-0">
              <Download className="w-6 h-6 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-slate-900 text-base">
                  FinPilot Tally Connector
                </p>
                {latestVersion && (
                  <span className="px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold">
                    {latestVersion}
                  </span>
                )}
              </div>
              <p className="text-sm text-slate-500 mt-0.5">
                Windows application · Runs on the same PC as TallyPrime · No technical setup needed
              </p>
              <div className="flex flex-wrap gap-2 mt-2">
                {['Windows 10/11', 'TallyPrime 2.x+', 'Free'].map(tag => (
                  <span key={tag} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-2 shrink-0">
              <Button
                onClick={() => setShowDownload(true)}
                className="gap-2"
              >
                <Download className="w-4 h-4" />
                Download Connector
              </Button>
              <a
                href="https://github.com/Srihil/FinPilot-AI/releases/latest"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-1.5 text-xs text-slate-500 hover:text-indigo-600 transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
                View all releases
              </a>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { n: '1', t: 'Download & Run', d: 'Double-click the .exe — no installation required' },
              { n: '2', t: 'Enter Pairing Code', d: 'Generate a code here and enter it in the connector' },
              { n: '3', t: 'Connected', d: 'Connector links to your TallyPrime automatically' },
            ].map(({ n, t, d }) => (
              <div key={n} className="flex gap-3 p-3 bg-white rounded-lg border border-indigo-100">
                <div className="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold shrink-0">
                  {n}
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">{t}</p>
                  <p className="text-xs text-slate-500">{d}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── How It Works ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Info className="w-4 h-4 text-indigo-600" />
            Architecture — How It Works
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-slate-600">
          <div className="p-3 bg-indigo-50 border border-indigo-100 rounded-lg">
            <p className="text-indigo-900 font-medium mb-1">Secure Connector Architecture</p>
            <p className="text-indigo-700 text-xs">
              FinPilot <strong>never</strong> exposes TallyPrime to the internet. The connector runs on
              your PC, reaches out to FinPilot cloud over HTTPS, and communicates with Tally locally.
            </p>
          </div>

          <div className="space-y-2">
            {[
              { icon: '🌐', title: 'FinPilot Cloud (Render)', desc: 'Hosts job queue. Connector polls securely over HTTPS.' },
              { icon: '🖥️', title: 'FinPilot Connector (Your PC)', desc: 'Lightweight Python process. Polls cloud, executes Tally operations locally.' },
              { icon: '📊', title: 'TallyPrime (localhost:9000)', desc: 'Never exposed to internet. Connector communicates via XML/HTTP on localhost.' },
            ].map(({ icon, title, desc }) => (
              <div key={title} className="flex gap-3 p-3 bg-slate-50 rounded-lg">
                <span className="text-xl">{icon}</span>
                <div>
                  <p className="font-semibold text-slate-900">{title}</p>
                  <p className="text-slate-500 text-xs">{desc}</p>
                </div>
              </div>
            ))}
          </div>

          <Separator />

          <div>
            <p className="font-semibold text-slate-900 mb-2">Setup Steps</p>
            <div className="space-y-2">
              {[
                { n: '1', t: 'Enable TallyPrime HTTP Server', d: 'In Tally: F12 → Configure → Connectivity → Enable HTTP server on port 9000' },
                { n: '2', t: 'Download FinPilot Connector', d: 'Download from the /tally-connector directory of this repository and run setup.bat' },
                { n: '3', t: 'Generate Pairing Code', d: 'Click "Connect TallyPrime" above. A code appears — enter it in the connector.' },
                { n: '4', t: 'Connector Registers', d: 'Connector pairs, starts polling for jobs, and sends heartbeats every 30 seconds.' },
              ].map(({ n, t, d }) => (
                <div key={n} className="flex gap-3">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                    {n}
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{t}</p>
                    <p className="text-xs text-slate-500">{d}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800">
              <strong>Demo mode:</strong> When no connector is paired, FinPilot uses its internal
              PostgreSQL data. Tally data is only read/written when a connector is active.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
