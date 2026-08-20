import { useState } from 'react';
import { Download, FileText, Sheet, Braces, FileBarChart, Loader2, X } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './dialog';
import { Button } from './button';
import { Label } from './label';
import { cn } from '../../utils/cn';

export type ExportFormat = 'csv' | 'xlsx' | 'json' | 'pdf';

interface FormatOption {
  value: ExportFormat;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

const FORMAT_OPTIONS: FormatOption[] = [
  {
    value: 'xlsx',
    label: 'Excel',
    description: 'Formatted spreadsheet with column headers',
    icon: Sheet,
    color: 'text-emerald-600 bg-emerald-50 border-emerald-200',
  },
  {
    value: 'csv',
    label: 'CSV',
    description: 'Plain comma-separated, import-ready',
    icon: FileText,
    color: 'text-blue-600 bg-blue-50 border-blue-200',
  },
  {
    value: 'pdf',
    label: 'PDF',
    description: 'Print-ready report with company header',
    icon: FileBarChart,
    color: 'text-rose-600 bg-rose-50 border-rose-200',
  },
  {
    value: 'json',
    label: 'JSON',
    description: 'Structured data for API / integration use',
    icon: Braces,
    color: 'text-violet-600 bg-violet-50 border-violet-200',
  },
];

interface ExportDialogProps {
  open: boolean;
  onClose: () => void;
  /** Called when the user clicks Export. Receives the chosen format. */
  onExport: (format: ExportFormat) => void | Promise<void>;
  /** E.g. "Sales Vouchers — Jan 2026" shown so user knows what will be exported */
  contextLabel: string;
  isExporting?: boolean;
}

export function ExportDialog({
  open,
  onClose,
  onExport,
  contextLabel,
  isExporting = false,
}: ExportDialogProps) {
  const [selected, setSelected] = useState<ExportFormat>('xlsx');

  const handleExport = async () => {
    await onExport(selected);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !isExporting) onClose(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-slate-900">
            <Download className="w-5 h-5 text-indigo-600" />
            Export Data
          </DialogTitle>
        </DialogHeader>

        {/* Context label */}
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 text-sm text-indigo-700 font-medium">
          Exporting: <span className="font-semibold">{contextLabel}</span>
        </div>

        {/* Format selector */}
        <div className="space-y-2">
          <Label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            File Format
          </Label>
          <div className="grid grid-cols-2 gap-2">
            {FORMAT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setSelected(opt.value)}
                className={cn(
                  'text-left p-3 rounded-xl border-2 transition-all',
                  selected === opt.value
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50',
                )}
              >
                <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center mb-2 border', opt.color)}>
                  <opt.icon className="w-4 h-4" />
                </div>
                <p className={cn(
                  'font-semibold text-sm',
                  selected === opt.value ? 'text-indigo-700' : 'text-slate-800',
                )}>
                  {opt.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5 leading-snug">{opt.description}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Destination note */}
        <p className="text-xs text-slate-400">
          Your browser will prompt you to choose where to save the file.
        </p>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onClose} disabled={isExporting}>
            <X className="w-4 h-4 mr-1" /> Cancel
          </Button>
          <Button onClick={handleExport} disabled={isExporting}>
            {isExporting
              ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              : <Download className="w-4 h-4 mr-2" />
            }
            {isExporting ? 'Exporting…' : `Export ${selected.toUpperCase()}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
