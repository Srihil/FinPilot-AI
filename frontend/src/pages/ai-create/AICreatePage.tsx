import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Wand2, Zap, Loader2, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { aiCreateApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { toast } from '../../components/ui/use-toast';

const QUICK_GROUPS = [
  {
    label: 'Accounting Masters',
    chips: ['Create Ledger account', 'Create account Group', 'Add Customer ledger', 'Add Vendor ledger'],
  },
  {
    label: 'Inventory Masters',
    chips: ['Add Stock Item / product', 'Create Stock Group', 'Create Unit of measure', 'Add Godown / warehouse'],
  },
  {
    label: 'Vouchers (Transactions)',
    chips: ['Create Sales Invoice', 'Record Purchase Bill', 'Record Receipt from customer',
            'Record Payment to vendor', 'Journal Entry', 'Credit Note (sales return)',
            'Debit Note (purchase return)', 'Contra / bank transfer'],
  },
];

const ENTITY_COLORS: Record<string, string> = {
  customer: 'bg-emerald-100 text-emerald-800',
  vendor: 'bg-blue-100 text-blue-800',
  ledger: 'bg-teal-100 text-teal-800',
  group: 'bg-teal-100 text-teal-800',
  sales_invoice: 'bg-indigo-100 text-indigo-800',
  purchase_bill: 'bg-orange-100 text-orange-800',
  invoice: 'bg-indigo-100 text-indigo-800',
  expense: 'bg-purple-100 text-purple-800',
  stock_item: 'bg-slate-100 text-slate-800',
  product: 'bg-slate-100 text-slate-800',
  stock_group: 'bg-slate-100 text-slate-800',
  unit: 'bg-slate-100 text-slate-800',
  godown: 'bg-amber-100 text-amber-800',
  receipt: 'bg-green-100 text-green-800',
  payment: 'bg-red-100 text-red-800',
  journal: 'bg-violet-100 text-violet-800',
  credit_note: 'bg-yellow-100 text-yellow-800',
  debit_note: 'bg-pink-100 text-pink-800',
  contra: 'bg-cyan-100 text-cyan-800',
};

type ExtractionResult = {
  entity_type: string;
  data: Record<string, unknown>;
  confidence: number;
  missing_fields: string[];
};

type CreationResult = {
  id: string;
  entity_type: string;
  tally_queued: boolean;
};

// Returns a label for a field key
function fieldLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function AICreatePage() {
  const [text, setText] = useState('');
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [editableData, setEditableData] = useState<Record<string, unknown>>({});
  const [created, setCreated] = useState<CreationResult | null>(null);

  const extractMutation = useMutation({
    mutationFn: () => aiCreateApi.extractEntity(text),
    onSuccess: (result) => {
      setExtraction(result);
      setEditableData({ ...result.data });
      setCreated(null);
    },
    onError: () => {
      toast({ title: 'Extraction failed', description: 'Could not contact AI service.', variant: 'destructive' });
    },
  });

  const createMutation = useMutation({
    mutationFn: () =>
      aiCreateApi.createEntity(extraction!.entity_type, editableData),
    onSuccess: (result) => {
      setCreated(result);
      toast({
        title: `${fieldLabel(result.entity_type)} created`,
        description: result.tally_queued
          ? 'Also queued for Tally sync.'
          : 'Saved to FinPilot (no Tally connector active).',
        variant: 'success',
      });
    },
    onError: (err: unknown) => {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Something went wrong.';
      toast({ title: 'Creation failed', description: message, variant: 'destructive' });
    },
  });

  function handleQuickStart(chip: string) {
    setText(chip);
  }

  function handleExtract() {
    if (!text.trim()) return;
    extractMutation.mutate();
  }

  function handleFieldChange(key: string, value: string) {
    setEditableData((prev) => ({ ...prev, [key]: value }));
  }

  function handleReset() {
    setText('');
    setExtraction(null);
    setEditableData({});
    setCreated(null);
  }

  const isLoading = extractMutation.isPending;
  const isCreating = createMutation.isPending;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Wand2 className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-slate-900">Create with AI</h1>
        </div>
        <p className="text-slate-500 text-sm">
          Describe anything in plain English — AI extracts the details
        </p>
      </div>

      {/* Input card */}
      {!created && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <div>
              <Label htmlFor="ai-input" className="text-sm font-medium text-slate-700 mb-1.5 block">
                What would you like to create?
              </Label>
              <textarea
                id="ai-input"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleExtract();
                }}
                rows={4}
                placeholder="e.g. Add customer ABC Traders, email abc@traders.com, GST 27AABCU9603R1ZX..."
                className="w-full px-3 py-2 rounded-md border border-slate-200 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>

            {/* Quick-start chips grouped by category */}
            <div className="space-y-3">
              {QUICK_GROUPS.map((group) => (
                <div key={group.label}>
                  <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">{group.label}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {group.chips.map((chip) => (
                      <button
                        key={chip}
                        onClick={() => handleQuickStart(chip)}
                        className="text-xs px-2.5 py-1 rounded-full border border-slate-200 text-slate-600 hover:bg-indigo-50 hover:border-indigo-300 hover:text-indigo-700 transition-colors"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <Button
              onClick={handleExtract}
              disabled={!text.trim() || isLoading}
              className="w-full"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Extracting...
                </>
              ) : (
                <>
                  <Wand2 className="w-4 h-4 mr-2" />
                  Extract with AI
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-1">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-9 w-full" />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Extraction preview */}
      {extraction && !isLoading && !created && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Preview</CardTitle>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${ENTITY_COLORS[extraction.entity_type] || 'bg-slate-100 text-slate-700'}`}>
                {fieldLabel(extraction.entity_type)}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <div className="flex-1 bg-slate-100 rounded-full h-1.5">
                <div
                  className="bg-indigo-500 h-1.5 rounded-full transition-all"
                  style={{ width: `${Math.round(extraction.confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs text-slate-500 shrink-0">
                {Math.round(extraction.confidence * 100)}% confidence
              </span>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Editable fields */}
            <div className="grid gap-3">
              {Object.entries(editableData).map(([key, val]) => (
                <div key={key} className="space-y-1">
                  <Label htmlFor={`field-${key}`} className="text-xs font-medium text-slate-600">
                    {fieldLabel(key)}
                  </Label>
                  <Input
                    id={`field-${key}`}
                    value={val != null ? String(val) : ''}
                    onChange={(e) => handleFieldChange(key, e.target.value)}
                    className="text-sm"
                  />
                </div>
              ))}
            </div>

            {/* Missing fields warning */}
            {extraction.missing_fields && extraction.missing_fields.length > 0 && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-medium text-amber-800">Missing information</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    {extraction.missing_fields.join(', ')}
                  </p>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-3 pt-1">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
                className="flex-1"
              >
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                Start Over
              </Button>
              <Button
                onClick={() => createMutation.mutate()}
                disabled={isCreating}
                size="sm"
                className="flex-1"
              >
                {isCreating ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Zap className="w-3.5 h-3.5 mr-1.5" />
                    Create &amp; Sync to Tally
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Success state */}
      {created && (
        <Card className="border-emerald-200 bg-emerald-50">
          <CardContent className="pt-6 space-y-4">
            <div className="flex items-center gap-3">
              <CheckCircle className="w-8 h-8 text-emerald-600 shrink-0" />
              <div>
                <p className="font-semibold text-emerald-900">
                  {fieldLabel(created.entity_type)} created successfully
                </p>
                <p className="text-sm text-emerald-700 mt-0.5">
                  {created.tally_queued
                    ? 'Queued for sync to TallyPrime.'
                    : 'Saved to FinPilot (connect TallyPrime to sync).'}
                </p>
                {created.id && <p className="text-xs text-emerald-600 mt-1 font-mono">ID: {created.id}</p>}
              </div>
            </div>
            <Button onClick={handleReset} variant="outline" className="w-full border-emerald-300 text-emerald-800 hover:bg-emerald-100">
              <Wand2 className="w-4 h-4 mr-2" />
              Create Another
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
