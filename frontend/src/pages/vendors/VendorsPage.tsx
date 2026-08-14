import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Search, Plus, Edit, Trash2, Building2 } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { vendorsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { StatusBadge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { formatCurrency } from '../../utils/format';
import { toast } from '../../components/ui/use-toast';
import type { Vendor } from '../../types';

const schema = z.object({
  name: z.string().min(2, 'Name is required'),
  email: z.string().email('Invalid email').optional().or(z.literal('')),
  phone: z.string().optional(),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().optional(),
  gst_number: z.string().optional(),
  pan_number: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

function VendorForm({ onClose, vendor }: { onClose: () => void; vendor?: Vendor }) {
  const queryClient = useQueryClient();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: vendor ? {
      name: vendor.name,
      email: vendor.email || '',
      phone: vendor.phone || '',
      address: vendor.address || '',
      city: vendor.city || '',
      state: vendor.state || '',
      gst_number: vendor.gst_number || '',
      pan_number: vendor.pan_number || '',
    } : undefined,
  });

  const onSubmit = async (data: FormData) => {
    try {
      if (vendor) {
        await vendorsApi.update(vendor.id, data);
        toast({ title: 'Vendor updated', variant: 'success' });
      } else {
        await vendorsApi.create(data);
        toast({ title: 'Vendor created', variant: 'success' });
      }
      queryClient.invalidateQueries({ queryKey: ['vendors'] });
      onClose();
    } catch {
      toast({ title: 'Failed to save vendor', variant: 'destructive' });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2 space-y-1.5">
          <Label>Name *</Label>
          <Input placeholder="Vendor name" error={errors.name?.message} {...register('name')} />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input type="email" placeholder="vendor@example.com" {...register('email')} />
        </div>
        <div className="space-y-1.5">
          <Label>Phone</Label>
          <Input placeholder="+91 98765 43210" {...register('phone')} />
        </div>
        <div className="col-span-2 space-y-1.5">
          <Label>Address</Label>
          <Input placeholder="Street address" {...register('address')} />
        </div>
        <div className="space-y-1.5">
          <Label>City</Label>
          <Input placeholder="Mumbai" {...register('city')} />
        </div>
        <div className="space-y-1.5">
          <Label>State</Label>
          <Input placeholder="Maharashtra" {...register('state')} />
        </div>
        <div className="space-y-1.5">
          <Label>GSTIN</Label>
          <Input placeholder="27AAAAA0000A1Z5" {...register('gst_number')} />
        </div>
        <div className="space-y-1.5">
          <Label>PAN</Label>
          <Input placeholder="AAAAA9999A" {...register('pan_number')} />
        </div>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" loading={isSubmitting}>{vendor ? 'Update' : 'Create'} Vendor</Button>
      </DialogFooter>
    </form>
  );
}

export default function VendorsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingVendor, setEditingVendor] = useState<Vendor | undefined>();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['vendors', page, search],
    queryFn: () => vendorsApi.list({ page, page_size: 20, search: search || undefined }),
  });

  const deleteMutation = useMutation({
    mutationFn: vendorsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vendors'] });
      toast({ title: 'Vendor deleted', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to delete vendor', variant: 'destructive' }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Vendors</h2>
          <p className="text-sm text-slate-500">{data?.total || 0} total vendors</p>
        </div>
        <Button onClick={() => { setEditingVendor(undefined); setShowForm(true); }}>
          <Plus className="w-4 h-4 mr-2" />
          Add Vendor
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input
              placeholder="Search vendors..."
              className="pl-9"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
            />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-14" />)}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Name</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Email</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Phone</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Total Spend</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Outstanding</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-slate-500 uppercase tracking-wide">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items?.length ? data.items.map((vendor: Vendor) => (
                    <tr key={vendor.id} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4">
                        <div>
                          <p className="font-medium text-slate-900">{vendor.name}</p>
                          {vendor.gst_number && <p className="text-xs text-slate-400">GSTIN: {vendor.gst_number}</p>}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{vendor.email || '-'}</td>
                      <td className="py-3 px-4 text-slate-600">{vendor.phone || '-'}</td>
                      <td className="py-3 px-4 text-right font-semibold text-slate-900">{formatCurrency(vendor.total_purchases || 0)}</td>
                      <td className="py-3 px-4 text-right">
                        <span className={vendor.outstanding_payable > 0 ? 'text-amber-600 font-semibold' : 'text-slate-600'}>
                          {formatCurrency(vendor.outstanding_payable || 0)}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${vendor.is_active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-600'}`}>
                          {vendor.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex gap-2">
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-indigo-600"
                            onClick={() => { setEditingVendor(vendor); setShowForm(true); }}>
                            <Edit className="w-4 h-4" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-600"
                            onClick={() => { if (confirm('Delete this vendor?')) deleteMutation.mutate(vendor.id); }}>
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={7} className="py-16 text-center">
                        <Building2 className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                        <p className="text-slate-400 text-sm">No vendors yet. Add your first vendor.</p>
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
            <DialogTitle>{editingVendor ? 'Edit Vendor' : 'Add Vendor'}</DialogTitle>
          </DialogHeader>
          <VendorForm onClose={() => setShowForm(false)} vendor={editingVendor} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
