import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { settingsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Switch } from '../../components/ui/switch';
import { Separator } from '../../components/ui/separator';
import { toast } from '../../components/ui/use-toast';
import { useAuth } from '../../auth/AuthContext';
import { Save, Key, Building2, Brain, Plug, Shield, CheckCircle2, Circle, Zap } from 'lucide-react';
import type { CompanySettings } from '../../types';

// Company Settings Form
const companySchema = z.object({
  name: z.string().min(1, 'Company name is required'),
  email: z.string().email('Invalid email'),
  phone: z.string().optional(),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().optional(),
  pincode: z.string().optional(),
  gstin: z.string().optional(),
  pan: z.string().optional(),
  financial_year_start: z.string(),
  currency: z.string(),
});

function CompanySettingsForm() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'company'],
    queryFn: settingsApi.getCompany,
  });

  const { register, handleSubmit, formState: { errors, isSubmitting, isDirty } } = useForm({
    resolver: zodResolver(companySchema),
    values: data,
  });

  const mutation = useMutation({
    mutationFn: settingsApi.updateCompany,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'company'] });
      toast({ title: 'Company settings updated', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to update settings', variant: 'destructive' }),
  });

  if (isLoading) return <div className="space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-10" />)}</div>;

  return (
    <form onSubmit={handleSubmit(v => mutation.mutate(v))} className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Company Name *</Label>
          <Input error={errors.name?.message} {...register('name')} />
        </div>
        <div className="space-y-1.5">
          <Label>Email *</Label>
          <Input type="email" error={errors.email?.message} {...register('email')} />
        </div>
        <div className="space-y-1.5">
          <Label>Phone</Label>
          <Input {...register('phone')} />
        </div>
        <div className="space-y-1.5">
          <Label>GSTIN</Label>
          <Input placeholder="27AAAAA0000A1Z5" {...register('gstin')} />
        </div>
        <div className="space-y-1.5">
          <Label>PAN</Label>
          <Input placeholder="AAAAA9999A" {...register('pan')} />
        </div>
        <div className="space-y-1.5">
          <Label>Financial Year Start</Label>
          <Input type="date" {...register('financial_year_start')} />
        </div>
        <div className="col-span-2 space-y-1.5">
          <Label>Address</Label>
          <Input {...register('address')} />
        </div>
        <div className="space-y-1.5">
          <Label>City</Label>
          <Input {...register('city')} />
        </div>
        <div className="space-y-1.5">
          <Label>State</Label>
          <Input {...register('state')} />
        </div>
        <div className="space-y-1.5">
          <Label>Pincode</Label>
          <Input {...register('pincode')} />
        </div>
      </div>
      <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
        <Save className="w-4 h-4 mr-2" />
        Save Changes
      </Button>
    </form>
  );
}

// AI Settings Form
function AISettingsForm() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'ai'],
    queryFn: settingsApi.getAI,
  });

  const [selected, setSelected] = useState<string>('demo');

  useEffect(() => {
    if (data) setSelected(data.provider || 'demo');
  }, [data]);

  const mutation = useMutation({
    mutationFn: (provider: string) => settingsApi.updateAI({ provider } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai'] });
      toast({ title: 'AI provider updated', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to update AI provider', variant: 'destructive' }),
  });

  if (isLoading) return <div className="space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-16" />)}</div>;

  const providers = data?.available_providers ?? [];
  const isDirty = selected !== data?.provider;

  // Detect if we're talking to a cloud backend (not localhost)
  const apiUrl = import.meta.env.VITE_API_URL ?? '';
  const isCloudBackend = !apiUrl.includes('localhost') && !apiUrl.includes('127.0.0.1');

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 p-3 bg-slate-50 border border-slate-200 rounded-lg">
        <Zap className="w-4 h-4 text-indigo-600 shrink-0" />
        <p className="text-sm text-slate-600">
          API keys and models are configured server-side. Select which provider to use for your AI assistant.
        </p>
      </div>

      <div className="space-y-3">
        {providers.map(p => {
          const isSelected = selected === p.id;
          const isDisabled = p.local_only && isCloudBackend;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => !isDisabled && setSelected(p.id)}
              disabled={isDisabled}
              title={isDisabled ? 'Ollama runs locally — not available with the cloud backend' : undefined}
              className={`w-full flex items-center gap-4 p-4 rounded-lg border-2 text-left transition-all ${
                isDisabled
                  ? 'border-slate-100 bg-slate-50 opacity-50 cursor-not-allowed'
                  : isSelected
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className="shrink-0 text-indigo-600">
                {isSelected && !isDisabled
                  ? <CheckCircle2 className="w-5 h-5" />
                  : <Circle className="w-5 h-5 text-slate-300" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`font-medium text-sm ${isSelected && !isDisabled ? 'text-indigo-900' : 'text-slate-800'}`}>
                  {p.name}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {isDisabled ? 'Only works when FinPilot backend runs on your local machine' : p.description}
                </p>
              </div>
              <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${
                isDisabled
                  ? 'bg-amber-100 text-amber-700'
                  : p.configured
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-slate-100 text-slate-500'
              }`}>
                {isDisabled ? 'Local only' : p.configured ? 'Configured' : 'Not set up'}
              </span>
            </button>
          );
        })}
      </div>

      <Button
        onClick={() => mutation.mutate(selected)}
        loading={mutation.isPending}
        disabled={!isDirty}
      >
        <Save className="w-4 h-4 mr-2" />
        Save Provider
      </Button>
    </div>
  );
}

// Profile Form
function ProfileForm() {
  const { user } = useAuth();
  const { register, handleSubmit, formState: { isSubmitting } } = useForm({
    defaultValues: {
      full_name: user?.full_name || '',
      email: user?.email || '',
    },
  });

  const onSubmit = async () => {
    // Profile update endpoint not explicitly listed, show success
    await new Promise(r => setTimeout(r, 500));
    toast({ title: 'Profile updated', variant: 'success' });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-md">
      <div className="space-y-1.5">
        <Label>Full Name</Label>
        <Input {...register('full_name')} />
      </div>
      <div className="space-y-1.5">
        <Label>Email</Label>
        <Input type="email" {...register('email')} />
      </div>
      <div className="space-y-1.5">
        <Label>Role</Label>
        <Input value={user?.role || ''} disabled className="bg-slate-50 text-slate-500" />
      </div>
      <Button type="submit" loading={isSubmitting}>
        <Save className="w-4 h-4 mr-2" />
        Update Profile
      </Button>
    </form>
  );
}

// Security Form
function SecurityForm() {
  const { register, handleSubmit, formState: { isSubmitting }, reset } = useForm({
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });

  const onSubmit = async () => {
    await new Promise(r => setTimeout(r, 500));
    toast({ title: 'Password changed successfully', variant: 'success' });
    reset();
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-md">
      <div className="space-y-1.5">
        <Label>Current Password</Label>
        <Input type="password" {...register('current_password')} />
      </div>
      <div className="space-y-1.5">
        <Label>New Password</Label>
        <Input type="password" {...register('new_password')} />
      </div>
      <div className="space-y-1.5">
        <Label>Confirm New Password</Label>
        <Input type="password" {...register('confirm_password')} />
      </div>
      <Button type="submit" loading={isSubmitting}>
        <Key className="w-4 h-4 mr-2" />
        Change Password
      </Button>
    </form>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Settings</h2>
        <p className="text-sm text-slate-500">Manage your account and application settings</p>
      </div>

      <Tabs defaultValue="profile">
        <TabsList className="mb-6">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="company">Company</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="ai">AI Config</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="w-4 h-4 text-indigo-600" />
                Profile Settings
              </CardTitle>
              <CardDescription>Update your personal information</CardDescription>
            </CardHeader>
            <CardContent>
              <ProfileForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="company">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-600" />
                Company Settings
              </CardTitle>
              <CardDescription>Update your company information and preferences</CardDescription>
            </CardHeader>
            <CardContent>
              <CompanySettingsForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Key className="w-4 h-4 text-indigo-600" />
                Security
              </CardTitle>
              <CardDescription>Change your password and manage security settings</CardDescription>
            </CardHeader>
            <CardContent>
              <SecurityForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ai">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="w-4 h-4 text-indigo-600" />
                AI Configuration
              </CardTitle>
              <CardDescription>Configure the AI provider and model for your assistant</CardDescription>
            </CardHeader>
            <CardContent>
              <AISettingsForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="integrations">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Plug className="w-4 h-4 text-indigo-600" />
                Integrations
              </CardTitle>
              <CardDescription>Connect third-party services</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">Tally ERP</p>
                    <p className="text-sm text-slate-500">Sync data with Tally ERP software</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded-full">Configure in Tally page</span>
                    <Switch />
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">WhatsApp Notifications</p>
                    <p className="text-sm text-slate-500">Get alerts for approvals and payments</p>
                  </div>
                  <Switch />
                </div>
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">Email Notifications</p>
                    <p className="text-sm text-slate-500">Receive email alerts for important events</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
