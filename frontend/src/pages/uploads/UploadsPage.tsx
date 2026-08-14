import { useState, useRef, useCallback } from 'react';
import { Upload, FileText, CheckCircle, XCircle, AlertTriangle, Download } from 'lucide-react';
import { uploadsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Label } from '../../components/ui/label';
import { Progress } from '../../components/ui/progress';
import { Badge } from '../../components/ui/badge';
import { toast } from '../../components/ui/use-toast';
import { formatFileSize } from '../../utils/format';
import { cn } from '../../utils/cn';
import type { UploadResult } from '../../types';

const DATA_TYPES = [
  { value: 'customers', label: 'Customers' },
  { value: 'vendors', label: 'Vendors' },
  { value: 'products', label: 'Products' },
  { value: 'invoices', label: 'Invoices' },
  { value: 'expenses', label: 'Expenses' },
];

export default function UploadsPage() {
  const [isDragging, setIsDragging] = useState(false);
  const [dataType, setDataType] = useState('');
  const [uploadType, setUploadType] = useState<'csv' | 'pdf'>('csv');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) setSelectedFile(file);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    if (uploadType === 'csv' && !dataType) {
      toast({ title: 'Please select a data type', variant: 'destructive' });
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setResult(null);

    const interval = setInterval(() => {
      setUploadProgress(prev => Math.min(prev + 15, 85));
    }, 300);

    try {
      if (uploadType === 'csv') {
        const res = await uploadsApi.uploadCSV(selectedFile, dataType);
        setResult(res);
      } else {
        await uploadsApi.uploadPDFInvoice(selectedFile);
        toast({ title: 'PDF invoice processed successfully', variant: 'success' });
      }
      setUploadProgress(100);
      toast({ title: 'Upload complete', variant: 'success' });
    } catch {
      toast({ title: 'Upload failed', variant: 'destructive' });
      setUploadProgress(0);
    } finally {
      clearInterval(interval);
      setIsUploading(false);
    }
  };

  const handleDownloadErrors = () => {
    if (!result?.errors?.length) return;
    const csv = ['Row,Field,Error', ...result.errors.map(e => `${e.row},${e.field},${e.message}`)].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'upload_errors.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Bulk Uploads</h2>
        <p className="text-sm text-slate-500">Import data via CSV files or extract data from PDF invoices</p>
      </div>

      {/* Upload type selector */}
      <div className="flex gap-3">
        <Button
          variant={uploadType === 'csv' ? 'default' : 'outline'}
          onClick={() => setUploadType('csv')}
        >
          CSV / XLSX Upload
        </Button>
        <Button
          variant={uploadType === 'pdf' ? 'default' : 'outline'}
          onClick={() => setUploadType('pdf')}
        >
          PDF Invoice
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {uploadType === 'csv' ? 'Upload CSV File' : 'Upload PDF Invoice'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {uploadType === 'csv' && (
            <div className="space-y-1.5">
              <Label>Data Type *</Label>
              <Select value={dataType} onValueChange={setDataType}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Select data type" />
                </SelectTrigger>
                <SelectContent>
                  {DATA_TYPES.map(t => (
                    <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Drop zone */}
          <div
            className={cn(
              "border-2 border-dashed rounded-xl p-10 text-center transition-all cursor-pointer",
              isDragging
                ? "border-indigo-400 bg-indigo-50"
                : "border-slate-300 hover:border-indigo-400 hover:bg-slate-50"
            )}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={uploadType === 'csv' ? '.csv,.xlsx' : '.pdf'}
              className="hidden"
              onChange={handleFileSelect}
            />
            {selectedFile ? (
              <div className="space-y-2">
                <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center mx-auto">
                  <FileText className="w-6 h-6 text-indigo-600" />
                </div>
                <p className="font-medium text-slate-900">{selectedFile.name}</p>
                <p className="text-sm text-slate-500">{formatFileSize(selectedFile.size)}</p>
                <p className="text-xs text-indigo-600 hover:underline">Click to change file</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto">
                  <Upload className="w-6 h-6 text-slate-400" />
                </div>
                <div>
                  <p className="font-medium text-slate-700">Drop your file here, or click to browse</p>
                  <p className="text-sm text-slate-400 mt-1">
                    {uploadType === 'csv' ? 'Supports CSV and XLSX files' : 'Supports PDF files'}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Progress */}
          {isUploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm text-slate-600">
                <span>Uploading and processing...</span>
                <span>{uploadProgress}%</span>
              </div>
              <Progress value={uploadProgress} />
            </div>
          )}

          <Button
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
            loading={isUploading}
            size="lg"
          >
            <Upload className="w-4 h-4 mr-2" />
            {isUploading ? 'Processing...' : 'Upload & Process'}
          </Button>
        </CardContent>
      </Card>

      {/* Results */}
      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Upload Results</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: 'Total Rows', value: result.total_rows, color: 'text-slate-700' },
                { label: 'Valid', value: result.valid_rows, color: 'text-emerald-600' },
                { label: 'Invalid', value: result.invalid_rows, color: 'text-red-600' },
                { label: 'Duplicates', value: result.duplicate_rows, color: 'text-amber-600' },
              ].map((s) => (
                <div key={s.label} className="bg-slate-50 rounded-lg p-4 text-center">
                  <p className={`text-3xl font-bold ${s.color}`}>{s.value}</p>
                  <p className="text-xs text-slate-500 mt-1">{s.label}</p>
                </div>
              ))}
            </div>

            {result.invalid_rows > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-amber-700">
                    <AlertTriangle className="w-4 h-4" />
                    <span className="font-medium text-sm">{result.errors.length} validation errors</span>
                  </div>
                  <Button variant="outline" size="sm" onClick={handleDownloadErrors}>
                    <Download className="w-4 h-4 mr-2" />
                    Download Errors
                  </Button>
                </div>
                <div className="border border-red-200 rounded-lg overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-red-50">
                      <tr>
                        <th className="text-left py-2 px-3 font-semibold text-red-700">Row</th>
                        <th className="text-left py-2 px-3 font-semibold text-red-700">Field</th>
                        <th className="text-left py-2 px-3 font-semibold text-red-700">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.errors.map((err, i) => (
                        <tr key={i} className="border-t border-red-100">
                          <td className="py-1.5 px-3 text-red-700">{err.row}</td>
                          <td className="py-1.5 px-3 text-red-700">{err.field}</td>
                          <td className="py-1.5 px-3 text-red-600">{err.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {result.valid_rows > 0 && result.invalid_rows === 0 && (
              <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 rounded-lg p-3">
                <CheckCircle className="w-5 h-5" />
                <p className="text-sm font-medium">All {result.valid_rows} rows imported successfully!</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Template downloads */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Download Templates</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 mb-4">Use our CSV templates to ensure correct formatting</p>
          <div className="flex flex-wrap gap-3">
            {DATA_TYPES.map(t => (
              <Button key={t.value} variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                {t.label} Template
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
