import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, Plus, AlertTriangle, Package } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { productsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { formatCurrency } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import type { Product } from '../../types';

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  sku: z.string().min(1, 'SKU is required'),
  category: z.string().min(1, 'Category is required'),
  unit: z.string().default('pcs'),
  unit_price: z.number().min(0, 'Price must be positive'),
  cost_price: z.number().min(0).optional(),
  stock_quantity: z.number().min(0).default(0),
  low_stock_threshold: z.number().min(0).default(10),
  description: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

function ProductForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { unit: 'pcs', stock_quantity: 0, low_stock_threshold: 10 },
  });

  const onSubmit = async (data: FormData) => {
    try {
      await productsApi.create(data);
      toast({ title: 'Product created', variant: 'success' });
      queryClient.invalidateQueries({ queryKey: ['products'] });
      onClose();
    } catch {
      toast({ title: 'Failed to create product', variant: 'destructive' });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Product Name *</Label>
          <Input error={errors.name?.message} {...register('name')} placeholder="Product name" />
        </div>
        <div className="space-y-1.5">
          <Label>SKU *</Label>
          <Input error={errors.sku?.message} {...register('sku')} placeholder="SKU-001" />
        </div>
        <div className="space-y-1.5">
          <Label>Category *</Label>
          <Input error={errors.category?.message} {...register('category')} placeholder="Electronics" />
        </div>
        <div className="space-y-1.5">
          <Label>Unit</Label>
          <Input {...register('unit')} placeholder="pcs / kg / ltr" />
        </div>
        <div className="space-y-1.5">
          <Label>Selling Price (₹) *</Label>
          <Input type="number" step="0.01" error={errors.unit_price?.message} {...register('unit_price', { valueAsNumber: true })} />
        </div>
        <div className="space-y-1.5">
          <Label>Cost Price (₹)</Label>
          <Input type="number" step="0.01" {...register('cost_price', { valueAsNumber: true })} />
        </div>
        <div className="space-y-1.5">
          <Label>Stock Quantity</Label>
          <Input type="number" {...register('stock_quantity', { valueAsNumber: true })} />
        </div>
        <div className="space-y-1.5">
          <Label>Low Stock Threshold</Label>
          <Input type="number" {...register('low_stock_threshold', { valueAsNumber: true })} />
        </div>
        <div className="col-span-2 space-y-1.5">
          <Label>Description</Label>
          <Input {...register('description')} placeholder="Optional description" />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" loading={isSubmitting}>Create Product</Button>
      </DialogFooter>
    </form>
  );
}

export default function InventoryPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['products', page, search],
    queryFn: () => productsApi.list({ page, page_size: 20, search: search || undefined }),
  });

  const lowStockCount = data?.items?.filter((p: Product) => p.is_low_stock).length || 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Inventory</h2>
          <p className="text-sm text-slate-500">{data?.total || 0} total products</p>
        </div>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Add Product
        </Button>
      </div>

      {/* Low stock alert */}
      {lowStockCount > 0 && (
        <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />
          <p className="text-sm text-amber-800">
            <span className="font-semibold">{lowStockCount} product{lowStockCount > 1 ? 's' : ''}</span> are running low on stock
          </p>
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search products..."
              className="pl-9"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">{[1,2,3,4].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">SKU</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Name</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Category</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Stock</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Unit Price</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Total Value</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.length ? data.items.map((product: Product) => (
                    <tr key={product.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-mono text-xs text-slate-600">{product.sku}</td>
                      <td className="py-3 px-4">
                        <p className="font-medium text-slate-900">{product.name}</p>
                        {product.description && <p className="text-xs text-slate-400 truncate max-w-48">{product.description}</p>}
                      </td>
                      <td className="py-3 px-4 text-slate-600">{product.category}</td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {product.is_low_stock && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                          <span className={product.is_low_stock ? 'text-amber-600 font-semibold' : 'text-slate-900 font-medium'}>
                            {product.stock_quantity} {product.unit}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right font-semibold">{formatCurrency(product.unit_price)}</td>
                      <td className="py-3 px-4 text-right font-semibold text-slate-900">{formatCurrency(product.total_value || 0)}</td>
                      <td className="py-3 px-4">
                        {product.is_low_stock ? (
                          <Badge variant="secondary" className="text-amber-700 bg-amber-100">Low Stock</Badge>
                        ) : (
                          <Badge variant="success">In Stock</Badge>
                        )}
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="py-16 text-center">
                        <Package className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                        <p className="text-slate-400 text-sm">No products yet. Add your first product.</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-4">
              <Button variant="outline" size="sm" onClick={() => setPage(p => p - 1)} disabled={page === 1}>Previous</Button>
              <span className="text-sm text-slate-500">Page {page} of {data.total_pages}</span>
              <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page === data.total_pages}>Next</Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Add Product</DialogTitle>
          </DialogHeader>
          <ProductForm onClose={() => setShowForm(false)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
